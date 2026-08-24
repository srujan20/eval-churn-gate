PY ?= python3

.PHONY: help install lint test experiments receipts verify evidence pdf sweep clean

help:
	@echo "install      editable install with the dev extra"
	@echo "lint         ruff check and format check"
	@echo "test         pytest with coverage, writing reports/"
	@echo "experiments  re-run all five, writing docs/experiments/*.json"
	@echo "receipts     re-measure every figure, then check it against the documents"
	@echo "verify       lint, test, receipts. The one command the README promises."
	@echo "evidence     diagram, screenshots, demo video and the README image check."
	@echo "             Needs the evidence extra: pip install -e '.[evidence]'"
	@echo "pdf          lay out the defense guide for offline reading"

install:
	$(PY) -m pip install -e ".[dev]"

lint:
	$(PY) -m ruff check src tests tools experiments
	$(PY) -m ruff format --check src tests tools experiments

test:
	$(PY) -m pytest -q --junitxml=reports/junit.xml \
		--cov=churngate --cov-report=json:reports/coverage.json \
		--cov-report=xml:reports/coverage.xml --cov-report=term-missing

experiments:
	$(PY) experiments/exp01_the_gate_graded_against_nothing.py
	$(PY) experiments/exp02_the_regression_the_aggregate_cannot_see.py
	$(PY) experiments/exp03_what_the_eval_set_can_resolve.py
	$(PY) experiments/exp04_the_aggregate_carries_no_churn_information.py
	$(PY) experiments/exp05_what_the_combined_gate_costs.py

# Reads the reports that `make test` produced rather than running pytest again,
# so a red test surfaces as a failing test target and not as a traceback from a
# metrics script.
receipts:
	$(PY) tools/collect_metrics.py --skip-tests
	$(PY) tools/check_numbers.py --strict

verify: lint test receipts

evidence:
	$(PY) tools/render_diagram.py
	$(PY) tools/capture_screenshots.py
	$(PY) tools/record_demo.py
	$(PY) tools/check_readme.py README.md

pdf:
	$(PY) tools/build_pdf.py docs/defense-guide.md

sweep:
	$(PY) -m churngate sweep --html reports/sweep.html --json reports/sweep.json

clean:
	rm -rf reports .cache .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
