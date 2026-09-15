# tellurium — developer shortcuts.
# Mirrors what .github/workflows/ci.yml runs, so `make test lint` locally
# approximates a green CI run.

PY      ?= .venv/bin/python
PYTEST  ?= .venv/bin/pytest
RUFF    ?= uvx ruff
PARITY  := examples/fingerprint_tests/test_stock_runtime_parity.py

# tests/stealth needs an X display. Use the running one if present, else Xvfb.
XVFB := $(if $(DISPLAY),,xvfb-run -a)

.PHONY: help test test-unit test-integration test-stealth lint fmt build parity clean

help: ## Show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

test: test-unit test-integration test-stealth ## Run the full local suite

test-unit: ## Unit tests (fast, offline, no browser)
	$(PYTEST) tests/unit -q

test-integration: ## Integration tests (headless Chrome + local HTTP servers, ~47s)
	$(XVFB) $(PYTEST) tests/integration -q

test-stealth: ## Stealth tests (offline, needs a DISPLAY, ~15s)
	$(XVFB) $(PYTEST) tests/stealth -q

lint: ## ruff check + ruff format --check (same gate as CI)
	$(RUFF) check .
	$(RUFF) format --check .

fmt: ## Autofix: ruff check --fix + ruff format
	$(RUFF) check --fix .
	$(RUFF) format .

build: ## Build sdist + wheel into dist/ and validate metadata
	rm -rf dist
	uv build
	uvx twine check --strict dist/*

parity: ## CreepJS stock-runtime parity gate (NEEDS NETWORK, not part of CI)
	$(XVFB) $(PYTEST) $(PARITY) -q

clean: ## Remove build + cache artifacts
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
