.PHONY: install dev prod lint format clean test \
	docker-network docker-build docker-up docker-down docker-logs docker-restart \
	help

install:
	pip install uv
	uv sync

dev:
	@echo "Starting server in development environment"
	APP_ENV=development uv run uvicorn app.main:app --reload --port 8000

prod:
	@echo "Starting server in production environment"
	APP_ENV=production uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

lint:
	uv run ruff check .

format:
	uv run ruff format .

test:
	uv run pytest

clean:
	rm -rf .venv
	rm -rf __pycache__
	rm -rf .pytest_cache

# Docker
DOCKER_COMPOSE ?= docker compose
ENV ?= development

docker-network:
	@docker network inspect backend-internal >/dev/null 2>&1 || docker network create backend-internal

docker-build: docker-network
	@ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then echo "Missing $$ENV_FILE, copy .env.example first"; exit 1; fi
	APP_ENV=$(ENV) $(DOCKER_COMPOSE) build

docker-up: docker-network
	@ENV_FILE=.env.$(ENV); \
	if [ ! -f $$ENV_FILE ]; then echo "Missing $$ENV_FILE, copy .env.example first"; exit 1; fi
	APP_ENV=$(ENV) $(DOCKER_COMPOSE) up --build -d

docker-down:
	APP_ENV=$(ENV) $(DOCKER_COMPOSE) down

docker-logs:
	APP_ENV=$(ENV) $(DOCKER_COMPOSE) logs -f app

docker-restart: docker-down docker-up

help:
	@echo "Usage: make <target> [ENV=development|staging|production]"
	@echo ""
	@echo "  install       Install dependencies with uv"
	@echo "  dev           Run server locally with reload (development)"
	@echo "  prod          Run server locally (production)"
	@echo "  lint          Run ruff check"
	@echo "  format        Run ruff format"
	@echo "  test          Run pytest"
	@echo "  clean         Remove .venv and caches"
	@echo ""
	@echo "  docker-build  Build the app image (ENV selects .env.<ENV>)"
	@echo "  docker-up     Start the app via docker compose (joins backend-internal)"
	@echo "  docker-down   Stop the app"
	@echo "  docker-logs   Follow app logs"
	@echo "  docker-restart  Down then up"
