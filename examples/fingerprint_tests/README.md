# Fingerprint tests

Manual detection/fingerprint runners for tellurium and for the patched
`chromium-telluride` binary. None of these are part of `make test`: they need
a display, and most of them need network access to third-party detection sites.

Run them with the project venv from the repo root, e.g.

```bash
DISPLAY=:0 .venv/bin/python examples/fingerprint_tests/quick_fingerprint_test.py --seed 42069
```

---

## Runners

### `run_all_tests.py` — full suite (recommended)

Quick local collection, stability check (same seed → same fingerprint),
variation check (different seed → different fingerprint), then the live sites.

```bash
python run_all_tests.py                    # everything
python run_all_tests.py --quick-only       # skip the external sites
python run_all_tests.py --chrome /path/to/chrome
```

Writes `test_report.json` and screenshots into `screenshots/`.

### `quick_fingerprint_test.py` — fast development loop

Collects fingerprint data straight from the browser, no external sites.

```bash
python quick_fingerprint_test.py --seed 42069
python quick_fingerprint_test.py --seed 42069 --compare 99999   # seed A vs seed B
python quick_fingerprint_test.py --seed 42069 --stability       # same seed, repeated
```

### `comparative_test.py` — tellurium vs the other frameworks

Runs the same detection suite (bot.sannysoft.com, CreepJS, BrowserLeaks
Canvas/WebGL, browserscan.net — 8 checks) across tellurium, selenium,
playwright, playwright-stealth, nodriver, undetected-chromedriver,
DrissionPage and pydoll, so tellurium's score is always read against a
baseline rather than in isolation.

```bash
# all frameworks on stock Chrome
DISPLAY=:0 .venv/bin/python comparative_test.py

# only tellurium, on the patched binary, with a fixed seed
DISPLAY=:0 TELLURIUM_FP_SEED=42069 .venv/bin/python comparative_test.py \
    --frameworks tellurium \
    --chrome-path /path/to/chromium-telluride/chrome

# a subset
DISPLAY=:0 .venv/bin/python comparative_test.py \
    --frameworks nodriver,tellurium,playwright_stealth
```

Writes `comparative_results.json`. The competitor frameworks are **not**
tellurium dependencies — install the ones you want to compare against first.

### `test_stock_runtime_parity.py` — the CreepJS gate

The only pytest file here. Asserts that tellurium on **stock** Chrome with
`stealth=True` matches the nodriver baseline on the comparative suite. It
shells out to `comparative_test.py` and reads `comparative_results.json`.

```bash
make parity                       # from the repo root
STOCK_CHROME=/usr/bin/google-chrome-stable .venv/bin/pytest \
    examples/fingerprint_tests/test_stock_runtime_parity.py -q
```

Deliberately excluded from `ci.yml` (it hits third-party sites); it runs
weekly in `.github/workflows/nightly-creepjs.yml` and must be green before a
release — see `RELEASING.md`.

### `test_canvas_geometry.py` — patched binary, canvas seed determinism

Checks that the Skia antialiasing perturbation (C4.6) changes the canvas hash
across seeds even for geometry-only drawing (no `fillText`/`strokeText`).
Requires a `chromium-telluride` build.

### `test_fingerprint_sites.py` — detailed per-site report

FingerprintJS demo, CreepJS, BrowserLeaks Canvas, BrowserLeaks WebGL.

```bash
python test_fingerprint_sites.py --seed 42069
python test_fingerprint_sites.py --seeds 42069,99999,12345
```

### `diagnose_cdp_detection.py` — CDP detection vectors

The one diagnostic kept in tree. Probes three known CDP detection techniques
and then reads the Smart Signals / Suspect Score off `fingerprint.com/demo`.

```bash
python diagnose_cdp_detection.py [--chrome PATH]
```

---

## Archived scripts

The ~45 single-purpose `diagnose_*.py` scripts written while chasing
individual CreepJS signals during T7/T7.5/T7.6 (`diagnose_headless_33.py`,
`diagnose_capture_lies.py`, `diagnose_chain_cycle.py`, …) were archived on
2026-09-15 into `.archive/fingerprint-debug-2026-09-15.tar.gz` at the repo
root. They were one-off probes tied to signals that are now closed, not
maintained tooling. Extract the tarball if you need one back:

```bash
tar xzf .archive/fingerprint-debug-2026-09-15.tar.gz \
    examples/fingerprint_tests/diagnose_headless_33.py
```

---

## Stored results

| File | What it is |
|---|---|
| `comparative_results.json` | Latest comparative run — the numbers quoted in the README and in the parity gate |
| `results_stock_chrome.json` | Raw 8-framework run on stock Chrome |
| `test_report.json` | Output of `run_all_tests.py` |
| `CREEPJS_BASELINE.txt` | Reference CreepJS output |
| `COMPARATIVE_REPORT.md` | Written analysis of the 2026-04-24 comparative run (**historical**: the residual CreepJS `headless 33%` / `stealth 60%` it discusses were closed by T7.5/T7.6; current scores are in `comparative_results.json`) |
| `screenshots/` | Per-site screenshots from the runners |

Current stock-Chrome scores (`comparative_results.json`): CreepJS `lies=0`,
`headless=0%`, `stealth=0%`, `like_headless=38%` (environmental), sannysoft 31
passed / 0 failed, browserscan no bot, comparative suite **8/8**.

## Requirements

- A display (`DISPLAY=:0`, or `xvfb-run -a` — but WebGPU/GPU-dependent checks
  need a real one)
- Network access for everything except `--quick-only`
- For the patched-binary runners: a `chromium-telluride` build, either
  installed via `tellurium download-browser --browser patched` or passed with
  `--chrome` / `--chrome-path`
