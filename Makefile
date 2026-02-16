.PHONY: lint typecheck test docs check fix format coverage coverage-html \
       bench-bip bench-bip-json bench-bip-profile \
       bench-router bench-router-json bench-router-profile \
       bench-bbmd bench-bbmd-json bench-bbmd-profile \
       bench-sc bench-sc-json bench-sc-profile \
       bench-sc-profile-client bench-sc-profile-hub \
       docker-build docker-test docker-stress docker-test-client docker-test-bbmd \
       docker-test-router docker-test-device-mgmt docker-test-cov-advanced \
       docker-test-events docker-test-sc docker-test-sc-stress docker-sc-stress \
       docker-test-router-stress docker-router-stress \
       docker-test-bbmd-stress docker-bbmd-stress \
       docker-test-ipv6 \
       docker-test-mixed-bip-ipv6 docker-test-mixed-bip-sc \
       docker-demo docker-demo-auto docker-clean

lint:
	uv run ruff check src/ tests/ docker/ examples/ scripts/
	uv run ruff format --check src/ tests/ docker/ examples/ scripts/

typecheck:
	uv run mypy src/ examples/ docker/ scripts/

test:
	uv run pytest --tb=short -q

docs:
	uv run sphinx-build -W -b html docs docs/_build/html

check: lint typecheck test docs

fix:
	uv run ruff check --fix src/ tests/ docker/ examples/ scripts/
	uv run ruff format src/ tests/ docker/ examples/ scripts/

format:
	uv run ruff format src/ tests/ docker/ examples/ scripts/

coverage:
	uv run pytest --cov --cov-report=term-missing

coverage-html:
	uv run pytest --cov --cov-report=html

# ---------------------------------------------------------------------------
# Local benchmarks (no Docker required)
# ---------------------------------------------------------------------------

bench-bip:
	uv run python scripts/bench_bip.py

bench-bip-json:
	uv run python scripts/bench_bip.py --json

bench-router:
	uv run python scripts/bench_router.py

bench-router-json:
	uv run python scripts/bench_router.py --json

bench-bbmd:
	uv run python scripts/bench_bbmd.py

bench-bbmd-json:
	uv run python scripts/bench_bbmd.py --json

bench-sc:
	uv run python scripts/bench_sc.py

bench-sc-json:
	uv run python scripts/bench_sc.py --json

bench-bip-profile:
	uv run python scripts/bench_bip.py --profile --sustain 10

bench-router-profile:
	uv run python scripts/bench_router.py --profile --sustain 10

bench-bbmd-profile:
	uv run python scripts/bench_bbmd.py --profile --sustain 10

bench-sc-profile:
	uv run python scripts/bench_sc.py --profile --sustain 10

# ---------------------------------------------------------------------------
# Mixed-environment SC profiling (Docker ↔ local split)
# ---------------------------------------------------------------------------

# Generate shared TLS certs for mixed SC benchmarks
.sc-bench-certs:
	uv run python scripts/bench_sc.py --generate-certs .sc-bench-certs

# Profile client side: hub runs in Docker, echo nodes + stress client run locally
bench-sc-profile-client: .sc-bench-certs docker-build
	SC_BENCH_CERTS=.sc-bench-certs $(COMPOSE) --profile sc-bench-hub up -d
	@echo "Waiting for Docker hub..." && sleep 5
	-uv run python scripts/bench_sc.py --mode client \
		--hub-uri wss://localhost:4443 --cert-dir .sc-bench-certs \
		--profile --sustain 15
	SC_BENCH_CERTS=.sc-bench-certs $(COMPOSE) --profile sc-bench-hub down

# Profile hub side: hub runs locally, echo nodes + stress client run in Docker
bench-sc-profile-hub: .sc-bench-certs docker-build
	SC_BENCH_CERTS=.sc-bench-certs $(COMPOSE) --profile sc-bench-client up -d &
	@echo "Waiting for Docker clients..." && sleep 10
	uv run python scripts/bench_sc.py --mode hub --port 4443 \
		--cert-dir .sc-bench-certs --profile --duration 100
	SC_BENCH_CERTS=.sc-bench-certs $(COMPOSE) --profile sc-bench-client down

# ---------------------------------------------------------------------------
# Docker integration tests
# ---------------------------------------------------------------------------

BAC_PY_VERSION := $(shell uv run python -c "import bac_py; print(bac_py.__version__)")
export BAC_PY_VERSION

COMPOSE := docker compose -f docker/docker-compose.yml

docker-build:
	docker build --no-cache -t bac-py:$(BAC_PY_VERSION) -f docker/Dockerfile .

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

docker-test-ipv6: docker-build
	$(COMPOSE) --profile ipv6 up --abort-on-container-exit --exit-code-from test-ipv6
	$(COMPOSE) --profile ipv6 down -v

docker-test-mixed-bip-ipv6: docker-build
	$(COMPOSE) --profile mixed-bip-ipv6 up --abort-on-container-exit --exit-code-from test-mixed-bip-ipv6
	$(COMPOSE) --profile mixed-bip-ipv6 down -v

.sc-mixed-certs:
	uv run python -c "from docker.lib.sc_pki import generate_test_pki; from pathlib import Path; generate_test_pki(Path('.sc-mixed-certs'), names=['hub','node1','node2','router'])"

docker-test-mixed-bip-sc: docker-build .sc-mixed-certs
	SC_MIXED_CERTS=$(CURDIR)/.sc-mixed-certs $(COMPOSE) --profile mixed-bip-sc up --abort-on-container-exit --exit-code-from test-mixed-bip-sc
	SC_MIXED_CERTS=$(CURDIR)/.sc-mixed-certs $(COMPOSE) --profile mixed-bip-sc down -v
	rm -rf .sc-mixed-certs

docker-test: docker-build
	$(MAKE) docker-test-client
	$(MAKE) docker-test-bbmd
	$(MAKE) docker-test-router
	$(MAKE) docker-test-stress
	$(MAKE) docker-test-device-mgmt
	$(MAKE) docker-test-cov-advanced
	$(MAKE) docker-test-events
	$(MAKE) docker-test-sc
	$(MAKE) docker-test-ipv6
	$(MAKE) docker-test-mixed-bip-ipv6
	$(MAKE) docker-test-mixed-bip-sc

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
	$(COMPOSE) --profile mixed-bip-ipv6 down -v --rmi local
	$(COMPOSE) --profile mixed-bip-sc down -v --rmi local
	rm -rf .sc-mixed-certs
	@echo "Removing all bac-py images..."
	docker images --format '{{.Repository}}:{{.Tag}}' | grep '^bac-py:' | xargs -r docker rmi 2>/dev/null || true
