.PHONY: up down build logs ps smoke test

up:
	docker compose up --build -d --wait --wait-timeout 240

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs --tail=100 -f

ps:
	docker compose ps

smoke:
	python scripts/smoke_test.py

test:
	cd apps/api && python -m pytest && python -m ruff check .
	cd apps/worker && python -m pytest && python -m ruff check .
	cd apps/web && npm run build
