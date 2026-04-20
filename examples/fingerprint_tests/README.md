# Fingerprint Tests for chromium-telluride

Test scripts per verificare le patch Tier 1 di chromium-telluride.

## Scripts

### `run_all_tests.py` (Raccomandato)

Suite completa di test:

```bash
# Test completo (quick + live sites)
python run_all_tests.py

# Solo test rapidi (senza siti esterni)
python run_all_tests.py --quick-only

# Con Chrome custom
python run_all_tests.py --chrome /path/to/chrome
```

**Output:**
- `test_report.json` — Report completo
- `screenshots/` — Screenshot dei siti di fingerprinting

### `quick_fingerprint_test.py`

Test rapido per sviluppo:

```bash
# Singolo seed
python quick_fingerprint_test.py --seed 42069

# Confronto tra seed
python quick_fingerprint_test.py --seed 42069 --compare 99999

# Test stabilità
python quick_fingerprint_test.py --seed 42069 --stability
```

### `test_fingerprint_sites.py`

Test dettagliato sui siti di fingerprinting:

```bash
# Test singolo seed
python test_fingerprint_sites.py --seed 42069

# Confronto multipli seed
python test_fingerprint_sites.py --seeds 42069,99999,12345
```

## Siti Testati

| Sito | Cosa verifica |
|------|---------------|
| fingerprintjs.github.io | Canvas, Audio, WebGL hash |
| abrahamjuliot.github.io/creepjs | Trust score, Lies detection |
| browserleaks.com/canvas | Canvas hash stability |
| browserleaks.com/webgl | WebGL/WebGPU info |

## Risultati Attesi

### Stabilità (stesso seed)
- Canvas hash identico tra run
- Audio fingerprint identico
- Text metrics identici
- Client rects identici

### Variazione (seed diversi)
- Canvas hash diverso
- Audio fingerprint diverso
- Text metrics diversi (differenza minima ma presente)

### CreepJS
- Trust Score ≥ 70%
- Lies Detected ≤ 2

## Requisiti

- chromium-telluride build (`/home/miczza/PycharmProjects/chromium-telluride/src/out/Release/chrome`)
- Display disponibile (non headless per WebGPU)
- tellurium installato
