# Умный кредитный кабинет предпринимателя

Прототип кредитного процесса для предпринимателя и специалиста банка. Включает заявки и уточнения, проверку данных, серверное решение, предложения, PDF-договор, условное подтверждение подписью и моделируемую выдачу. Все данные синтетические; SMS, электронная подпись и перевод денег не выполняются.

## Быстрый запуск для жюри

Нужны Docker Engine с Compose v2 и интернет для первоначальной загрузки образов и зависимостей. Python, Node.js и PostgreSQL на компьютере устанавливать не требуется.

Из корня скачанного проекта:

```sh
test -f .env || cp .env.example .env
docker compose -p alfa-credit-jury up --build -d --wait --wait-timeout 300
docker compose -p alfa-credit-jury ps
```

При первом старте контейнер применит миграции, создаст синтетические компании, продукты и тестовые учётные записи. Откройте приложение: **http://localhost:8080**. Swagger UI: **http://localhost:8080/api/docs/**. OpenAPI: **http://localhost:8080/api/schema/**. Проверка API: **http://localhost:8080/api/v1/health/**.

В `.env.example` уже заданы локальные значения, необходимые для показа. Пароль одинаковый для тестовых пользователей: `AlfaHack2026!Demo`.

| Роль | Логин |
|---|---|
| Клиент | `client` |
| Кредитный специалист | `specialist` |

Это открытые синтетические учётные данные для локального показа. Контейнеры публикуются только на loopback. Не используйте эти значения в интернете или реальной системе. Не заменяйте логин эксперта по догадке: сверяйтесь с официальными указаниями организаторов.

### Сценарий показа двумя ролями

Откройте клиентский и специалистский кабинеты в разных браузерах или изолированных профилях, чтобы не смешивать сессии.

1. Войдите как `client`, создайте заявку на компанию **Рост** и продукт **Оборотные средства**: сумма **1 000 000 ₽**, срок **24 месяца**, цель «Оборотные средства», месячная выручка **1 500 000 ₽**, расходы **900 000 ₽**, платежи по обязательствам **50 000 ₽**. Отправьте заявку.
2. Войдите во втором профиле как `specialist`. Найдите заявку в очереди, нажмите **«Взять в работу»**, затем **«Принять решение по правилам»**.
3. Вернитесь в профиль клиента, откройте заявку и примите предложение.
4. Откройте PDF договора, отметьте ознакомление и подтвердите действие автоматически показанным демо-кодом.
5. В профиле специалиста выполните **«Моделировать выдачу»**. Клиент увидит результат в карточке заявки.

Для стабильного одобрения используйте именно указанные синтетические вводные. Решение и окончательные условия формирует сервер. Подпись и выдача — только симуляция, реального SMS и перевода денег нет.

Остановка без удаления данных: `docker compose -p alfa-credit-jury stop`. Повторный запуск: `docker compose -p alfa-credit-jury start`. Не используйте `down -v`, если хотите сохранить локальные демонстрационные данные. Если `.env` уже существует, не перезаписывайте его.

Если заняты порты 8000 или 8080, задайте другие до запуска, например:

```sh
WEB_PORT=18100 FRONTEND_PORT=18180 docker compose -p alfa-credit-jury up --build -d --wait --wait-timeout 300
```

Тогда откройте **http://localhost:18180** и Swagger **http://localhost:18180/api/docs/**. При проблемах смотрите `docker compose -p alfa-credit-jury ps` и `docker compose -p alfa-credit-jury logs --tail=100 web`; миграции и создание тестовых данных выполняются сервисом `web` автоматически. Для подробной диагностики см. [backend demo](docs/backend-demo.md).

### Необязательный ИИ-помощник

Основной кредитный сценарий работает без ИИ, ключей и загрузки модели. Чтобы включить помощника с OpenRouter, установите в `.env` `AI_ENABLED=true`, `VITE_AI_ASSISTANT_ENABLED=true`, `LLM_PROVIDER=openrouter`, `LLM_BASE_URL=https://openrouter.ai/api/v1`, `LLM_MODEL=nvidia/nemotron-3-super-120b-a12b:free` и свой `OPENROUTER_API_KEY` с [страницы ключей](https://openrouter.ai/settings/keys); затем пересоберите сервисы командой запуска выше. Это [NVIDIA Nemotron 3 Super 120B A12B FP8](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8), доступная через [OpenRouter](https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free); лицензия — [NVIDIA Nemotron Open Model License](https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-nemotron-open-model-license/). Бесплатный маршрут может быть нестабилен или временно недоступен; ключ храните только в локальном `.env`.

Без облачного ключа можно отдельно установить Ollama и скачать командой `ollama pull qwen3:4b-instruct-2507-q4_K_M` модель Qwen3-4B-Instruct-2507; источник весов — [Hugging Face](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507), лицензия [Apache 2.0](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/main/LICENSE). В `.env` задайте `LLM_PROVIDER=compatible`, `LLM_BASE_URL=http://host.docker.internal:11434/v1`, `LLM_MODEL=qwen3:4b-instruct-2507-q4_K_M` и оба флага `AI_ENABLED=true`, `VITE_AI_ASSISTANT_ENABLED=true`. На Linux укажите адрес хоста, доступный контейнеру. Чтобы отключить помощника, верните оба флага в `false` и пересоберите frontend. Модель не входит в Compose и не нужна для основного сценария. Инструкция: [docs/assistant.md](docs/assistant.md); лицензии зависимостей и моделей: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Документация и проверки

[Стек и границы релиза](docs/stack.md) · [Архитектура](docs/architecture.md) · [OpenAPI](docs/openapi.yaml) · [Интеграция frontend/backend](docs/frontend-integration.md) · [Продуктовые исследования](docs/product-research.md) · [PDF и подпись](docs/agreements.md) · [Итоговый QA](docs/qa-product-research.md) · [Проверка frontend](docs/frontend-polish-qa.md) · [Проверки входа](docs/qa-auth-verification.md).

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
| `backend/assistant/models.py` | Conversation, Message, Interaction, AssistantQuota |

Модель данных и связи: [docs/data-model.md](docs/data-model.md). Архитектура, состояния и допущения: [docs/architecture.md](docs/architecture.md). Пошаговые запросы: [docs/demo.http](docs/demo.http). Сгенерированная схема: [docs/openapi.yaml](docs/openapi.yaml). Проверки: [docs/verification.md](docs/verification.md).

## Дополнительные материалы

Точный API-контракт и примеры запросов: [OpenAPI](docs/openapi.yaml), [коллекция запросов](docs/demo.http), [интеграция frontend/backend](docs/frontend-integration.md). В тестовых данных есть заявки для одобрения, встречного предложения, уточнения, отказа и технической ошибки. [Документация помощника](docs/assistant.md) описывает сценарий, настройку и ограничения.

## Локальная разработка и проверки

Требуются Python 3.14 и PostgreSQL 18. Для PDF также нужны системные Pango/HarfBuzz и локальные DejaVu Serif; они уже включены в Docker. Native-подготовка и `PDF_FONT_DIR` — [docs/agreements.md](docs/agreements.md). Создайте отдельную БД и пользователя, настройте `DB_*` в `.env`. Для создания тестовой БД пользователь должен иметь `CREATEDB`; при публичном запуске нужны отдельные ограниченные полномочия.

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

В контейнере базовый набор: `docker compose exec web pytest -c /app/pyproject.toml`. Инструменты покрытия устанавливаются отдельно из `requirements-test.lock`; `coverage.patch=subprocess` учитывает настоящий PDF-worker, а не исключает его. Для безопасной полной проверки используйте отдельный Compose project и временный тестовый venv по [docs/qa-product-research.md](docs/qa-product-research.md), не пользовательскую демо-базу. Истечение предложений обрабатывается при чтении карточки/предложения и командой `python manage.py expire_offers`. Новые данные после рассмотрения отправляются через `/revise/`, ответ на уточнение — через `/provide-information/`. Seeds идемпотентны. `seed_demo --reset-passwords` обновляет пароли только четырёх демо-пользователей.

## Границы версии

Реализованы backend и React-интерфейс. Помощник — необязательный пошаговый сценарий с Django API и выдвижной панелью React (`AI_ENABLED=false` и `VITE_AI_ASSISTANT_ENABLED=false` по умолчанию). Прогноз денежных потоков и стресс-тесты — следующий продуктовый этап; SLA и сложная приоритизация вне релиза. Скоринг, условия продуктов, подпись и выдача демонстрационные; реальных переводов, БКИ/ФНС, финансовых документов и платных API нет. Применены `alfa-credit-frontend`, `alfa-credit-build`, `alfa-credit-guardrails`, React- и Playwright-рекомендации; для backend — `django-expert` и PostgreSQL-рекомендации. Юридическая проверка реального банковского сервиса не проводилась. Зависимости перечислены в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
