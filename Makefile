.PHONY: install dev prod lint format clean test \
	docker-network docker-build docker-up docker-down docker-logs docker-restart \
	docker-prod-up docker-prod-down docker-prod-logs \
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

# docker-compose.prod.yml is an overlay (pulls IMAGE_TAG from ghcr, no
# build:) meant to layer on top of docker-compose.yml, not run standalone.
docker-prod-up: docker-network
	@if [ ! -f .env.production ]; then echo "Missing .env.production"; exit 1; fi
	$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml up -d

docker-prod-down:
	$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml down

docker-prod-logs:
	$(DOCKER_COMPOSE) -f docker-compose.yml -f docker-compose.prod.yml logs -f app

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
	@echo "  docker-prod-up    Start via docker-compose.yml + docker-compose.prod.yml (needs IMAGE_TAG, .env.production)"
	@echo "  docker-prod-down  Stop the prod stack"
	@echo "  docker-prod-logs  Follow prod app logs"
