# CI workflows

## `ci.yml` — DRAFT

Status: **DRAFT, not yet active.**

This workflow ships in v0.1 of tellurium ready-to-trigger. It does not
run on the local development machine because there is no GitHub remote
configured at v0.1 release time.

### What it does

- **`unit` job** — runs `tests/unit` on Python 3.10 + 3.13 (Linux only).
- **`build` job** — produces sdist + wheel via `python -m build`,
  uploads as artifact (gated on `unit` passing).

### What it intentionally does NOT do

- `tests/stealth` and `tests/integration` are **skipped** in CI.
  They require a Chrome runtime + `DISPLAY` and are run locally:
  ```bash
  DISPLAY=:0 .venv/bin/pytest tests/stealth tests/integration
  ```
- Multi-OS matrix (macOS / Windows runners) — out of scope for v0.1,
  Linux only.

### Activation procedure

1. Create a GitHub remote (`gh repo create` or push to a created repo).
2. Push the branch / open a PR.
3. GitHub Actions auto-discovers `.github/workflows/ci.yml` and
   runs on next push / PR.
4. (Optional) enable required-status-checks on `main` in branch protection.

No code change is required to activate.
