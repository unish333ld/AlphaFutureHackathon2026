# Умный кредитный кабинет предпринимателя

Backend хакатонного прототипа на Django 5.2 LTS, Django REST Framework, PostgreSQL 18 и drf-spectacular. Реализованы модели, миграции и API кредитного процесса с синтетическими данными, локальными проверками, условной подписью и моделируемой выдачей.

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

Миграции, static-файлы Swagger и seeds выполняются при старте. PostgreSQL доступен внутри Compose; веб-сервис слушает `127.0.0.1:8000`.

- Swagger: http://localhost:8000/api/docs/
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
3. Войдите как `specialist`. `POST /staff/applications/{id}/decide/` с новой версией применит серверную демо-политику и создаст предложение либо отказ.
4. Как `client`: `POST /offers/{id}/accept/`. В ответе появится демо-договор с зафиксированными условиями и `document_hash`.
5. `POST /agreements/{id}/sign/`: `lock_version`, `document_hash`, `confirm_simulation=true`.
6. Как `specialist`: `POST /agreements/{id}/disburse/` с новой версией и UUID в заголовке `Idempotency-Key`. Повтор того же ключа и договора вернёт ту же выдачу. Клиент видит результат в карточке и `/disbursements/`.

Версию берите из последнего `GET /applications/{id}/`: одно действие может сохранить несколько переходов. Мутирующие действия принимают только разрешённые поля; статус, риск, ставку и банковское решение назначает сервер.

Демо-компании: `Рост` — одобрение, `Мастерская` — встречная меньшая сумма, `Уточнение` — новая ревизия после финансовых данных, `Проверка риска` — отказ, `Повтор проверки` — техническая ошибка и успешный `retry-checks`. `outsider` имеет доступ только к своей шестой компании. У `accountant` нет права подписи.

## Савелий: backend помощника

Помощник выключен по умолчанию (`AI_ENABLED=false`), а кредитный процесс работает без него. Он использует OpenAI-совместимый Chat Completions API; модель, URL и ключ меняются настройками без правки кода. `.env.example` показывает OpenRouter с бесплатной открытовесной `google/gemma-4-26b-a4b-it:free`, резервной `nvidia/nemotron-3.5-lightning:free` и необязательной локальной Ollama. Для включения задайте **только на сервере** `AI_ENABLED=true` и `LLM_API_KEY` в игнорируемом `.env`, затем пересоздайте контейнер web. Не добавляйте ключ в Git, frontend, URL или Swagger. Судьи могут подставить свой OpenAI-совместимый URL, ключ и модель в те же переменные.

При ошибке основной модели OpenRouter пробует следующую из `LLM_FALLBACK_MODELS`. При сетевой ошибке, превышении квоты или недоступности OpenRouter backend обращается к `LLM_LOCAL_FALLBACK_BASE_URL`, если там запущена Ollama с `LLM_LOCAL_FALLBACK_MODEL`. Этот адрес должен быть доступен **из контейнера web**; `host.docker.internal` подходит для локального Docker Desktop и не является универсальным адресом для Linux-хоста. Для полностью локального режима задайте `LLM_PROVIDER=compatible`, `LLM_BASE_URL=http://host.docker.internal:11434/v1`, `LLM_MODEL=qwen2.5:7b-instruct-q4_0`; ключ не нужен. Если нет ни облака, ни локальной модели, оставьте `AI_ENABLED=false`.

Бесплатная квота OpenRouter на обычном аккаунте — 50 запросов в день и 20 в минуту; вопрос с инструментом обычно расходует два запроса, а переключение между бесплатными моделями не увеличивает квоту аккаунта. Проверяйте [актуальные лимиты](https://openrouter.ai/docs/api_reference/limits) и [каталог моделей](https://openrouter.ai/api/v1/models) перед показом. Бесплатный endpoint NVIDIA [может записывать запросы](https://openrouter.ai/nvidia/nemotron-3.5-lightning:free); используйте только синтетические демо-данные. Ключ OpenRouter и качество ответов облачных моделей на целевом аккаунте требуют отдельной живой проверки.

Клиент создаёт диалог через `POST /api/v1/assistant/conversations/` с `company_id` и необязательным `application_id`. `GET /api/v1/assistant/conversations/` и `GET /api/v1/assistant/conversations/{id}/messages/` показывают только свои диалоги. `POST .../{id}/messages/` принимает `text` и текущий `expected_version` из диалога. Нужны вход в сессию и CSRF. Ответ содержит текст, серверные `facts`, необязательный `suggested_draft` и новую версию. Числа берутся из каталога продуктов, серверного аннуитетного расчёта или сохранённой заявки, а предложение черновика **ничего не записывает**. Для создания заявки клиент подтверждает его через обычный API. Лимит отправки — 10 сообщений в минуту на пользователя; при двух процессах это приблизительное ограничение.

Помесячной финансовой истории и сценарного прогноза пока нет. Савелий не обещает одобрение, не назначает условия, не запускает проверки и не принимает кредитных решений. Если второй модельный запрос не удался после получения серверных фактов, помощник возвращает проверенное краткое резюме этих фактов. Если ни одна модель не ответила до получения фактов, сообщение не сохраняется и API отвечает 503; основные операции кабинета продолжают работать. Первый запрос после запуска Ollama может занять несколько десятков секунд; перед демонстрацией отправьте пробный вопрос. Локально проверен реальный диалог с `qwen2.5:7b-instruct-q4_0` через Docker и HTTP API.

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

Реализован backend кредитного процесса и необязательный API Савелия. React-интерфейс и финансовые сценарии — следующие этапы. Скоринг, условия продуктов, подпись и выдача демонстрационные; реальных переводов, БКИ/ФНС, финансовых документов и платных API нет. Применены проектные навыки `alfa-credit-build`, `alfa-credit-guardrails`, `django-expert` и PostgreSQL-рекомендации. Юридическая проверка реального банковского сервиса не проводилась. Зависимости перечислены в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
