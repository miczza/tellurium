# Changelog

All notable changes to tellurium are documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- `Browser.launch(chrome_log=path)` appends Chrome's stdout and stderr to a
  file. By default the output is discarded, keeping only its tail in memory.
- Patched-binary auto-install: `tellurium download-browser --browser patched
  [--version]`, `update-browser` (installs; `--security-only`), `verify-browser
  --reinstall` now wired. Releases are fetched from GitHub Releases of
  `chromium-telluride`, checked against `SHA256SUMS`, extracted safely and the
  `chrome` binary verified against `MANIFEST.json`.
- `Browser.launch(auto_security_update=True)` installs security releases found
  by the daily check (was `NotImplementedError`).
- `TELLURIUM_CACHE_DIR` environment override for the browser cache.
- `tellurium stealth-test`: fixed (`async with` on a coroutine), adds toString
  shape invariants, `--full` visits sannysoft/browserscan, `--headed`.
- OOPIF and worker stealth patching: `Target.setAutoAttach` with
  `waitForDebuggerOnStart=True`, wired on **every page session** (a
  browser-root-only auto-attach never fires for a page's OOPIFs or dedicated
  workers), `Page.enable` on OOPIF sessions so scripts run at document-start,
  and `Runtime.runIfWaitingForDebugger` only after the patches land — an
  anti-bot inside a cross-origin frame never sees an unpatched value.
- `tellurium/stealth/scripts/worker_navigator.js`: worker targets get
  `hardwareConcurrency` parity with the main world. `navigator.webdriver` is
  deliberately left undefined in workers — real Chrome's `WorkerNavigator` has
  no such property, so defining one would be a new fingerprint (closes the
  T7.6 F6 candidate by deciding against it).
- `Tab.window_offset()` and P0.4 screen parity: Chrome already derives
  `screenX`/`screenY` from the window origin, so tellurium only repairs the
  degenerate placement (window at `(0,0)` without a frame, where
  `screenX === clientX`). All mouse dispatch now goes through
  `Tab._dispatch_mouse()`; no-op on backends advertising `native_cdp_fix`.
- `Browser.launch(stealth_idle=True)`: `Tab.wait()` emits low-amplitude mouse
  micro-movements via `IdleSimulator` instead of a perfectly still cursor.
- `ActionTimer` wired into `human=True` click / type / scroll / navigate, with
  a log-normal fallback (median ~270 ms, capped at 2 s) for action pairs that
  `ACTION_TRANSITION_DELAYS` does not list.
- `tellurium download-geoip`: installs DB-IP Country Lite (CC BY 4.0, no
  account) or MaxMind GeoLite2-Country with `--maxmind-license-key` into
  `~/.tellurium/geolite2/`. `resolve_geoip()` also searches
  `$TELLURIUM_GEOIP_DB` and falls back to a one-shot online IP→country lookup
  when no database is installed (a bundled database is not licensable).
  `tellurium info` reports the database in use.
- `tests/integration/test_patched_e2e.py`: patched-backend end-to-end coverage
  (skipped unless a `chromium-telluride` binary is installed in the cache or
  via `TELLURIUM_PATCHED_EXECUTABLE`) — `--fingerprint` flag, random-seed
  default, per-seed canvas determinism, `stealth=True` on the native backend.
- CI/tooling: `ci.yml` activated (ruff lint non-blocking, unit matrix
  3.10–3.13, integration + stealth under xvfb with Chrome stable, build +
  `twine check`), `release.yml` (tag `v*` → build → PyPI trusted publishing →
  GitHub Release with the CHANGELOG section as body), `nightly-creepjs.yml`
  (weekly parity gate, results uploaded as an artifact), `[tool.ruff]` in
  `pyproject.toml`, and a `Makefile` (`test`, `lint`, `fmt`, `build`,
  `parity`, `clean`).
- `docs/RELEASE.md`: end-to-end publishing procedure for tellurium and for
  `chromium-telluride`.
- Popup tracking: every new page (`new_tab`, context tabs, `target=_blank`,
  `window.open`) is auto-attached frozen from the browser root, patched
  (stealth scripts, overrides) and only then resumed; popups appear in
  `browser.tabs`. `Browser.wait_for_tab(url)` waits for one.
- `Tab.close()` / `Tab.closed`; tabs closed by the page leave `browser.tabs`.
- `Tab.get(wait_until=...)` now honours `"commit"`, `"domcontentloaded"`,
  `"load"` and `"networkidle"` (via `Page.lifecycleEvent`, tied to the
  navigation's loader); unknown values raise `ValueError`.

### Changed

- Single cache layout shared by engine, CLI and installer:
  `~/.tellurium/chromium/<chromium-version>/chrome` (+ `MANIFEST.json`,
  `current` symlink). CLI previously looked in `chromium-patched-<v>/`.
  The legacy binary name `tellurium-chromium` is still accepted.
- CLI reads `binary_sha256[<platform>]` from `MANIFEST.json` (was flat `sha256`,
  which never matched the fork's manifest).
- `PatchedEngine` always passes `--fingerprint=<seed>` (random seed if none
  given: the fork requires it) and no longer emits `--fingerprint-timezone` /
  `--fingerprint-locale`, which no chromium-telluride patch implements.
- Update-check and release URLs point at `github.com/miczza/chromium-telluride`.
- Repo housekeeping: architecture specs migrated into `docs/superpowers/specs/architecture/`,
  build noise untracked, the one-off `diagnose_*` fingerprint scripts archived
  out of `examples/fingerprint_tests/`.

### Fixed

- A launch cancelled a second time while rolling back (or `asyncio.run`
  ending right after) skipped the remaining cleanup: the pipe, the proxy
  forwarder and the temporary profile were left behind. `Browser.close()` now
  runs every step, each bounded by a timeout, and re-raises the cancellation
  at the end.
- Every launch/close cycle left Chrome's shared-memory files and singleton
  socket dir (`.com.google.Chrome.*`, about 400 KB, RAM on tmpfs) in the
  system temp dir. Chrome now gets a private `TMPDIR`, removed on close
  (POSIX).
- Tellurium-managed Chrome for Testing installs were ranked by directory name,
  so `chrome-99…` beat `chrome-140…`; they are ranked by version now.
- `download_cft` extracted with `zipfile.extractall`, losing exec bits
  (`chrome_crashpad_handler`) and symlinks (macOS framework links); modes and
  links are kept now, and entries outside the install dir are refused. The
  download and extraction run off the event loop.
- Windows: the Chrome version (used to refuse extensions on branded Chrome
  137+) is read from the install layout; `chrome.exe --version` prints
  nothing there, so the check silently passed.
- Chrome's stdout and stderr went to pipes nobody read: once about 64 KiB of
  log piled up (failed TLS handshakes, `--enable-logging=stderr`) Chrome
  blocked and every CDP command hung. The output is now drained on a thread
  (or written to `chrome_log`).
- `Browser.launch()` is all-or-nothing: on failure or cancellation (e.g.
  `asyncio.wait_for` timing out) the Chrome process is reaped and the pipe,
  temporary profile and proxy forwarder are released. When Chrome exits during
  launch, `LaunchError` reports its exit code and last output (a profile
  already in use, a missing library) instead of `ConnectionError('Browser pipe
  closed')`.
- `Browser.close()` stops Chrome before closing its pipe (on Windows closing a
  pipe with a pending read can block), reaps it without blocking the event
  loop, and still releases everything when cancelled.
- The CDP pipe did not reach Chrome when the parent's pipe ends landed on fds
  3 or 4 (an embedder with few open fds): the child closed the end it had just
  set up.
- A crashed renderer (OOM, killed process) left its tab in `browser.tabs` and
  every command on it waiting forever. `Target.targetCrashed` now fails the
  tab's pending and future commands with `TargetCrashedError` (a
  `ConnectionError`, in `tellurium.cdp.types`) and drops the tab.
- The pipe transport re-scanned its whole receive buffer for the message
  terminator on every chunk, so one large reply (full-page screenshot, big
  response body) cost quadratic time with the event loop blocked: 64 MB took
  about 1.5 s. Only new bytes are scanned now.
- `PipePosixTransport.close()` left the read end of the CDP pipe open: one fd
  leaked per launch/close cycle.
- Elements went stale after any later query: every `select`/`xpath`/`find`
  refreshes the DOM agent (`DOM.getDocument`), voiding all earlier nodeIds,
  so `h1 = select("h1"); select("p"); h1.text()` raised "No node with given
  id". Elements are now addressed by their `objectId`, resolved as soon as
  they are found; `html()`, `attributes()`, `upload()`, `focus()` and the
  relative `select()`/`select_all()` no longer use nodeIds.
- CDP dispatch could hang every pending command: an event handler that raised
  killed the dispatch loop silently; a detached target left its commands
  waiting forever; a malformed message ended the loop without failing them.
  Handler errors are now logged, detached sessions fail their pending and
  future commands with `ConnectionError`, and any end of the loop fails all
  pending commands.
- `webrtc_ip="auto"` with `browser="patched"` passed the literal `auto` to
  `--fingerprint-webrtc-ip`, which the fork took as the IP to advertise. The
  resolved IP is passed now; `"disable"` leaves the flag out.
- `Tab.get()` ignored `wait_until` and timed out on same-document
  (`#fragment`) navigations; `Tab.title` was always `""`; `Tab.url` kept the
  requested URL after a redirect.
- `BrowserContext.new_tab()` applied no stealth or overrides and loaded the
  URL before any patching.
- `Tab.select()`/`wait_for()` raised instead of retrying when a navigation
  removed the node between the query and its resolution.
- CHANGELOG/README claimed 3 residual CreepJS lies on the patched binary; the
  2026-04-27 triage measured `totalLies = 0`.
- Accept-Language: `Emulation.setUserAgentOverride.acceptLanguage` leaked the
  raw q-value string into `navigator.languages` (`["en-US", "en;q=0.9"]`),
  produced a malformed header (`"en-US, en;q=0.9;q=0.9"`) and a window/worker
  mismatch — a value real Chrome never emits. Chrome now derives both from
  `--accept-lang=<profile languages>`: header `en-US,en;q=0.9`,
  `navigator.languages` `["en-US","en"]` in window and workers. Measured on
  Chrome 153; CreepJS gate re-run 8/8, lies 0.
- `Tab.xpath()`: dropped an unused root id, always calls
  `DOM.discardSearchResults`, uses `get_running_loop()` in callbacks, and
  removed a no-op `native_client_hints` branch.
- Stealth documentation in `README.md` described the pre-T7/T7.5 posture
  (extension-only delivery, WebGL spoofing, `toString` masking); realigned
  with the shipped engine.

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

- (closed in Unreleased) Auto-download tooling for the patched binary
  (`download-browser --browser patched`, `update-browser`,
  `verify-browser --reinstall`); F6 worker-scope masking — resolved by
  patching `hardwareConcurrency` only and deliberately *not* defining
  `navigator.webdriver` in workers; periodic baseline re-validation cadence —
  now the weekly `nightly-creepjs.yml` parity gate.
- T8 Honeypot + robots.txt detection (renamed from "T7" on 2026-09-15 to avoid
  colliding with the T7 runtime stealth layer)
- F7 dynamic same-origin iframe injection
- `_NATIVE_SHAPES` array refactor (T7.6 reviewer note)
- CreepJS bundle content hashing for drift detection (T7.6 reviewer note)
- Multi-OS CI matrix (macOS, Windows) — CI is Linux-only

### Notes

- CI workflow `.github/workflows/ci.yml` existed in draft state at v0.1 release
  time (no GitHub remote); activated in Unreleased
- Pre-migration history of C-series specs (chromium-telluride patches) reachable from `tellurium@ace0afa`
