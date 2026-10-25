# Демонстрация backend

[Стек и границы](stack.md); [контракт frontend](frontend-integration.md). Новые миграции сохраняют существующие данные; перед банковскими действиями требуется claim.

Проверенный Compose-проект: `alfa-credit-demo`. На этой машине он запущен на порту **18000**. Обычный запуск без `WEB_PORT` использует порт 8000.

## Запустить

Из корня проекта, с работающим Docker Desktop и заполненным `.env` по README:

```sh
WEB_PORT=18000 docker compose -p alfa-credit-demo up --build -d --wait --wait-timeout 120
WEB_PORT=18000 docker compose -p alfa-credit-demo ps
```

Оба сервиса должны показывать `healthy`. При первом запуске автоматически применяются миграции, собираются локальные ресурсы Swagger/ReDoc и создаются синтетические профили.

- Вход: http://localhost:18000/api/session/login/
- Swagger: http://localhost:18000/api/docs/
- ReDoc: http://localhost:18000/api/redoc/
- OpenAPI: http://localhost:18000/api/schema/
- Health: http://localhost:18000/api/v1/health/

Профили: `client`, `specialist`, `accountant`, `outsider`. Пароль берётся из `DEMO_PASSWORD` в `.env`; скрипт проверки читает его из окружения контейнера. Клиент и специалист не являются администраторами Django.

## Автоматически проверить работающий backend

```sh
WEB_PORT=18000 docker compose -p alfa-credit-demo exec -T web python /app/scripts/demo_smoke.py
```

Проверка выполняет настоящие HTTP-запросы к Gunicorn: Swagger/ReDoc и пять static-ресурсов, OpenAPI, cookie/CSRF, запрет подмены статуса и неверного JSON, очередь свободных/моих, claim/release, подсказки действий, пять кредитных сценариев, подпись и выдачу, идемпотентный повтор и изоляцию чужой компании.

Она добавляет **пять новых синтетических заявок и одну моделируемую выдачу**. Исходные пять черновиков остаются доступными для ручной демонстрации. Успех — JSON с `status: ok` и UUID созданных заявок. Повторный запуск создаёт новый набор записей.

После перезапуска можно проверить ранее выданную заявку: добавьте `--verify-application UUID`, подставив значение `approval_application_id` из вывода. Этот режим читает сохранённую заявку и выдачу, проверяет документацию и не создаёт новых заявок.

## Пройти основной путь в Swagger

1. Войдите как `client` через страницу входа. Она перенаправит в Swagger с обновлённым CSRF-токеном. `GET /api/v1/applications/?status=draft`: выберите компанию `Демо · Рост`, сохраните UUID заявки и `lock_version`.
2. `POST /applications/{id}/submit/` с текущим `lock_version`. Ожидаемое состояние — `review`. Все проверки и оценка доступны в `revisions` карточки.
3. В отдельном профиле браузера или приватном окне войдите как `specialist`. `GET /staff/applications/{id}/`, затем `POST /staff/applications/{id}/claim/` с актуальной версией. Из ответа возьмите новый lock_version и вызовите `/decide/`. Ожидаются offered, approved и предложение. Кнопки и причины недоступности описаны в available_actions; свободные/мои — `GET /staff/applications/?assignment=free` / `mine`.
4. Как клиент: `GET /applications/{id}/`, затем `POST /offers/{id}/accept/`. В ответе — договор и `document_hash`.
5. Как клиент: `POST /agreements/{id}/sign/` с актуальным `lock_version`, принятым `document_hash` и `confirm_simulation=true`. После подписи загрузите карточку заявки заново, чтобы получить новую версию.
6. Как назначенный специалист: `POST /agreements/{id}/disburse/` с новой версией и любым UUID в заголовке `Idempotency-Key`. Выдача имеет is_simulated=true; заявка переходит в issued и освобождает назначение.
7. Повторите последний запрос с тем же ключом: ответ содержит ту же выдачу. Войдите как `outsider`: чужая заявка недоступна.

Тело действия с версией:

```json
{"lock_version": 0}
```

Число заменяйте текущим значением из карточки; отправка может выполнить несколько переходов и увеличить версию больше чем на один. Ответ `409` означает необходимость обновить состояние.

Другие исходные черновики: `Мастерская` — меньшая сумма, `Уточнение` — запрос финансовых данных и новая ревизия, `Проверка риска` — отказ, `Повтор проверки` — состояние `checking` и последующий `retry-checks`.

## Тесты и перезапуск

```sh
WEB_PORT=18000 docker compose -p alfa-credit-demo exec -T web pytest -c /app/pyproject.toml /app/backend/tests -o cache_dir=/tmp/pytest-cache
WEB_PORT=18000 docker compose -p alfa-credit-demo exec -T web python manage.py check
```

Тесты создают отдельную тестовую БД. Генерация HTML-покрытия в локальном окружении описана в README.

Пересоздать контейнеры, сохранив PostgreSQL-том:

```sh
WEB_PORT=18000 docker compose -p alfa-credit-demo up -d --force-recreate --wait --wait-timeout 120
```

Остановить демо с сохранением данных:

```sh
WEB_PORT=18000 docker compose -p alfa-credit-demo stop
```

Для этой демонстрации PostgreSQL доступен только внутри Compose, веб-порт привязан к `127.0.0.1`, Django работает с `DEBUG=false`, Gunicorn — от пользователя `credit` с UID 10001.
