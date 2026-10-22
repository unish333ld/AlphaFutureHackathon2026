# Умный кредитный кабинет предпринимателя

Backend хакатонного прототипа на Django 5.2 LTS, Django REST Framework, PostgreSQL 18 и drf-spectacular. Реализованы модели, миграции и API кредитного процесса с синтетическими данными, локальными проверками, условной подписью и моделируемой выдачей.

## Запуск через Docker

Требуются работающий Docker Engine и Compose v2.

```sh
cp .env.example .env
```

В `.env` задайте `DJANGO_SECRET_KEY` (случайная строка от 50 символов), `DB_PASSWORD` и `DEMO_PASSWORD` (от 12 символов). Для генерации ключа: `python3 -c 'import secrets; print(secrets.token_urlsafe(64))'`. `.env` игнорируется Git. Остальные настройки подходят для локального запуска.

```sh
docker compose up --build -d
docker compose logs -f web
```

Миграции, static-файлы Swagger и seeds выполняются при старте. PostgreSQL доступен внутри Compose; веб-сервис слушает `127.0.0.1:8000`.

- Swagger: http://localhost:8000/api/docs/
- Вход для Swagger: http://localhost:8000/api/session/login/
- ReDoc: http://localhost:8000/api/redoc/
- OpenAPI: http://localhost:8000/api/schema/
- Проверка готовности: http://localhost:8000/api/v1/health/
- Django Admin: http://localhost:8000/admin/ (администратор создаётся отдельно).

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

Модель данных и связи: [docs/data-model.md](docs/data-model.md). Архитектура, состояния и допущения: [docs/architecture.md](docs/architecture.md). Пошаговые запросы: [docs/demo.http](docs/demo.http). Сгенерированная схема: [docs/openapi.yaml](docs/openapi.yaml). Проверки: [docs/verification.md](docs/verification.md).

## Пройти кредитный процесс в Swagger

1. Войдите как `client`. В `GET /api/v1/applications/` есть пять черновиков. `Демо · Рост` предназначен для одобрения. Новая заявка создаётся через `POST /applications/` с UUID из справочников компаний и продуктов.
2. Вызовите `POST /applications/{id}/submit/` с текущим `lock_version`. Проверки синхронные и локальные; стандартная заявка перейдёт в `review`.
3. Войдите как `specialist`. `POST /staff/applications/{id}/decide/` с новой версией применит серверную демо-политику и создаст предложение либо отказ.
4. Как `client`: `POST /offers/{id}/accept/`. В ответе появится демо-договор с зафиксированными условиями и `document_hash`.
5. `POST /agreements/{id}/sign/`: `lock_version`, `document_hash`, `confirm_simulation=true`.
6. Как `specialist`: `POST /agreements/{id}/disburse/` с новой версией и UUID в заголовке `Idempotency-Key`. Повтор того же ключа и договора вернёт ту же выдачу. Клиент видит результат в карточке и `/disbursements/`.

Версию берите из последнего `GET /applications/{id}/`: одно действие может сохранить несколько переходов. Мутирующие действия принимают только разрешённые поля; статус, риск, ставку и банковское решение назначает сервер.

Демо-компании: `Рост` — одобрение, `Мастерская` — встречная меньшая сумма, `Уточнение` — новая ревизия после финансовых данных, `Проверка риска` — отказ, `Повтор проверки` — техническая ошибка и успешный `retry-checks`. `outsider` имеет доступ только к своей шестой компании. У `accountant` нет права подписи.

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

В контейнере: `docker compose exec web pytest -c /app/pyproject.toml`. Истечение предложений обрабатывается при чтении карточки/предложения и командой `python manage.py expire_offers`. Новые данные после рассмотрения отправляются через `/revise/`, ответ на уточнение — через `/provide-information/`. Seeds идемпотентны. `seed_demo --reset-passwords` обновляет пароли только четырёх демо-пользователей.

## Границы версии

Реализован backend. React-интерфейс и ИИ-помощник — следующие этапы. Скоринг, условия продуктов, подпись и выдача демонстрационные; реальных переводов, БКИ/ФНС, финансовых документов и платных API нет. Применены проектные навыки `alfa-credit-build`, `alfa-credit-guardrails`, `django-expert` и PostgreSQL-рекомендации. Юридическая проверка реального банковского сервиса не проводилась. Зависимости перечислены в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
