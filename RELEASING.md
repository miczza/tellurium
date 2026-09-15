# Release procedure

Two repositories ship independently:

| Repo | Artifact | Where it goes |
| --- | --- | --- |
| `tellurium` (this repo) | sdist + wheel | PyPI + a GitHub Release |
| `chromium-telluride` | a ~191 MiB tarball + 2 sidecars | a GitHub Release only |

**Release `chromium-telluride` first.** `tellurium download-browser --browser
patched` resolves the binary from `chromium-telluride`'s GitHub Releases, so
publishing tellurium first ships a command that 404s.

Neither repo has a git remote configured yet. Everything below is a one-time
bootstrap followed by a repeatable tag-and-push.

---

## 0. Prerequisites

```bash
# gh is NOT installed on this machine
pacman -S github-cli      # Arch / CachyOS
gh auth login
```

`gh` is only needed for `chromium-telluride` (uploading a 191 MiB asset).
Everything for tellurium runs inside GitHub Actions. If you would rather not
install `gh`, every `gh` step below has a web-UI equivalent, noted inline.

---

## 1. chromium-telluride

Repo: `/home/miczza/PycharmProjects/chromium-telluride`, branch `main`.

### 1.1 Confirm the artifacts are on disk

`scripts/release.sh` has already been run (2026-09-15) and wrote the three
release assets to the repo root. It never tags and never pushes — that is
operator work. Verify before publishing:

```bash
cd /home/miczza/PycharmProjects/chromium-telluride
ls -l chromium-telluride-146.0.7680.188-linux-x64.tar.gz MANIFEST.json SHA256SUMS
sha256sum -c SHA256SUMS
./scripts/validate-manifest.sh MANIFEST.json --release
```

Expected tarball SHA-256:

```
5205b114d19fc427fa557893bb362e97528d702719313d4895328f6b406151a6
```

To re-cut the release from an already-built tree instead:

```bash
./scripts/release.sh --seed=42069 --skip-build --skip-repro
```

`--skip-build` packages whatever is in `src/out/Release` (add
`--out-dir=PATH` if the build lives elsewhere); `--skip-repro` skips the
~5 h two-build reproducibility test. The run gates the tarball layout, checks
the sidecar `MANIFEST.json` is byte-identical to the in-tarball copy, verifies
`SHA256SUMS`, and requires `creepjs_lies == 0` in release mode.

### 1.2 Create the remote and push

```bash
cd /home/miczza/PycharmProjects/chromium-telluride
git remote add origin git@github.com:miczza/chromium-telluride.git
git push -u origin main
git push --tags        # optional: the pre-existing rc/dev tags
```

(Create the repository on github.com first, or use
`gh repo create miczza/chromium-telluride --public --source=. --push`.)

### 1.3 Tag

The release contract is `v<telluride_version>-<chromium_upstream>`, both read
from `MANIFEST.json` (`version` and `chromium_upstream`):

```bash
git tag -a v0.1.0-146.0.7680.188 \
    -m "v0.1.0 (Chromium 146.0.7680.188, 32 patches, 0 CreepJS lies)"
git push origin v0.1.0-146.0.7680.188
```

> The repo already carries `v0.1.0-rc0-…`, `v0.1.0-rc1-…`, `v0.1.0-rc2`,
> `v0.2.0-rc1`, `v0.3.0`, `v0.4.0`, `v0.4.0-rc1` from earlier experiments.
> `v0.1.0-146.0.7680.188` has never existed. Only the tags carrying the
> `-<chromium_upstream>` suffix follow the contract; the rest are noise and
> should not be published as releases.

`.github/workflows/build-linux.yml` fires on `v*` tags but runs on a
**self-hosted** runner and only uploads workflow *artifacts* — it does not
create a Release. With no self-hosted runner registered it will simply queue;
the release upload below is manual either way.

### 1.4 Create the GitHub Release with all three assets

All three files must be attached. tellurium's installer reads `SHA256SUMS`
before downloading and `MANIFEST.json` without downloading the tarball, so a
release missing a sidecar is unusable.

```bash
cd /home/miczza/PycharmProjects/chromium-telluride
gh release create v0.1.0-146.0.7680.188 \
    chromium-telluride-146.0.7680.188-linux-x64.tar.gz \
    MANIFEST.json \
    SHA256SUMS \
    --title "chromium-telluride v0.1.0 (Chromium 146.0.7680.188)" \
    --notes "Chromium 146.0.7680.188 Extended Stable, 32 patches, CreepJS lies = 0.
Linux x64 only. chrome_sandbox is not bundled: launch with --no-sandbox or
enable unprivileged user namespaces."
```

**Without `gh`**: github.com → *Releases* → *Draft a new release* → pick the
existing tag `v0.1.0-146.0.7680.188` → drag the three files into the asset
box → *Publish release*. Attach them as separate assets; do not zip them.

### 1.5 Post-release verification from tellurium

```bash
cd /home/miczza/PycharmProjects/tellurium
.venv/bin/tellurium download-browser --browser patched
.venv/bin/tellurium list-browsers
.venv/bin/tellurium verify-browser
.venv/bin/tellurium info
```

This exercises the whole contract end to end: GitHub Releases lookup →
`SHA256SUMS` check → safe tar extraction into
`~/.tellurium/chromium/146.0.7680.188/` → `binary_sha256["linux-x64"]`
verification against `MANIFEST.json` → `current` symlink.

Then a real launch (remember the missing sandbox):

```bash
.venv/bin/python - <<'EOF'
import asyncio
from tellurium import Browser

async def main():
    b = await Browser.launch(browser="patched", seed=42069,
                             args=["--no-sandbox"])
    async with b:
        tab = await b.new_tab("https://example.com")
        print(await tab.eval("navigator.userAgent"))

asyncio.run(main())
EOF
```

`tests/integration/test_patched_e2e.py` un-skips once a patched binary is
installed, so `make test-integration` now covers the fork too.

---

## 2. tellurium

### 2.1 Create the remote and push

```bash
cd /home/miczza/PycharmProjects/tellurium
git remote add origin git@github.com:miczza/tellurium.git
git push -u origin master
```

(Or `gh repo create miczza/tellurium --public --source=. --push`.)

Note the default branch is `master` here; `ci.yml` is wired to `master`.

### 2.2 One-time GitHub + PyPI setup

Full detail in [`.github/workflows/README.md`](../.github/workflows/README.md).

1. **Create the `pypi` environment**: repo *Settings* → *Environments* →
   *New environment* → name it exactly `pypi`. Optionally add a required
   reviewer so every publish needs manual approval.
2. **Register the trusted publisher on PyPI**: pypi.org → *Your projects* →
   *Publishing*. For a project that has never been uploaded, use
   *Publishing* → *Add a pending publisher*:
   - Owner: `miczza`
   - Repository: `tellurium`
   - Workflow name: `release.yml`
   - Environment: `pypi`

   Trusted publishing uses OIDC, so no API token is ever stored in the repo.
3. **(Optional) branch protection**: require `unit`, `integration` and `build`
   as status checks on `master`.

### 2.3 Pre-release checklist

```bash
cd /home/miczza/PycharmProjects/tellurium
make test                                  # unit + integration + stealth
make lint                                  # ruff check + ruff format --check
make parity                                # CreepJS gate — NEEDS network + display
make build                                 # uv build + twine check --strict
```

- `make test` must be green. `make lint` is still `continue-on-error` in CI
  (lint backlog: `BLE001`, `F841`, `E741`, `B904`, `B905`); it is not a
  release blocker yet.
- `make parity` is the 8/8 CreepJS gate and is **not** part of CI by design
  (it hits third-party sites). It must pass before a release; it updates
  `examples/fingerprint_tests/comparative_results.json`, so commit the diff
  if the numbers moved.
- `make build` runs `uv build` then `uvx twine check --strict dist/*`. Both the
  sdist and the wheel must validate.

Then:

1. Bump `version` in `pyproject.toml`.
2. Move the `## [Unreleased]` entries in `CHANGELOG.md` into a new
   `## [X.Y.Z] - <date>` section — `release.yml` extracts exactly that section
   as the GitHub Release body.
3. Commit both.

### 2.4 Tag and publish

```bash
git tag v0.1.0
git push origin v0.1.0
# or: git push --tags
```

Pushing a `v*` tag runs `.github/workflows/release.yml`:

1. **`build`** — sdist + wheel, `twine check --strict`, and extracts the
   matching `## [X.Y.Z]` section from `CHANGELOG.md` into `release-notes.md`.
2. **`publish-pypi`** — `pypa/gh-action-pypi-publish` in the `pypi`
   environment via trusted publishing (OIDC).
3. **`github-release`** — `softprops/action-gh-release@v2`, body from
   `release-notes.md`, with the sdist and wheel attached.

The workflow also accepts `workflow_dispatch` with an existing tag, for a
re-run after a transient failure.

### 2.5 Post-release verification

```bash
python -m venv /tmp/tel-check && /tmp/tel-check/bin/pip install tellurium
/tmp/tel-check/bin/tellurium info
/tmp/tel-check/bin/python -c "import tellurium; print(tellurium.__version__)"
/tmp/tel-check/bin/pip install 'tellurium[geoip]'   # optional extra
```

---

## 3. Order of operations, condensed

```
chromium-telluride:  verify assets -> remote + push main -> tag v0.1.0-146.0.7680.188
                     -> gh release create (3 assets) -> tellurium download-browser
                        --browser patched + verify-browser

tellurium:           remote + push master -> create `pypi` environment
                     -> PyPI pending trusted publisher -> make test/lint/parity/build
                     -> CHANGELOG + version bump -> git tag v0.1.0 && git push --tags
                     -> release.yml publishes PyPI + GitHub Release
```
