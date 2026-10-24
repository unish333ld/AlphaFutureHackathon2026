# Выбранный стек и границы релиза

Актуальное решение владельца на 24.10.2026. Реализованы Django backend, React frontend и Nginx; зависимости frontend закреплены отдельным package-lock.json.

| Область | Выбор |
|---|---|
| Backend | Python, Django, Django REST Framework; модульный монолит |
| База | PostgreSQL, Django ORM, миграции |
| Frontend | React, TypeScript с `strict: true`, Vite |
| UI | Core Components Альфа-Банка |
| Собственные стили | CSS Modules, CSS Grid, Flexbox, медиазапросы |
| Маршрутизация | React Router |
| Серверные данные | TanStack Query |
| Формы | React Hook Form, Zod; повторная серверная валидация |
| Авторизация | Django sessions, HttpOnly session cookie и CSRF; один origin |
| Документация API | drf-spectacular, OpenAPI, Swagger UI |
| Запуск | Docker Compose; Nginx для frontend и проксирования API |
| Проверки | pytest/pytest-django; Vitest и Playwright для frontend |

Документация: [Core Components](https://core-ds.github.io/core-components/master/?path=/docs/intro--docs). Bootstrap и другие CSS/UI-фреймворки в основной интерфейс не добавляются. Django Admin и служебный HTML-вход Swagger сохранены.

Compose запускает Django/Gunicorn, PostgreSQL и Nginx. Nginx отдаёт сборку Vite и проксирует `/api/`, `/admin/`, backend `/static/`; для разработки используется Vite proxy под одним origin. Frontend-зависимости не добавляются в Python-lock. React 18.3.1 поддерживается peerDependencies Core Components 50.38.0. У транзитивного react-virtual 2 есть устаревшее ограничение React 16/17: npm сообщает предупреждение; используется nativeSelect, без виртуализированного списка. Подробности и проверки — [frontend.md](frontend.md).

Текущий релиз: синтетические данные, локальные моки банковских проверок, условная подпись и моделируемая выдача. Риск — low/medium/high, без Grade A–E. `status_changed_at` показывает начало текущего состояния, но не банковский SLA. Прогноз денежных потоков, сложная приоритизация и отчётность вне релиза; обычный калькулятор платежа сохранён. ИИ — только отключаемая визуальная заготовка frontend, без backend LLM-интеграции. FastAPI, микросервисы, PyTorch и дополнительные инфраструктурные компоненты не требуются.
