.PHONY: setup dev-backend dev-frontend test build compose-config up down

setup:
	@test -f backend/.env || cp .env.example backend/.env
	python -m pip install -r backend/requirements-dev.txt
	npm --prefix frontend ci

dev-backend:
	python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	npm --prefix frontend run dev

test:
	python -m pytest -q

build:
	npm --prefix frontend run build
	python -m compileall -q backend

compose-config:
	docker compose config --quiet

up:
	docker compose up --build

down:
	docker compose down
