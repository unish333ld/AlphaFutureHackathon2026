# Инструкции проекта

## Стек и текущий релиз

Следовать [docs/stack.md](docs/stack.md): Python/Django/DRF, PostgreSQL; frontend React, TypeScript strict, Vite; Core Components Альфа-Банка; CSS Modules, Grid, Flexbox, медиазапросы; React Router, TanStack Query, React Hook Form/Zod. Авторизация — Django sessions, HttpOnly cookie и CSRF. API — drf-spectacular/OpenAPI/Swagger UI. Запуск — Docker Compose, Nginx для frontend и API proxy. Проверки — pytest/pytest-django, frontend — Vitest/Playwright. Инструкции запуска frontend: [docs/frontend.md](docs/frontend.md).

Bootstrap и другие CSS/UI-фреймворки в основной интерфейс не добавлять; стандартный Django Admin и служебный HTML-вход сохранять. Не добавлять FastAPI, микросервисы, PyTorch и frontend-пакеты в Python-lock. Текущий релиз использует синтетические данные, локальные моки, условную подпись и выдачу; без прогноза денежных потоков и backend LLM. ИИ — только отключаемая визуальная заготовка frontend. [Контракт интеграции](docs/frontend-integration.md). Сохранять пользовательский ввод при 409; не повторять значимые операции автоматически. Ключ моделируемой выдачи хранить до запроса в sessionStorage с областью user/agreement, повтор — только осознанно с тем же ключом после сверки сервера. Не хранить финансовые payload, пароли и session cookies в Web Storage.

## Сообщения коммитов

Следовать [Conventional Commits Cheatsheet от qoomon](https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13) по пожеланию владельца проекта.

Формат:

```text
<type>(<scope>)!: <description>

<optional body>

<optional footer>
```

- `type` обязателен: `feat`, `fix`, `refactor`, `perf`, `style`, `test`, `docs`, `build`, `ops`, `chore`.
- `feat` — изменение функциональности API/UI; `fix` — исправление ошибки; `refactor` — изменение структуры без изменения поведения; `perf` — оптимизация.
- `style` — форматирование; `test` — тесты; `docs` — документация; `build` — сборка и зависимости; `ops` — инфраструктура, развёртывание и CI/CD; `chore` — служебные задачи.
- `scope` необязателен; выбирать предметный модуль или область: `accounts`, `companies`, `products`, `applications`, `checks`, `decisions`, `offers`, `agreements`, `api`, `frontend`, `infra`. Номер задачи не использовать как scope.
- Описание писать на английском, кратко, в повелительной форме, со строчной буквы и без точки в конце.
- Body при необходимости объясняет причину изменения и прежнее поведение; отделять его пустой строкой.
- Для несовместимого изменения ставить `!` перед двоеточием и добавлять footer `BREAKING CHANGE:` с объяснением последствий и перехода на новую версию.
- Ссылки на задачи при наличии указывать в footer, например `Closes #123`.
- Для начального коммита использовать `chore: init`. Для обычных merge/revert допустимы стандартные сообщения Git.

Примеры для проекта:

```text
feat(applications): add application revision workflow
fix(agreements): prevent duplicate disbursement
docs(api): document session authentication in swagger
build(backend): update django rest framework
```
