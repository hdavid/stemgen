# StemGen — Makefile
# ─────────────────────────────────────────────────────────────────────────────
# Build/package split (mirrors the Track Kommander / Cath-Axis convention):
#   make venv       uv sync — create/refresh .venv (runtime + build deps)
#   make lock       uv lock — refresh uv.lock from pyproject.toml
#   make run        run the app from source
#   make test       run the unit tests
#   make build      Nuitka compile -> executable:
#                       macOS   -> dist/StemGen.app
#                       Windows -> dist/StemGenApp.dist/StemGenApp.exe
#   make package    wrap the executable into the platform distributable:
#                       macOS   -> dist/StemGen.dmg
#                       Windows -> dist/StemGenSetup-<ts>.msi (+ .sha256)
#   make deploy     macOS: build + install into /Applications
#   make clean      remove dist/, build/
#   make distclean  clean + remove .venv
#
# Cross-platform: macOS/Linux run native POSIX recipes. On Windows, GNU Make is
# invoked from cmd.exe / PowerShell where there are no POSIX tools (awk, sh, rm)
# on PATH, so every target delegates to make.ps1 — always runnable via
# powershell.exe. `make` works from cmd, PowerShell, or Git Bash on Windows;
# the behaviour is identical.
# ─────────────────────────────────────────────────────────────────────────────

APP_NAME       := StemGen
ENTRY          := src/StemGenApp.py
PYTHON_VERSION := 3.13
VENV           := .venv
DIST           := dist

.DEFAULT_GOAL := help
.PHONY: help venv lock run test build package dmg deploy clean distclean

ifeq ($(OS),Windows_NT)
# ══════════════════════════════ Windows ══════════════════════════════════════
# Thin dispatcher: hand each target to the PowerShell task runner. We avoid
# every POSIX construct here (no awk/sh/rm, no $(shell …)) because none of
# them exist when make is launched from a stock Windows shell. `OS` is set to
# "Windows_NT" by Windows itself, so this branch is also taken under Git Bash.
PS := powershell -NoProfile -ExecutionPolicy Bypass -File make.ps1

help:      ; @$(PS) help
venv:      ; @$(PS) venv
lock:      ; @$(PS) lock
run:       ; @$(PS) run
test:      ; @$(PS) test
build:     ; @$(PS) build
package:   ; @$(PS) package
clean:     ; @$(PS) clean
distclean: ; @$(PS) distclean

else
# ══════════════════════════════ macOS / Linux ════════════════════════════════

VENV_PY        := $(VENV)/bin/python

# Project-local env: pick up DEVELOPER_ID_APP / NOTARY_* from .env.local
# without touching the user's shell profile. The file is gitignored.
# Lines use plain ``KEY=value`` (Make syntax); `export` propagates them
# into the subshell used by `scripts/_build_app.sh`.
ifneq ($(wildcard .env.local),)
    include .env.local
    export
endif

# Resolve which `uv` to use. Prefer one already on PATH (Homebrew-installed,
# user-installed, etc.). If not, fall back to a project-local bootstrap that
# we install on first run via the stdlib venv + pip — that way ``make run``
# works on a fresh clone with only python3 on PATH.
UV_SYSTEM := $(shell command -v uv 2>/dev/null)
ifeq ($(UV_SYSTEM),)
    UV := .uv-bootstrap/bin/uv
else
    UV := $(UV_SYSTEM)
endif

BUNDLE         := $(DIST)/$(APP_NAME).app
DMG_OUT        := $(DIST)/$(APP_NAME).dmg
APP_INSTALL    := /Applications/$(APP_NAME).app
# Nuitka names the launcher binary after the entry script's stem.
ENTRY_STEM     := $(basename $(notdir $(ENTRY)))

help:
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ── Environment (uv-managed) ─────────────────────────────────────────────────

# Bootstrap target — creates .uv-bootstrap/ with uv installed, ONLY when
# the system doesn't have a uv on PATH. Idempotent: once .uv-bootstrap/bin/uv
# exists, this rule is a no-op.
.uv-bootstrap/bin/uv:
	@echo "→ uv not on PATH; bootstrapping into .uv-bootstrap/ (one-time)"
	@python3 -m venv .uv-bootstrap
	@.uv-bootstrap/bin/pip install --quiet uv
	@echo "  uv $$(.uv-bootstrap/bin/uv --version | awk '{print $$2}') installed"

venv: $(UV) ## uv sync — create/refresh .venv (runtime + build + dev deps)
	$(UV) sync --python $(PYTHON_VERSION) --extra build --extra dev

lock: $(UV) ## uv lock — refresh uv.lock
	$(UV) lock --python $(PYTHON_VERSION)

# Stamp file the build target depends on — uv sync re-runs only when
# pyproject.toml changes since the last sync.
$(VENV_PY): pyproject.toml
	@$(MAKE) --no-print-directory venv

# ── Run / test / build ───────────────────────────────────────────────────────
run: $(VENV_PY) ## run the app from source
	$(VENV_PY) $(ENTRY)

test: $(VENV_PY) ## run the unit tests
	$(VENV_PY) -m pytest

build: $(VENV_PY) ## Nuitka compile → dist/StemGen.app
	@APP_NAME="$(APP_NAME)" \
		ENTRY="$(ENTRY)" \
		VENV_PY="$(VENV_PY)" \
		DIST="$(DIST)" \
		./scripts/_build_app.sh

# ── Package ──────────────────────────────────────────────────────────────────
package: dmg ## package the .app for distribution (.dmg)

# The .sha256 sidecar mirrors what _package_windows.ps1 writes next to the
# MSI: same "<hash>  <filename>" shape, so a release carries a checksum for
# both platforms and `shasum -c` works from the download folder.
dmg: build ## wrap the .app into a .dmg installer (+ .sha256)
	@rm -f "$(DMG_OUT)" "$(DMG_OUT).sha256"
	$(VENV)/bin/dmgbuild -s scripts/dmg_settings.py \
		-D app="$(BUNDLE)" "$(APP_NAME)" "$(DMG_OUT)"
	@cd "$(DIST)" && shasum -a 256 "$(APP_NAME).dmg" > "$(APP_NAME).dmg.sha256"
	@echo "→ $(DMG_OUT)"
	@echo "→ $(DMG_OUT).sha256"

# ── Deploy ───────────────────────────────────────────────────────────────────

# Install the freshly built bundle into /Applications, replacing any previous
# copy (running from a stale install is a recurring bug source — fixes exist
# in the repo but not in the installed app).
deploy: build ## build + install into /Applications (replaces existing copy)
	@echo "→ deploying → $(APP_INSTALL)"
	@osascript -e 'tell application "$(APP_NAME)" to quit' >/dev/null 2>&1 || true
	@for i in $$(seq 1 40); do pgrep -xq $(ENTRY_STEM) || break; sleep 0.5; done; \
		if pgrep -xq $(ENTRY_STEM); then echo "✗ $(APP_NAME) is still running after 20 s — quit it and retry" >&2; exit 1; fi
	rm -rf "$(APP_INSTALL)"
	ditto "$(BUNDLE)" "$(APP_INSTALL)"
	@echo "✓ installed $(APP_INSTALL) ($$(date '+%H:%M:%S'))"

# ── Cleanup ──────────────────────────────────────────────────────────────────
clean: ## remove build artefacts
	rm -rf build $(DIST) "$(DIST).lock" dist-nuitka

distclean: clean ## clean + remove venv
	rm -rf $(VENV) .uv-bootstrap

endif
