.DEFAULT_GOAL := help

# Load .env so we can reference DB credentials in targets
-include .env

# Source directories for linting / type-checking
SRC_DIRS = scripts/ api/ config/ profiling/ streamlit_app/

# ---------- Help ----------

.PHONY: help
help: ## Show this help message
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ---------- Testing ----------

.PHONY: test
test: ## Run unit tests
	pytest -m "not integration"

.PHONY: test-integration
test-integration: ## Run integration tests
	pytest tests/integration -m integration

.PHONY: test-all
test-all: ## Run unit and integration tests
	pytest

.PHONY: coverage
coverage: ## Run unit tests with coverage report
	pytest -m "not integration" --cov=. --cov-report=term-missing --cov-report=html

# ---------- Code Quality ----------

.PHONY: lint
lint: ## Run ruff linter and formatter
	ruff check $(SRC_DIRS) --fix
	ruff format $(SRC_DIRS)

.PHONY: typecheck
typecheck: ## Run mypy type checking
	mypy $(SRC_DIRS)

.PHONY: check
check: lint typecheck ## Run all code quality checks

# ---------- Dev Server ----------

.PHONY: dev
dev: ## Start API dev server with auto-reload
	uvicorn api.main:app --reload

.PHONY: docs
docs: ## Serve documentation locally
	mkdocs serve

.PHONY: streamlit
streamlit: ## Run the Streamlit web app (requires API on localhost:8001)
	streamlit run streamlit_app/app.py

# ---------- Docker ----------

.PHONY: up
up: ## Start database and API containers
	docker compose up --build -d

.PHONY: down
down: ## Stop containers
	docker compose down

.PHONY: logs
logs: ## Tail API container logs
	docker compose logs -f api

.PHONY: test-db-up
test-db-up: ## Start test database container
	docker compose -f docker-compose.test.yml up -d

.PHONY: test-db-down
test-db-down: ## Stop and remove test database
	docker compose -f docker-compose.test.yml down -v

.PHONY: psql
psql: ## Connect to the database via docker exec
	docker compose exec db bash -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

.PHONY: psql-local
psql-local: ## Connect to the database via local psql
	psql -h localhost -p 5433 -U $(POSTGRES_USER) -d $(POSTGRES_DB)

# ---------- Data Pipeline ----------

.PHONY: pipeline
pipeline: ## Run full data pipeline
	POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db

.PHONY: pipeline-test
pipeline-test: ## Run pipeline with --test-limit 1
	POSTGRES_HOST=localhost POSTGRES_PORT=5433 python scripts/orchestrator.py --write-db --test-limit 1

# ---------- Security ----------

.PHONY: audit
audit: ## Run pip-audit on dependencies
	pip-audit -r requirements.txt --desc
	pip-audit -r requirements-dev.txt --desc
	pip-audit -r streamlit_app/requirements.txt --desc

# ---------- Cleanup ----------

.PHONY: clean
clean: ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -rf htmlcov/ .coverage
