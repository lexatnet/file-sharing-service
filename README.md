## Тестовое задание на позицию Fullstack разработчика (Python + React)

**Вводные:**
1. Здесь представлен MVP проект файлообменника. Он позволяет загружать файлы, проверяет их на подозрительный контент и отправляет алерты;
2. Репозиторий содержит в себе бэкенд и фронтенд части;
3. В обоих частях присутствуют баги, неоптимизированный код, неудачные архитектурные решения.

**Задачи:**
1. Проведите рефакторинг бэкенда, не ломая бизнес-логики: предложите свое видение архитектуры и реализуйте его;
2. (Дополнительно) На бэкенде есть возможность неочевидной оптимизации - выполните ее;
3. (Дополнительно) Разбейте логику фронтенда на слои;


**Примечания:**

в репозитории сделано несколько веток для удобства:
- old - задание без изменений
- fixes - исправления и рефакторинг
- new-arch - изменения в архитектуре приложения (содержит все измениения и влита в main)


**Запуск:**
   
```bash
docker compose --file docker-compose.dev.yml --env-file ./.env.dev up
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

---

## История изменений (по коммитам)

- **`97bd291` frontend refactoring** — логика фронтенда разбита на слои:
  - `src/components/` (таблицы, модалка загрузки, бейджи статусов)
  -  `src/lib/`(API-клиент fetch, форматирование размеров/дат)
  -  `src/types.ts` (модели)

- **`2092366` backend refactoring** — рефакторинг бэкенда без слома бизнес-логики:
  - новая слоистая архитектура:
    - `api.py` (HTTP) 
    - `services.py` (оркестрация)
    - `repositories.py` (доступ к данным)
    - `config.py`/`db.py` (конфиг/сессиия)
    - `scanner.py`/`metadata.py`/`storage.py` (бизнес-примитивы)
    - `tasks.py` (Celery задачи)
  - **автоинициализация БД при первом запуске**: 
    - миграции (`alembic upgrade head`) применяются при старте API (lifespan FastAPI) и воркера (`on_after_configure`), через `src/migration.py` (идемпотентно)
  - **рестарт незавершённых проверок при старте приложения**: файлы, оставшиеся в
    `uploaded`/`processing` после падения воркера, автоматически возвращаются в
    конвейер (`requeue_incomplete`: scan для `uploaded`, extract-metadata для `processing`);
  - добавлены тесты
  - миграции на ondelete-cascade для `alerts`;
  - загруженные файлы вынесены из кода на отдельный volume (`uploaded-files` → `/data/files`) (настройка через `STORAGE_DIR` вынесена в конфиг).

- **`5bd47a4` Periodic re-checking in case of worker failure/task loss** —
  периодическая перепроверка незавершённых файлов, независимо от рестартов:
  - Celery **beat** публикует `requeue_incomplete_periodic` по расписанию
    (по умолчанию раз в 5 минут; регулируется env `REQUEUE_INTERVAL_SECONDS`;
  - новый сервис **`backend-beat`** в `docker-compose.dev.yml` и `docker-compose.prod.yml`;
  - `celerybeat-schedule` (SQLite-состояние расписания** вынесен на volume `/data`
    (вне кода; в `.gitignore` добавлено правило `celerybeat-schedule*`.`

- **`777cb1d` new file upload/downlod with s3** —
  - Бэкенд: S3StorageService (boto3: create_multipart_upload → presign-URL → complete/abort/list_parts)
  - колонка upload_id в БД + миграция
  - 5 новых эндпоинтов: (/files/uploads, …/presign, …/complete, …/abort, GET …/{id}для resume)
  - скачивание — стрим из S3.
  - Воркер: metadata-extraction качает объект из S3 во временный файл.
  - Фронтенд: чанкованная загрузка по presigned-URL с прогрессом, «Отмена» (AbortController), возобновление прерванной из localStorage (с пропуском уже залитых частей).
  - Compose: depends_on: s3 у backend/worker/beat, убраны старые volume uploaded-files

- **`e87baf1` Refactoring** —
  - Мёртвый AlertRepository.create — удалён из repositories.py (воркер и так ходит напрямую через session.add).
  - Дублированная валидация title — вынесен общий хелпер _validate_title() в services.py; используется в initiate_upload и update_file..
  - body["Body"] — в storage.py введён типизированный @dataclass S3Object (.stream), метод iter_object переименован в open_stream; api.py пишет body stream вместо магической строки.
  - Import внутри функции — from urllib.parse import quote перенесён наверх модуля.
  - upload_all_parts — вынесен из двух тестовых файлов в общий tests/conftest.py.
  - Потеря причины S3-ошибки при complete — services.complete_upload теперь пробрасывает Code (detail …Could not complete…: ENTITY_TOO_SMALL и т.п.

- **`8ed7eec` events subscription** —
  - Бэкенд:
    - backend/src/events.py (новый) — пул событий:
      - publish_event(type, file_id) — воркер публикует в канал file-events.
      - stream_event_source() — API подписан и ретранслирует события в SSE + heartbeat-комментарии для удержания соединения.
    - backend/src/api.py — GET /events (SSE, text/event-stream, Cache-Control: no-cache); publish_event("file_created", ...) после успешного complete_upload.
    - backend/src/tasks.py — publish_event("file_processed") при завершении обработки (и успех, и сбой — _notify_processed покрывает обе ветки), publish_event("alert_created") после создания алерта.
  - Фронтенд:
    - frontend/src/lib/api.ts — subscribeFileEvents(onEvent): обёртка над EventSource, парсит SSE-событие file_event в {type, file_id}, возвращает handle с close().
    - frontend/src/app/page.tsx — useEffect подписывается на SSE, по каждому событию вызывает loadData() — перезапрос списков файлов/алертов; при размонтировании закрывает соединение.
  - Тесты:
    - backend/tests/test_events.py (новый): кодирование SSE-фрейма + полный round-trip pub/sub (скипается, если Redis недоступен локально).
  - Как это работает: Фронт слушает /events. Когда воркер завершает обработку файла или создаёт алерт, он публикует в Redis; FastAPI получает и рассылает всем открытым SSE-клиентам; браузер перезапрашивает GET /files / GET /alerts — списки всегда консистентны (полные объекты не пересылаются, по схеме «событие → перезапрос»). Второй открытый браузер также обновляется без ручного refresh.
