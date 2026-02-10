.PHONY: lint typecheck test docs check fix format coverage coverage-html

lint:
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/

typecheck:
	uv run mypy src/

test:
	uv run pytest --tb=short -q

docs:
	uv run sphinx-build -W -b html docs docs/_build/html

check: lint typecheck test docs

fix:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

format:
	uv run ruff format src/ tests/

coverage:
	uv run pytest --cov --cov-report=term-missing

coverage-html:
	uv run pytest --cov --cov-report=html
