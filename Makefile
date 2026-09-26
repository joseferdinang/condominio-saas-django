COMPOSE := docker compose

.PHONY: help build up down logs check migrate migrations test shell dbshell

help:
	@echo "build       Construir las imágenes"
	@echo "up          Levantar los servicios en segundo plano"
	@echo "down        Detener los servicios"
	@echo "logs        Seguir los logs del servidor"
	@echo "check       Ejecutar verificaciones de Django"
	@echo "migrate     Aplicar migraciones"
	@echo "migrations  Crear migraciones"
	@echo "test        Ejecutar las pruebas"
	@echo "shell       Abrir el shell de Django"
	@echo "dbshell     Abrir psql"

build:
	$(COMPOSE) build

up:
	$(COMPOSE) up --detach

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs --follow web

check:
	$(COMPOSE) exec web python manage.py check

migrate:
	$(COMPOSE) exec web python manage.py migrate

migrations:
	$(COMPOSE) exec web python manage.py makemigrations

test:
	$(COMPOSE) exec web python manage.py test --settings=config.settings.test

shell:
	$(COMPOSE) exec web python manage.py shell

dbshell:
	$(COMPOSE) exec db psql --username=$$POSTGRES_USER --dbname=$$POSTGRES_DB
