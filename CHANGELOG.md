# Changelog

All notable changes to tellurium are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

(none)

## [0.1.0] - 2026-04-26

First release-ready version of tellurium as an independent Python library.
Stock-Chrome path is fully functional; patched-binary path is experimental
(manual install workflow).

### Added

- T1: CDP layer (pipe transport, no observable WebSocket port)
- T2: Browser core (launch, tab management, navigation, element selection)
- T3: Stealth engine (Chrome-extension-based stealth patches; no detectable script injection)
- T4: Human input simulation (Wind Mouse, biomechanically correct typing dynamics)
- T5: Network capture (CDP-based request/response interception)
- T6: Testing & packaging baseline (294 unit tests + 28 stealth tests)
- T7: Runtime stealth via CDP `Page.addScriptToEvaluateOnNewDocument`
  (works on Chrome branded ≥137 where `--load-extension` is rejected)
- T7.5: Stealth scripts cleanup (consolidated, marker scheme for cross-realm masking)
- T7.6: Stealth hardening — 8/8 CreepJS parity with nodriver, 0 lies, headless=0%
- Stock-Chrome path: first-class, fully documented in README
- Patched-binary path: experimental, manual install via `executable=` kwarg
  or `~/.tellurium/chromium/<version>/` cache layout (see README)
- Optional `[geoip]` dependency for proxy-exit-IP-based timezone/locale resolution

### Verified

- **Build dry-run**: `uv build` produces clean sdist (337 KB after explicit
  `[tool.hatch.build.targets.sdist]` whitelist) + wheel (309 KB). Both
  install cleanly in a fresh Python 3.13 venv. `tellurium.__version__`
  returns `0.1.0`. `[geoip]` optional dep installs `maxminddb==3.1.1` and
  imports. `tellurium --help` post-install shows all 8 subcommands.
  LICENSE and METADATA verified in wheel `dist-info/`.
- **Multi-Python**: unit suite (296 tests = 294 baseline + 2 new CLI
  messaging tests) passes on Python 3.10.20 (uv-installed) and Python
  3.13.13 (uv-installed). No syntax or library incompatibilities surfaced.
- **3.10 syntax compatibility**: pre-flight grep for Python 3.11+ idioms
  (`typing.Self`, `ExceptionGroup`/`except*`, `@override`, `TypeAliasType`,
  PEP 695 `type` statement) found zero hits across the `tellurium/` package.
- **Stealth regression**: `tests/stealth` 28/28 green in 12.78s. Live
  CreepJS comparative (`examples/fingerprint_tests/comparative_test.py`)
  shows tellurium parity **8/8** with the nodriver baseline,
  `headless=0%`, `like_headless=38%`, `stealth=0%`, `lies=0`,
  `webdriver=False`, sannysoft 0 fails, browserscan no bot. No regression
  vs T7.6 baseline. Chrome version: 147.0.7727.101.
- **CI workflow**: `.github/workflows/ci.yml` YAML syntax valid (parses via
  `yaml.safe_load`), draft state documented in `.github/workflows/README.md`,
  ready-to-activate on first GitHub push.

### Known limitations

- `like_headless ~38%` on CreepJS is environmental (display/GPU/audio fingerprint), no lies
- Patched binary is experimental in v0.1; auto-download tooling deferred to v0.1.x
- 3 lies on CreepJS when using the experimental patched binary —
  tracked in chromium-telluride repository

### Deferred (future)

- Auto-download tooling for patched binary (`update-browser`, `verify-browser --reinstall`)
- T7 Honeypot + robots.txt detection
- F6 worker-scope webdriver masking
- F7 dynamic same-origin iframe injection
- `_NATIVE_SHAPES` array refactor (T7.6 reviewer note)
- CreepJS bundle content hashing for drift detection (T7.6 reviewer note)
- Periodic baseline re-validation cadence
- Multi-OS CI matrix (macOS, Windows)

### Notes

- CI workflow `.github/workflows/ci.yml` exists in draft state, not yet active
  (no GitHub remote at v0.1 release time)
- Pre-migration history of C-series specs (chromium-telluride patches) reachable from `tellurium@ace0afa`
