# GitHub Actions workflows

Three workflows. `ci.yml` also runs on Windows and macOS; the other two are
Linux-only.

| Workflow | Trigger | Blocking? |
| --- | --- | --- |
| `ci.yml` | push to `master` and `fetta/**`, any PR, manual | yes, on all three systems (`lint` included) |
| `release.yml` | push of a `v*` tag, manual | n/a |
| `nightly-creepjs.yml` | weekly cron (Mon 04:17 UTC), manual | no — informational |

---

## `ci.yml`

Status: **active** (no longer a draft). Concurrency group per ref and event
with `cancel-in-progress: true`, so a new push supersedes the in-flight push
run, and a manual run does not cancel it. Every job installs the `geoip`,
`dev` and `mcp` extras, so the MCP tests run too.

- **`lint`** — `ruff check` + `ruff format --check` over the whole repo,
  ruff pinned via the `RUFF_VERSION` env var to the version the flow's gate
  runs (`uvx ruff`, currently 0.17.3). Blocking: a lint error fails the run.
- **`unit`** — `pytest tests/unit` on Python 3.11 / 3.12 / 3.13.
- **`integration`** — Python 3.12, Chrome stable via
  `browser-actions/setup-chrome@v1`, then
  `xvfb-run -a pytest tests/integration tests/stealth -q` (40 min timeout:
  about 780 tests take longer than 20 min on a hosted runner).
  `tests/integration` runs headless against local HTTP servers and discovers
  the browser through `tellurium/browser/launcher.py::find_chrome()`;
  `tests/stealth` is offline but needs a `DISPLAY`, hence `xvfb-run`.
- **Which Chrome** — the tests on every system run setup-chrome's Chrome,
  not the runner image's own. `find_chrome()` reads no environment variable,
  so each job puts that Chrome where `find_chrome()` looks first: on Linux a
  managed-install entry, `~/.tellurium/browsers/google-chrome-stable/chrome`
  (a symlink; the folder name keeps `google-chrome` in the path, which is how
  tellurium tells a branded Chrome); on macOS setup-chrome's bundle replaces
  `/Applications/Google Chrome.app` (the image's goes aside). On Windows
  setup-chrome does not install: it takes the Chrome already in
  `Program Files` as "stable" ("Found in cache"), and the image's is often a
  version behind; so a step first updates it in place with Google's
  enterprise MSI. The step *Check the Chrome the tests use*
  (`python -m tests.ci_chrome`, in `integration` and `integration-os`)
  fails the job unless `find_chrome()` picks setup-chrome's Chrome, it
  launches, and its major version is the current stable one from Google's
  version history: the three systems run the same major.
- **Chrome's sandbox on Linux** — Ubuntu 24.04 restricts unprivileged
  user namespaces through AppArmor and Chrome from the tool cache has no
  AppArmor profile, so it aborts with `No usable sandbox!`. The Linux `unit`
  and `integration` jobs run
  `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` first.
- **`unit-os`** and **`integration-os`** — the same suites on
  `windows-2025` (x64) and `macos-15` (arm64), Python 3.12, one job per
  system and suite, `fail-fast: false`, 25 min (unit) and 35 min
  (integration) timeout. Chrome stable
  comes from `browser-actions/setup-chrome@v1` (see *Which Chrome*). No
  `xvfb-run`: both systems have a display, and `tests/conftest.py` skips its
  private Xvfb when there is no `Xvfb` binary; `tests/platform_marks.py`
  counts Windows and macOS as having a display. On macOS a step aliases
  `127.0.0.2` on `lo0`: the `other_server` fixture listens there, and macOS
  routes only `127.0.0.1` to loopback until told.
  `tests/stealth` stays on Linux. `integration-os` runs in four shards of
  test files balanced on their durations (`python -m tests.shard <n> 4`,
  weights in `tests/integration/durations.json`, the slowest system of a run;
  refresh it from the JUnit reports when the suite changes), because the
  whole suite takes about 55 min on a hosted runner; each shard ends near
  14 min. `pytest-timeout` (120 s per test for unit, 300 s for
  `integration-os`, whose waits for Chrome are x3 and at least 30 s, see
  `tests/timeout_scale.py`; a failing test adding a few of them up must fail
  with its own error) bounds a hang: on macOS (signal method) it fails that test and the run goes
  on; on Windows only the thread method exists, which dumps the stacks and
  ends the whole pytest process, so the rest of that shard does not run and
  there is no JUnit report for it. `-v` names the test that was running in
  either case, and each job uploads its JUnit
  XML as `junit-<suite>-<os>[-<shard>]`. The diagnostic step does not run
  `chrome.exe --version`: on Windows it opens a browser window and never
  exits.
  - **When**: on the same events as the Linux jobs (every push to `master`
    and `fetta/**`, every PR, manual runs). The repo is public, so hosted
    runners cost no minutes; what limits a run is the queue (an account runs
    few macOS jobs at a time, and one run asks for five), so a push that
    supersedes another cancels its run (`cancel-in-progress`), and a targeted
    manual run (below) is the quick way to retry one test on one system.
  - **Blocking**: a red test on Windows or macOS fails the run as on Linux.
    The job **`os-results`** (after them, `if: always()`) downloads their JUnit
    reports, writes one table of tests, failures, errors and skips per job
    and the failed tests to the run's summary (`python -m tests.ci_results`),
    and fails the run when a job left no report (it was cancelled, timed out,
    or its pytest was killed, so part of its tests never ran) or a report
    without a single test (pytest collected nothing).
  - **Skips**: a test is skipped on a system only when it exercises
    something that does not exist there (POSIX fds, `fork`, `SIGKILL`,
    `SingletonLock` symlinks, `/proc`), with a `reason=` saying so, on the
    test itself rather than its module: the shared marks live in
    `tests/platform_marks.py`. A test that fails because of a defect in
    `tellurium/` is never skipped.
  - Manual run: `gh workflow run ci.yml --ref <branch>`; read a red with
    `gh run view <id> --log-failed`. A targeted run costs less:
    `-f os=windows-2025 -f tests="tests/integration/test_downloads.py"`
    runs only those paths, in one job, on that system (`os` is `all`,
    `ubuntu-latest`, `windows-2025` or `macos-15`); with `tests` set the unit
    jobs are skipped and the Linux `integration` job runs those paths instead
    of its suites.
- **`build`** — `python -m build`, `twine check --strict`, uploads `dist/`
  as an artifact. Gated on `unit`.

Ruff configuration lives in `pyproject.toml` (`[tool.ruff]`). Generated and
vendored trees — notably `tellurium/cdp/domains` (emitted by
`tellurium/cdp/generator.py`) — are listed in `extend-exclude` and are never
linted.

### Not in CI, deliberately

- `examples/fingerprint_tests/test_stock_runtime_parity.py` — the CreepJS
  gate. It hits third-party sites, so it must never block a merge; it lives
  in `nightly-creepjs.yml` instead.

---

## `release.yml`

Triggered by pushing a `v*` tag (or manually, passing an existing tag):

1. **`build`** — sdist + wheel, `twine check --strict`, and extracts the
   matching `## [X.Y.Z]` section from `CHANGELOG.md` into `release-notes.md`
   (small `awk` script; falls back to a generic body if the section is
   missing). Both are uploaded as artifacts.
2. **`publish-pypi`** — `pypa/gh-action-pypi-publish@release/v1` using
   **trusted publishing** (OIDC — no API token stored in the repo).
   Runs in the `pypi` environment with `permissions: id-token: write`.
3. **`github-release`** — `softprops/action-gh-release@v2`, body from
   `release-notes.md`, attaching the sdist and wheel.

### One-time setup

1. **Repo**: done — `origin` is the public `miczza/tellurium`.
2. **Register the trusted publisher on PyPI**: log in to PyPI →
   *Your projects* → `tellurium` → *Publishing* (for a brand-new project, use
   *Publishing* → *Add a pending publisher* before the first upload) and add a
   GitHub publisher with:
   - Owner: `miczza`
   - Repository: `tellurium`
   - Workflow name: `release.yml`
   - Environment: `pypi`
3. **Create the `pypi` environment** in GitHub: repo *Settings* →
   *Environments* → *New environment* → name it `pypi`. Optionally add a
   required reviewer so every publish needs a manual approval.
4. **(Optional) branch protection**: require `unit`, `integration` and `build`
   as status checks on `master`.
5. **Release**: bump `version` in `pyproject.toml`, add the `## [X.Y.Z]`
   section to `CHANGELOG.md`, commit, then
   `git tag v0.1.0 && git push origin v0.1.0`.

---

## `nightly-creepjs.yml`

Weekly (and on demand) run of the CreepJS stock-runtime parity gate:
Chrome stable + `xvfb-run -a pytest examples/fingerprint_tests/test_stock_runtime_parity.py`.
The job and the test step are both `continue-on-error: true` — a red run is a
signal to investigate, never a broken build. `comparative_results.json` is
uploaded as an artifact (`if: always()`) so results can be diffed over time.
