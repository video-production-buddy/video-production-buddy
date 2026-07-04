PYTHON_VERSION ?= 3.10
VENV_DIR ?= .venv
BASE_PYTHON ?= $(shell command -v python$(PYTHON_VERSION) 2>/dev/null || command -v python3 2>/dev/null || command -v python 2>/dev/null)
RUN_PYTHON = $(shell for dir in "$$VIRTUAL_ENV" "$$CONDA_PREFIX" "$(VENV_DIR)"; do if [ -n "$$dir" ] && [ -x "$$dir/bin/python" ]; then printf "%s/bin/python" "$$dir"; exit 0; elif [ -n "$$dir" ] && [ -x "$$dir/Scripts/python.exe" ]; then printf "%s/Scripts/python.exe" "$$dir"; exit 0; fi; done; if [ "$(OS)" = "Windows_NT" ]; then printf "%s/Scripts/python.exe" "$(VENV_DIR)"; else printf "%s/bin/python" "$(VENV_DIR)"; fi)
PYTHON ?= $(RUN_PYTHON)
PIP = $(PYTHON) -m pip

.DEFAULT_GOAL := setup

.PHONY: setup install install-dev install-gpu test test-contracts test-integration test-qa genui-verify genui-evidence-check lint clean preflight preflight-full models-list models-check models-configure demo demo-list hyperframes-doctor hyperframes-warm venv ensure-venv

DEFAULT_TEST_MARKERS := not integration and not qa and not browser and not ffmpeg and not node and not hyperframes and not slow and not live_provider

# ---- Virtual environment ----

ensure-venv:
	@if [ -n "$$VIRTUAL_ENV" ] && { [ -x "$$VIRTUAL_ENV/bin/python" ] || [ -x "$$VIRTUAL_ENV/Scripts/python.exe" ]; }; then \
		echo "==> Using active virtual environment: $$VIRTUAL_ENV"; \
	elif [ -n "$$CONDA_PREFIX" ] && { [ -x "$$CONDA_PREFIX/bin/python" ] || [ -x "$$CONDA_PREFIX/Scripts/python.exe" ]; }; then \
		echo "==> Using active conda environment: $$CONDA_PREFIX"; \
	elif [ -x "$(VENV_DIR)/bin/python" ] || [ -x "$(VENV_DIR)/Scripts/python.exe" ]; then \
		echo "==> Using existing virtual environment: $(VENV_DIR)"; \
	elif command -v uv >/dev/null 2>&1; then \
		echo "==> Creating virtual environment with uv (Python $(PYTHON_VERSION)+): $(VENV_DIR)"; \
		uv venv --python $(PYTHON_VERSION) "$(VENV_DIR)"; \
	else \
		if [ -z "$(BASE_PYTHON)" ]; then \
			echo "ERROR: Python $(PYTHON_VERSION)+ is required, but no python executable was found."; \
			exit 1; \
		fi; \
		"$(BASE_PYTHON)" -c "import sys; required=tuple(map(int, '$(PYTHON_VERSION)'.split('.')[:2])); raise SystemExit(0 if sys.version_info[:2] >= required else 1)" || { \
			echo "ERROR: Video Production Buddy requires Python $(PYTHON_VERSION)+."; \
			echo "Install uv or Python $(PYTHON_VERSION)+, then run make again."; \
			exit 1; \
		}; \
		echo "==> Creating virtual environment with Python venv: $(VENV_DIR)"; \
		"$(BASE_PYTHON)" -m venv "$(VENV_DIR)" || { \
			echo "ERROR: Could not create $(VENV_DIR). Install uv or ensure python venv support is available."; \
			exit 1; \
		}; \
	fi
	@$(RUN_PYTHON) -c "import sys; required=tuple(map(int, '$(PYTHON_VERSION)'.split('.')[:2])); raise SystemExit(0 if sys.version_info[:2] >= required else 1)" || { \
		echo "ERROR: Video Production Buddy requires Python $(PYTHON_VERSION)+."; \
		echo "Current interpreter is $$($(RUN_PYTHON) -c 'import sys; print(\".\".join(map(str, sys.version_info[:3])))' 2>/dev/null || echo unavailable): $(RUN_PYTHON)"; \
		echo "Activate a compatible environment or remove it so make can create $(VENV_DIR)."; \
		exit 1; \
	}
	@$(RUN_PYTHON) -m pip --version >/dev/null 2>&1 || $(RUN_PYTHON) -m ensurepip --upgrade >/dev/null

venv: ensure-venv
	@echo "==> Virtual environment ready."
	@echo "    Python: $(RUN_PYTHON)"
	@if [ -z "$$VIRTUAL_ENV" ] && [ -z "$$CONDA_PREFIX" ]; then if [ "$(OS)" = "Windows_NT" ]; then echo "    Activate with: $(VENV_DIR)\\Scripts\\Activate.ps1"; else echo "    Activate with: source $(VENV_DIR)/bin/activate"; fi; fi

# ---- One-command setup ----

setup: ensure-venv
	@echo "==> Installing Python dependencies..."
	$(PIP) install -r requirements.txt
	@echo ""
	@echo "==> Installing Remotion composer..."
	$(MAKE) install-remotion
	@echo ""
	@echo "==> Installing free offline TTS (Piper)..."
	$(PIP) install piper-tts || echo "  [skip] piper-tts install failed — TTS will use cloud providers instead"
	@echo ""
	@echo "==> Installing HyperFrames runtime (cache-warm via npx)..."
	@echo "    Pulls the 'hyperframes' npm package into the local npx cache so the"
	@echo "    first render doesn't pay a 30-60s cold-fetch penalty. ~20MB of disk."
	@npx --yes hyperframes --version >/dev/null 2>&1 && echo "    HyperFrames CLI cached (npx)" || echo "  [skip] HyperFrames cache-warm failed — offline or npm unavailable; first render will fetch on demand"
	@$(RUN_PYTHON) -c "from tools.video.hyperframes_compose import HyperFramesCompose; HyperFramesCompose._npm_resolve_cache=None; c=HyperFramesCompose()._runtime_check(); print(f'    HyperFrames runtime_available={c[\"runtime_available\"]}, npm={c.get(\"npm_package_version\") or c.get(\"npm_resolve_error\")}'); [print(f'    note: {r}') for r in c['reasons']]" || echo "  [skip] HyperFrames check failed — runtime can be set up later"
	@echo ""
	$(RUN_PYTHON) -c "import shutil, os; e=os.path.exists('.env'); shutil.copy('.env.example','.env') if not e else None; print('==> Created .env from .env.example — add your API keys there.' if not e else '==> .env already exists — skipping.')"
	@echo ""
	@echo "Done! Open this project in your AI coding assistant and start creating."
	@echo "  Optional: add API keys to .env to unlock cloud providers."
	@echo "  Optional: run 'make install-gpu' if you have an NVIDIA GPU."
	@echo "  Optional: run 'make hyperframes-doctor' to fully validate the HyperFrames runtime."
	@echo "  Optional: run 'make hyperframes-warm' anytime to refresh the npx cache to the latest hyperframes version."

# ---- Individual installs ----

install: ensure-venv
	$(PIP) install -r requirements.txt

install-dev: ensure-venv
	$(PIP) install -r requirements-dev.txt

install-gpu: ensure-venv
	$(PIP) install -r requirements-gpu.txt
	$(PIP) install diffusers transformers accelerate

install-remotion:
	$(PYTHON) -B -m lib.setup_runtime install-remotion

# ---- Testing ----

test: ensure-venv
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -m "$(DEFAULT_TEST_MARKERS)" tests/ -v

test-contracts: ensure-venv
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -m "$(DEFAULT_TEST_MARKERS)" tests/contracts/ -v

test-integration: ensure-venv
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -m "integration" tests/ -v

test-qa: ensure-venv
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -m "qa" tests/ -v

# ---- Utilities ----

preflight: ensure-venv
	$(PYTHON) -B -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"

preflight-full: ensure-venv
	$(PYTHON) -B -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu(), indent=2))"

models-list: ensure-venv
	$(PYTHON) -B -m lib.model_settings_wizard --list $(if $(CAPABILITY),--capability $(CAPABILITY),)

models-check: ensure-venv
	$(PYTHON) -B -m lib.model_settings_wizard --check $(if $(ENV_FILE),--env $(ENV_FILE),)

models-configure: ensure-venv
	@if [ -z "$(ENV_FILE)" ]; then \
		echo "usage: make models-configure ENV_FILE=.env CAPABILITY=video_generation [PRESET=fast] [DRY_RUN=1]"; \
		exit 2; \
	fi
	$(PYTHON) -B -m lib.model_settings_wizard --env $(ENV_FILE) $(if $(CAPABILITY),--capability $(CAPABILITY),) $(if $(PRESET),--preset $(PRESET),) $(if $(PROVIDER),--provider $(PROVIDER),) $(if $(MODEL),--model $(MODEL),) $(if $(DRY_RUN),--dry-run,) $(if $(YES),--yes,)

genui-verify:
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -q tests/contracts/test_genui_session_contract.py tests/contracts/test_genui_dynamic_interaction.py tests/contracts/test_genui_interaction_contract.py tests/contracts/test_genui_surface_contract.py
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -q tests/contracts/test_genui_session_hardening.py
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -q tests/contracts/test_genui_product_contract.py
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -m "browser" -q tests/integration/test_genui_browser_smoke.py
	VPB_ALLOW_BROWSER_OPEN=0 pnpm --dir genui-renderer test
	pnpm --dir genui-renderer typecheck
	@before=$$(mktemp); after=$$(mktemp); \
		status=0; \
		git diff -- lib/genui/static/renderer > $$before; \
		pnpm --dir genui-renderer build; \
		git diff -- lib/genui/static/renderer > $$after; \
		if ! cmp -s $$before $$after; then \
			echo "genui renderer static bundle is stale; rerun pnpm --dir genui-renderer build and include lib/genui/static/renderer"; \
			git diff --exit-code -- lib/genui/static/renderer || status=$$?; \
		fi; \
		rm -f $$before $$after; \
		exit $$status

genui-evidence-check:
	@project="$(PROJECT)"; pipeline="$(PIPELINE)"; stage="$(STAGE)"; \
		pipeline="$${pipeline:-ad-video}"; \
		stage="$${stage:-assets}"; \
		if [ -z "$$project" ]; then \
			echo "usage: make genui-evidence-check PROJECT=projects/<project-id> [PIPELINE=ad-video] [STAGE=assets]"; \
			exit 2; \
		fi; \
		PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m tools.validation.genui_evidence_check "$$project" "$$pipeline" "$$stage"

hyperframes-doctor: ensure-venv
	@echo "==> Probing HyperFrames runtime (node/ffmpeg/npx + hyperframes doctor)..."
	$(RUN_PYTHON) -c "from tools.video.hyperframes_compose import HyperFramesCompose; r=HyperFramesCompose().execute({'operation':'doctor'}); import json; print(json.dumps(r.data, indent=2)); print('OK' if r.success else f'FAIL: {r.error}')"

hyperframes-warm:
	@echo "==> Refreshing the HyperFrames npx cache to latest..."
	@echo "    Uses --prefer-online so npx picks up new releases since your last run."
	npx --yes --prefer-online hyperframes --version
	@echo "==> Cache warm complete."

demo: ensure-venv
	@echo "==> Rendering zero-key demo videos (no API keys needed)..."
	@echo "    These use only Remotion components — animated charts, text, data viz."
	@echo ""
	$(RUN_PYTHON) render_demo.py

demo-list: ensure-venv
	$(RUN_PYTHON) render_demo.py --list

lint: ensure-venv
	$(RUN_PYTHON) -m py_compile tools/base_tool.py
	$(RUN_PYTHON) -m py_compile tools/tool_registry.py
	$(RUN_PYTHON) -m py_compile tools/cost_tracker.py
	$(RUN_PYTHON) -m py_compile tools/analysis/composition_validator.py

clean:
	$(BASE_PYTHON) -c "import pathlib, shutil; excluded=[pathlib.Path('$(VENV_DIR)'), pathlib.Path('venv')]; skip=lambda p: any(p == root or root in p.parents for root in excluded); roots=[p for p in pathlib.Path('.').rglob('__pycache__') if not skip(p)]; [shutil.rmtree(p) for p in roots]; files=[p for p in pathlib.Path('.').rglob('*.pyc') if not skip(p)]; [p.unlink() for p in files]"
