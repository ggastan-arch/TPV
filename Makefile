# TPV Bizkaitropik - comandos de desarrollo
# En Windows usar Git Bash o `make` de GnuWin/choco. PYTHON se puede sobreescribir:
#   make test PYTHON=.venv/Scripts/python

PYTHON ?= python
ALEMBIC ?= $(PYTHON) -m alembic
PYTEST  ?= $(PYTHON) -m pytest
UVICORN ?= $(PYTHON) -m uvicorn
HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: dev test migrate seed revision arch

dev:            ## servidor local con recarga (make dev PORT=8123 si el 8000 esta ocupado)
	$(UVICORN) app.main:app --reload --host $(HOST) --port $(PORT)

arch:           ## verifica la regla de dependencias hexagonal (import-linter)
	lint-imports

test:           ## pytest (invariantes fiscales, huella, redondeo, concurrencia)
	$(PYTEST)

migrate:        ## alembic upgrade head
	$(ALEMBIC) upgrade head

seed:           ## datos de ejemplo (familias/articulos acuariofilia)
	$(PYTHON) -m app.seed

revision:       ## nueva migracion:  make revision m="mensaje"
	$(ALEMBIC) revision -m "$(m)"
