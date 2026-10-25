# Умный кредитный кабинет предпринимателя

Full-stack хакатонный прототип: Django 5.2 LTS, Django REST Framework, PostgreSQL 18, drf-spectacular и React-интерфейс клиента и кредитного специалиста. Единый кредитный процесс использует синтетические данные, локальные проверки, условную подпись и моделируемую выдачу.

Актуальный [стек и границы релиза](docs/stack.md): Python/Django/DRF/PostgreSQL; React + TypeScript strict + Vite, Core Components Альфа-Банка, CSS Modules/Grid/Flexbox/медиазапросы, React Router, TanStack Query, React Hook Form/Zod. Django sessions + HttpOnly cookie + CSRF, drf-spectacular/OpenAPI/Swagger UI; Docker Compose, Nginx для frontend/API proxy. pytest/pytest-django, Vitest и Playwright. Bootstrap в основном приложении не используется. [Frontend: запуск, экраны и тесты](docs/frontend.md).

Для frontend: [OpenAPI](docs/openapi.yaml) и [экран сотрудника → API, назначения, действия, ошибки и сессии](docs/frontend-integration.md).

Дополнительный [QA-отчёт: вход, сохранение ввода и браузерная регрессия](docs/qa-auth-verification.md).

## Запуск через Docker

Требуются работающий Docker Engine и Compose v2.

```sh
cp .env.example .env
```

В `.env` задайте `DJANGO_SECRET_KEY` (случайная строка от 50 символов), `DB_PASSWORD` и `DEMO_PASSWORD` (от 12 символов). Для генерации ключа: `python3 -c 'import secrets; print(secrets.token_urlsafe(64))'`. `.env` игнорируется Git. Остальные настройки подходят для локального запуска.

```sh
docker compose up --build -d --wait --wait-timeout 120
docker compose logs -f web
```

Миграции, static-файлы Swagger и seeds выполняются при старте. PostgreSQL доступен внутри Compose; Nginx отдаёт интерфейс на **http://localhost:8080**, а API доступен с того же origin `/api/`. Прямой backend слушает `127.0.0.1:8000`; не смешивайте разные origin в одной браузерной сессии.

- Swagger: http://localhost:8000/api/docs/
- Swagger через frontend origin: http://localhost:8080/api/docs/
- Вход для Swagger: http://localhost:8000/api/session/login/
- ReDoc: http://localhost:8000/api/redoc/
- OpenAPI: http://localhost:8000/api/schema/
- Проверка готовности: http://localhost:8000/api/v1/health/
- Django Admin: http://localhost:8000/admin/ (администратор создаётся отдельно).

Если порт 8000 занят, задайте `WEB_PORT`, например `WEB_PORT=18000 docker compose -p alfa-credit-demo up --build -d --wait --wait-timeout 120`. Подробный [сценарий демонстрации backend](docs/backend-demo.md) содержит проверенный запуск на 18000 и команды автоматической проверки через HTTP.

Пользователи `client`, `specialist`, `accountant`, `outsider` получают пароль из `DEMO_PASSWORD`. Специалист не является superuser. Для **Try it out** войдите через страницу входа в той же вкладке: cookie сессии и CSRF передаются автоматически. Поле Authorize для cookie заполнять не нужно. Для смены роли вызовите `POST /api/v1/session/logout/`, откройте страницу входа и обновите Swagger.

## Где находятся модели

| Модуль | Модели |
|---|---|
| `backend/accounts/models.py` | User |
| `backend/companies/models.py` | Company, CompanyMember |
| `backend/products/models.py` | CreditProduct |
| `backend/applications/models.py` | Application, ApplicationRevision, InformationRequest, ApplicationEvent |
| `backend/checks/models.py` | CheckResult |
| `backend/decisions/models.py` | Assessment, CreditDecision |
| `backend/offers/models.py` | Offer |
| `backend/agreements/models.py` | Agreement, Disbursement |
| `backend/assistant/models.py` | Conversation, Message |

Модель данных и связи: [docs/data-model.md](docs/data-model.md). Архитектура, состояния и допущения: [docs/architecture.md](docs/architecture.md). Пошаговые запросы: [docs/demo.http](docs/demo.http). Сгенерированная схема: [docs/openapi.yaml](docs/openapi.yaml). Проверки: [docs/verification.md](docs/verification.md).

## Пройти кредитный процесс в Swagger

1. Войдите как `client`. В `GET /api/v1/applications/` есть пять черновиков. `Демо · Рост` предназначен для одобрения. Новая заявка создаётся через `POST /applications/` с UUID из справочников компаний и продуктов.
2. Вызовите `POST /applications/{id}/submit/` с текущим `lock_version`. Проверки синхронные и локальные; стандартная заявка перейдёт в `review`.
3. Войдите как `specialist`. Сначала `POST /staff/applications/{id}/claim/` с lock_version, затем `POST /staff/applications/{id}/decide/` с версией из claim. Серверная политика создаст предложение либо отказ. Освободить свою заявку: `/release/`. Очередь «мои»: `GET /staff/applications/?assignment=mine`, свободные — `assignment=free`.
4. Как `client`: `POST /offers/{id}/accept/`. В ответе появится демо-договор с зафиксированными условиями и `document_hash`.
5. `POST /agreements/{id}/sign/`: `lock_version`, `document_hash`, `confirm_simulation=true`.
6. Как назначенный `specialist`: `POST /agreements/{id}/disburse/` с новой версией и UUID в заголовке `Idempotency-Key`. Повтор того же ключа и договора вернёт ту же выдачу. Клиент видит результат в карточке и `/disbursements/`. Завершение автоматически снимает назначение.

Версию берите из последнего `GET /applications/{id}/`: одно действие может сохранить несколько переходов. Мутирующие действия принимают только разрешённые поля; статус, риск, ставку и банковское решение назначает сервер.

Демо-компании: `Рост` — одобрение, `Мастерская` — встречная меньшая сумма, `Уточнение` — новая ревизия после финансовых данных, `Проверка риска` — отказ, `Повтор проверки` — техническая ошибка и успешный `retry-checks`. `outsider` имеет доступ только к своей шестой компании. У `accountant` нет права подписи.

## Савелий: локальный ИИ-помощник

Для показа окна задайте `VITE_AI_ASSISTANT_ENABLED=true` при сборке frontend. Для ответов дополнительно задайте `AI_ENABLED=true` в серверном `.env` и настройте `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`; `LLM_API_KEY` нужен только если его требует выбранный endpoint. Пример полностью локального варианта: `LLM_PROVIDER=compatible`, `LLM_BASE_URL=http://host.docker.internal:11434/v1`, `LLM_MODEL=qwen2.5:7b-instruct-q4_0` при запущенной Ollama. Настройки модели и ключ остаются только на сервере. `host.docker.internal` подходит Docker Desktop; на Linux адрес хоста может отличаться.

Клиентские диалоги доступны через `/api/v1/assistant/conversations/`. Отправка сообщения требует session cookie, CSRF, текста и актуального `expected_version`. Ответ содержит текст, проверенные серверные `facts` и иногда `suggested_draft`. Предложение черновика ничего не записывает: клиент подтверждает его через обычную форму заявки. При выключенном ИИ кабинет и весь кредитный процесс работают без помощника. Подробнее о frontend и запуске: [docs/frontend.md](docs/frontend.md).

## Локальная разработка и проверки

Требуются Python 3.14 и PostgreSQL 18. Создайте отдельную БД и пользователя, настройте `DB_*` в `.env`. Для создания тестовой БД пользователь должен иметь `CREATEDB`; при публичном запуске нужны отдельные ограниченные полномочия.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py seed_demo
.venv/bin/python backend/manage.py runserver 127.0.0.1:8000
```

Для `runserver` задайте `DJANGO_DEBUG=true` локально. Для gunicorn с `DEBUG=false` сначала выполните `collectstatic`. Публичный доступ требует HTTPS, домена/CSRF-настроек и `DJANGO_COOKIE_SECURE=true`. Compose предназначен для локального демо.

```sh
.venv/bin/python backend/manage.py check
.venv/bin/python backend/manage.py makemigrations --check --dry-run
.venv/bin/python backend/manage.py spectacular --file docs/openapi.yaml --validate --fail-on-warn
.venv/bin/pytest
.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
```

Для полного QA-прогона с измерением строк и ветвей установите дополнительные тестовые зависимости. Выполняйте команды из корня проекта:

```sh
.venv/bin/python -m pip install -r backend/requirements-test.lock
.venv/bin/pytest --cov --cov-report=term-missing --cov-report=html --cov-report=json:reports/coverage.json --cov-report=xml:reports/coverage.xml --junitxml=reports/junit.xml
```

HTML-отчёт: `htmlcov/index.html`. Порог покрытия — 95% по общей метрике строк и ветвей; более низкое значение завершает прогон ошибкой. Сгенерированные отчёты игнорируются Git. Считается код backend, включая API, сервисы, модели, Admin, настройки и команды; исключены сами тесты, миграции и точки запуска `manage.py`/`wsgi.py`. Тестовая БД создаётся из миграций и удаляется после прогона. HTTP-тест запускает временный локальный сервер; тесты гонок используют независимые PostgreSQL-соединения. Результаты и найденный дефект: [docs/verification.md](docs/verification.md).

В контейнере базовый набор: `docker compose exec web pytest -c /app/pyproject.toml`. Инструменты покрытия устанавливаются отдельно из `requirements-test.lock`. Истечение предложений обрабатывается при чтении карточки/предложения и командой `python manage.py expire_offers`. Новые данные после рассмотрения отправляются через `/revise/`, ответ на уточнение — через `/provide-information/`. Seeds идемпотентны. `seed_demo --reset-passwords` обновляет пароли только четырёх демо-пользователей.

## Границы версии

Реализованы backend и React-интерфейс. Савелий — необязательный помощник с Django API и плавающим React-окном (`AI_ENABLED=false` и `VITE_AI_ASSISTANT_ENABLED=false` по умолчанию). Прогноз денежных потоков и стресс-тесты — следующий продуктовый этап; SLA и сложная приоритизация вне релиза. Скоринг, условия продуктов, подпись и выдача демонстрационные; реальных переводов, БКИ/ФНС, финансовых документов и платных API нет. Применены `alfa-credit-frontend`, `alfa-credit-build`, `alfa-credit-guardrails`, React- и Playwright-рекомендации; для backend — `django-expert` и PostgreSQL-рекомендации. Юридическая проверка реального банковского сервиса не проводилась. Зависимости перечислены в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
