# Инструкции проекта

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
