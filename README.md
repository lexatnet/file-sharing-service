## Тестовое задание на позицию Fullstack разработчика (Python + React)

**Вводные:**
1. Здесь представлен MVP проект файлообменника. Он позволяет загружать файлы, проверяет их на подозрительный контент и отправляет алерты;
2. Репозиторий содержит в себе бэкенд и фронтенд части;
3. В обоих частях присутствуют баги, неоптимизированный код, неудачные архитектурные решения.

**Задачи:**
1. Проведите рефакторинг бэкенда, не ломая бизнес-логики: предложите свое видение архитектуры и реализуйте его;
2. (Дополнительно) На бэкенде есть возможность неочевидной оптимизации - выполните ее;
3. (Дополнительно) Разбейте логику фронтенда на слои;

**Запуск:**
   
```bash
docker compose -f docker-compose.dev.yml up
```

```bash
docker compose -f docker-compose.dev.yml exec -it backend alembic upgrade head
```

**Запуск тестов бэкенда:**

Тесты чистые: не требуют БД, Redis или файлов в storage. Бэкенд — Python 3.14+ (задан в `backend/.python-version`).

В контейнере (dev-стек, pytest уже в образе):
```bash
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml exec backend python -m pytest -q
```

dev-стек собирает backend/worker из `backend/Dockerfile.dev`, куда включена dev-группа
(pytest и др.); исходники монтируются с хоста (`./backend:/backend`), поэтому правки
подхватываются без пересборки. Продакшн-образ (`Dockerfile`) dev-зависимости не содержит.

Локально. Способ 1 — через `uv` в venv:

```bash
cd backend
python -m venv .venv                # создаем виртуальное окружение проекта в папке .venv
source .venv/bin/activate
pip install -U pip setuptools
pip install uv
uv sync --group dev                  # установит runtime-зависимости + dev-группу (pytest и др.)
uv run pytest -q
```


**Открыть фронт:** ```http://localhost:3000/test``` 

**Открыть бэк:** ```http://localhost:8000/docs```
