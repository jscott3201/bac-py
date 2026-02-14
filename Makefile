.PHONY: lint typecheck test docs check fix format coverage coverage-html \
       docker-build docker-test docker-stress docker-test-client docker-test-bbmd \
       docker-test-router docker-test-device-mgmt docker-test-cov-advanced \
       docker-test-events docker-test-sc docker-test-sc-stress docker-sc-stress \
       docker-test-router-stress docker-router-stress \
       docker-test-bbmd-stress docker-bbmd-stress \
       docker-demo docker-demo-auto docker-clean

lint:
	uv run ruff check src/ tests/ docker/ examples/
	uv run ruff format --check src/ tests/ docker/ examples/

typecheck:
	uv run mypy src/ examples/ docker/

test:
	uv run pytest --tb=short -q

docs:
	uv run sphinx-build -W -b html docs docs/_build/html

check: lint typecheck test docs

fix:
	uv run ruff check --fix src/ tests/ docker/ examples/
	uv run ruff format src/ tests/ docker/ examples/

format:
	uv run ruff format src/ tests/ docker/ examples/

coverage:
	uv run pytest --cov --cov-report=term-missing

coverage-html:
	uv run pytest --cov --cov-report=html

# ---------------------------------------------------------------------------
# Docker integration tests
# ---------------------------------------------------------------------------

COMPOSE := docker compose -f docker/docker-compose.yml

docker-build:
	$(COMPOSE) build --no-cache

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

docker-test-device-mgmt: docker-build
	$(COMPOSE) --profile device-mgmt up --abort-on-container-exit --exit-code-from test-device-mgmt
	$(COMPOSE) --profile device-mgmt down -v

docker-test-cov-advanced: docker-build
	$(COMPOSE) --profile cov-advanced up --abort-on-container-exit --exit-code-from test-cov-advanced
	$(COMPOSE) --profile cov-advanced down -v

docker-test-events: docker-build
	$(COMPOSE) --profile events up --abort-on-container-exit --exit-code-from test-events
	$(COMPOSE) --profile events down -v

docker-test-sc: docker-build
	$(COMPOSE) --profile secure-connect up --abort-on-container-exit --exit-code-from test-secure-connect
	$(COMPOSE) --profile secure-connect down -v

docker-test-sc-stress: docker-build
	$(COMPOSE) --profile sc-stress up --abort-on-container-exit --exit-code-from test-sc-stress
	$(COMPOSE) --profile sc-stress down -v

docker-test: docker-build
	$(MAKE) docker-test-client
	$(MAKE) docker-test-bbmd
	$(MAKE) docker-test-router
	$(MAKE) docker-test-stress
	$(MAKE) docker-test-device-mgmt
	$(MAKE) docker-test-cov-advanced
	$(MAKE) docker-test-events
	$(MAKE) docker-test-sc

docker-stress: docker-build
	$(COMPOSE) --profile stress-runner up --abort-on-container-exit --exit-code-from stress-runner
	$(COMPOSE) --profile stress-runner down -v

docker-sc-stress: docker-build
	$(COMPOSE) --profile sc-stress-runner up --abort-on-container-exit --exit-code-from sc-stress-runner
	$(COMPOSE) --profile sc-stress-runner down -v

docker-test-router-stress: docker-build
	$(COMPOSE) --profile router-stress up --abort-on-container-exit --exit-code-from test-router-stress
	$(COMPOSE) --profile router-stress down -v

docker-router-stress: docker-build
	$(COMPOSE) --profile router-stress-runner up --abort-on-container-exit --exit-code-from router-stress-runner
	$(COMPOSE) --profile router-stress-runner down -v

docker-test-bbmd-stress: docker-build
	$(COMPOSE) --profile bbmd-stress up --abort-on-container-exit --exit-code-from test-bbmd-stress
	$(COMPOSE) --profile bbmd-stress down -v

docker-bbmd-stress: docker-build
	$(COMPOSE) --profile bbmd-stress-runner up --abort-on-container-exit --exit-code-from bbmd-stress-runner
	$(COMPOSE) --profile bbmd-stress-runner down -v

docker-demo: docker-build
	$(COMPOSE) --profile demo run --rm demo-client
	$(COMPOSE) --profile demo down -v

docker-demo-auto: docker-build
	$(COMPOSE) --profile demo up --abort-on-container-exit --exit-code-from demo-client
	$(COMPOSE) --profile demo down -v

docker-clean:
	$(COMPOSE) --profile all down -v --rmi local
	$(COMPOSE) --profile demo down -v --rmi local
	$(COMPOSE) --profile stress-runner down -v --rmi local
	$(COMPOSE) --profile sc-stress down -v --rmi local
	$(COMPOSE) --profile sc-stress-runner down -v --rmi local
	$(COMPOSE) --profile router-stress down -v --rmi local
	$(COMPOSE) --profile router-stress-runner down -v --rmi local
	$(COMPOSE) --profile bbmd-stress down -v --rmi local
	$(COMPOSE) --profile bbmd-stress-runner down -v --rmi local
