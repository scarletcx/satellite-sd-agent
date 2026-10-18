VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

.PHONY: install install-deps run test test-unit test-api check template seed corpus-fetch demo-adv snapshot cost-report reference

install: install-deps
	python3 -m venv $(VENV) 2>/dev/null || true

install-deps:
	python3 -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q fastapi "uvicorn[standard]" "pydantic>=2.7" "sqlalchemy>=2.0.36" "docxtpl>=0.17" "pymupdf>=1.24" "python-multipart>=0.0.9" "mammoth>=1.8" "skyfield>=1.49" "sqlite-vec>=0.1.6" "langgraph>=0.2" "pytest>=8.0" "httpx>=0.27" "openpyxl>=3.1"

template:
	$(PY) scripts/build_template.py

seed:
	$(PY) scripts/seed.py

corpus-fetch:
	$(PY) scripts/fetch_corpus.py

demo-adv:
	$(PY) scripts/demo_adv.py

snapshot:
	$(PY) scripts/snapshot.py $(TASK)

cost-report:
	$(PY) scripts/cost_report.py $(TASK)

reference:
	$(PY) scripts/build_reference.py

run:
	$(VENV)/bin/uvicorn app.main:app --reload --port 8000

test:
	$(PY) -m pytest

test-unit:
	$(PY) -m pytest tests/test_budgets.py

test-api:
	$(PY) -m pytest tests/test_pipeline.py tests/test_api_smoke.py

check:
	curl -s http://127.0.0.1:8000/api/v1/healthz | $(PY) -m json.tool
