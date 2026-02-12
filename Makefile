.PHONY: lint typecheck test docs check fix format coverage coverage-html \
       docker-build docker-test docker-stress docker-test-client docker-test-bbmd \
       docker-test-router docker-clean

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

# ---------------------------------------------------------------------------
# Docker integration tests
# ---------------------------------------------------------------------------

COMPOSE := docker compose -f docker/docker-compose.yml

docker-build:
	$(COMPOSE) build

docker-test-client: docker-build
	$(COMPOSE) --profile client-server up --abort-on-container-exit --exit-code-from test-client-server
	$(COMPOSE) --profile client-server down -v

docker-test-bbmd: docker-build
	$(COMPOSE) --profile bbmd up --abort-on-container-exit --exit-code-from test-bbmd
	$(COMPOSE) --profile bbmd down -v

docker-test-router: docker-build
	$(COMPOSE) --profile router up --abort-on-container-exit --exit-code-from test-router
	$(COMPOSE) --profile router down -v

docker-test-stress: docker-build
	$(COMPOSE) --profile stress up --abort-on-container-exit --exit-code-from test-stress
	$(COMPOSE) --profile stress down -v

docker-test: docker-build
	$(MAKE) docker-test-client
	$(MAKE) docker-test-bbmd
	$(MAKE) docker-test-router
	$(MAKE) docker-test-stress

docker-stress: docker-build
	$(COMPOSE) --profile stress-runner up --abort-on-container-exit --exit-code-from stress-runner
	$(COMPOSE) --profile stress-runner down -v

docker-clean:
	$(COMPOSE) --profile all down -v --rmi local
	$(COMPOSE) --profile stress-runner down -v --rmi local
