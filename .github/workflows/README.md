# GitHub Actions workflows

Three workflows. `ci.yml` also runs on Windows and macOS; the other two are
Linux-only.

| Workflow | Trigger | Blocking? |
| --- | --- | --- |
| `ci.yml` | push to `master` and `fetta/**`, any PR, manual | Linux jobs yes (except `lint`, for now); Windows/macOS no, until C6 is merged |
| `release.yml` | push of a `v*` tag, manual | n/a |
| `nightly-creepjs.yml` | weekly cron (Mon 04:17 UTC), manual | no — informational |

---

## `ci.yml`

Status: **active** (no longer a draft). Concurrency group per ref with
`cancel-in-progress: true`, so a new push supersedes the in-flight run.

- **`lint`** — `ruff check` + `ruff format --check` over the whole repo,
  ruff pinned via the `RUFF_VERSION` env var.
  **Currently `continue-on-error: true`**: the existing code has a lint
  backlog (see the TODO comment in the job). Most of it disappears with
  `ruff check --fix` + `ruff format`; the manual remainder is `BLE001`,
  `F841`, `E741`, `B904`, `B905`. Flip to `false` once clean.
- **`unit`** — `pytest tests/unit` on Python 3.11 / 3.12 / 3.13.
- **`integration`** — Python 3.12, Chrome stable via
  `browser-actions/setup-chrome@v1`, then
  `xvfb-run -a pytest tests/integration tests/stealth -q` (40 min timeout:
  about 780 tests take longer than 20 min on a hosted runner).
  `tests/integration` runs headless against local HTTP servers and discovers
  the browser through `tellurium/browser/launcher.py::find_chrome()`;
  `tests/stealth` is offline but needs a `DISPLAY`, hence `xvfb-run`.
- **Chrome's sandbox on Linux** — Ubuntu 24.04 restricts unprivileged
  user namespaces through AppArmor and Chrome from the tool cache has no
  AppArmor profile, so it aborts with `No usable sandbox!`. The Linux `unit`
  and `integration` jobs run
  `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0` first.
- **`unit-os`** and **`integration-os`** — the same suites on
  `windows-2025` (x64) and `macos-15` (arm64), Python 3.12, one job per
  system and suite, `fail-fast: false`, 25 min timeout each. Chrome stable
  comes from `browser-actions/setup-chrome@v1` and its path is exported as
  `STOCK_CHROME`; the step *Show the Chrome the tests use* prints that path
  and what `find_chrome()` picks (the runner image also ships its own
  Chrome). No `xvfb-run`: both systems have a display, and
  `tests/conftest.py` skips its private Xvfb when there is no `Xvfb` binary.
  `tests/stealth` stays on Linux. `pytest-timeout` (120 s per unit test,
  180 s per integration test) turns a hang into a red test instead of a
  killed job, and each job uploads its JUnit XML as `junit-<suite>-<os>`.
  - **When**: only on `workflow_dispatch` and on pushes to `fetta/C6-*`
    branches. The repo is private: macOS minutes count x10 and Windows x2
    against the free 2000 min/month, so ordinary pushes stay Linux-only.
    After C6 is merged they also run on `master`.
  - **Blocking**: `continue-on-error: true` until C6 is merged; the known
    reds are listed per system in `docs/requests/C6.md`.
  - **Skips**: a test is skipped on a system only when it exercises
    something that does not exist there (POSIX fds, `fork`, `SIGKILL`,
    `SingletonLock` symlinks, `/proc`), with a `reason=` saying so. A test
    that fails because of a defect in `tellurium/` is never skipped.
  - Manual run: `gh workflow run ci.yml --ref <branch>`; read a red with
    `gh run view <id> --log-failed`.
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

1. **Repo**: done — `origin` is the private `miczza/tellurium`.
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
