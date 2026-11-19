.PHONY: install accept clean

install:
	python -m pip install -e ".[dev]"

accept:
	python -m pytest -q tests/

clean:
	rm -rf .pytest_cache build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
