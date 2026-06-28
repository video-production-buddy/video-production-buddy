PYTHON ?= python3

.PHONY: setup install install-dev install-gpu install-remotion test test-contracts test-integration test-qa genui-verify genui-evidence-check lint clean preflight preflight-full demo demo-list hyperframes-doctor hyperframes-warm

DEFAULT_TEST_MARKERS := not integration and not qa and not browser and not ffmpeg and not node and not hyperframes and not slow and not live_provider

# ---- One-command setup ----

setup:
	@echo "==> Installing Python dependencies..."
	$(PYTHON) -m pip install -r requirements.txt
	@echo ""
	@echo "==> Installing Remotion composer..."
	$(MAKE) install-remotion
	@echo ""
	@echo "==> Installing free offline TTS (Piper)..."
	$(PYTHON) -B -m lib.setup_runtime install-piper
	@echo ""
	@echo "==> Installing HyperFrames runtime (cache-warm via npx)..."
	@echo "    Pulls the 'hyperframes' npm package into the local npx cache so the"
	@echo "    first render doesn't pay a 30-60s cold-fetch penalty. ~20MB of disk."
	@$(PYTHON) -B -m lib.setup_runtime warm-hyperframes
	@$(PYTHON) -B -m lib.setup_runtime check-hyperframes
	@echo ""
	$(PYTHON) -B -m lib.setup_runtime ensure-env
	@echo ""
	@echo "Done! Open this project in your AI coding assistant and start creating."
	@echo "  Optional: add API keys to .env to unlock cloud providers."
	@echo "  Optional: run 'make install-gpu' if you have an NVIDIA GPU."
	@echo "  Optional: run 'make hyperframes-doctor' to fully validate the HyperFrames runtime."
	@echo "  Optional: run 'make hyperframes-warm' anytime to refresh the npx cache to the latest hyperframes version."

# ---- Individual installs ----

install:
	$(PYTHON) -m pip install -r requirements.txt

install-dev:
	$(PYTHON) -m pip install -r requirements-dev.txt

install-gpu:
	$(PYTHON) -m pip install -r requirements-gpu.txt
	$(PYTHON) -m pip install diffusers transformers accelerate

install-remotion:
	$(PYTHON) -B -m lib.setup_runtime install-remotion

# ---- Testing ----

test:
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -m "$(DEFAULT_TEST_MARKERS)" tests/ -v

test-contracts:
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -m "$(DEFAULT_TEST_MARKERS)" tests/contracts/ -v

test-integration:
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -m "integration" tests/ -v

test-qa:
	VPB_ALLOW_BROWSER_OPEN=0 PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m pytest -p no:cacheprovider -m "qa" tests/ -v

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

# ---- Utilities ----

preflight:
	$(PYTHON) -B -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"

preflight-full:
	$(PYTHON) -B -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu(), indent=2))"

hyperframes-doctor:
	@echo "==> Probing HyperFrames runtime (node/ffmpeg/npx + hyperframes doctor)..."
	$(PYTHON) -B -c "from tools.video.hyperframes_compose import HyperFramesCompose; import json; r=HyperFramesCompose().execute({'operation':'doctor'}); print(json.dumps(r.data, indent=2)); print('OK' if r.success else f'FAIL: {r.error}'); raise SystemExit(0 if r.success else 1)"

hyperframes-warm:
	@echo "==> Refreshing the HyperFrames npx cache to latest..."
	@echo "    Uses --prefer-online so npx picks up new releases since your last run."
	npx --yes --prefer-online hyperframes --version
	@echo "==> Cache warm complete."

demo:
	@echo "==> Rendering zero-key demo videos (no API keys needed)..."
	@echo "    These use only Remotion components — animated charts, text, data viz."
	@echo ""
	$(PYTHON) -B render_demo.py

demo-list:
	@$(PYTHON) -B render_demo.py --list

lint:
	@set -e; \
	cache_dir=$$(mktemp -d); \
	trap 'rm -rf "$$cache_dir"' EXIT; \
	PYTHONPYCACHEPREFIX="$$cache_dir" $(PYTHON) -m py_compile tools/base_tool.py; \
	PYTHONPYCACHEPREFIX="$$cache_dir" $(PYTHON) -m py_compile tools/tool_registry.py; \
	PYTHONPYCACHEPREFIX="$$cache_dir" $(PYTHON) -m py_compile tools/cost_tracker.py; \
	PYTHONPYCACHEPREFIX="$$cache_dir" $(PYTHON) -m py_compile tools/output_paths.py; \
	PYTHONPYCACHEPREFIX="$$cache_dir" $(PYTHON) -m py_compile tools/status_utils.py; \
	PYTHONPYCACHEPREFIX="$$cache_dir" $(PYTHON) -m py_compile tools/analysis/composition_validator.py

clean:
	find . \( -path './.git' -o -path './node_modules' -o -path './remotion-composer/node_modules' -o -path './genui-renderer/node_modules' -o -path './projects' \) -prune -o \( -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -prune -exec rm -rf {} + \) -o \( -type f -name '*.pyc' -exec rm -f {} + \)
