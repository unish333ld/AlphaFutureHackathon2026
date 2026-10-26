# Контракт для frontend

[Выбранный стек](stack.md). Источник API — Django/DRF-аннотации; [openapi.yaml](openapi.yaml) генерируется с валидацией. Подсказки действий не заменяют проверку прав и состояния в транзакционных сервисах.

API 1.2.0 добавляет `Product.catalog_reference`, `Application.readiness`, `Offer.cost_breakdown/comparison` и `Agreement.cost_breakdown`. Калькулятор принимает product вместо annual_rate для цены каталога. Форматы, источники и совместимость старых снимков — [product-research.md](product-research.md). Все суммы/итоги приходят с сервера; заполненность не является скорингом.

API **1.3.0** развивает этот контракт: приватные PDF/metadata, nullable Agreement.confirmation, документы original/signed_copy, обязательная кодовая попытка на прежнем sign endpoint. Старый hash-only sign больше не работает. Пошаговая интеграция/ошибки/миграция frontend — [agreements.md](agreements.md). Readiness теперь отдельно сообщает verification_state (not_checked/pending/checked/needs_information/technical_error/outdated), checked_at; некорректный показатель имеет state=invalid, не ready.

API **1.4.0**: очередь специалиста и история заявки возвращают до 10 записей на странице. `GET applications/notifications/` отдаёт новые события рассмотрения после cursor; без cursor возвращает только исходную отметку. Помощник работает через `POST assistant/conversations/current/` и `GET/POST assistant/conversations/{id}/step/`: один актуальный шаг, режим choice/input/waiting/result/error, version и step_id. Повторный request_id сверяет серверный журнал; устаревшие шаги и action_id получают 409. Прежние endpoints диалогов сохранены для совместимости, frontend их не вызывает. Кредитные endpoints и available_actions не изменены. Подробнее — [assistant.md](assistant.md).

## Экран сотрудника → API → поля → действия → ограничения

Префикс всех бизнес-маршрутов — `/api/v1/`.

| Экран / элемент | API | Поля и действия | Ограничения |
|---|---|---|---|
| Очередь | `GET staff/applications/` | id, number, company/company_name/company_inn, product/product_name, current_revision_id, amount, term_months, risk_level, status, assigned_to, assigned_at, created_at, updated_at, status_changed_at, lock_version | Активный specialist; без истории ревизий |
| Свободные / мои | Та же очередь: `assignment=free` / `mine` | Реальное назначение; mine — текущий пользователь; default all | Чужое назначение нельзя изменить |
| Фильтры / поиск | `status`, `risk_level`, `search` | Один status; low/medium/high/unassessed; подстрока номера/названия компании/ИНН | Нет Grade A–E, приоритета или SLA |
| Сортировка / страницы | `ordering`, `page` | created_at, updated_at, assigned_at, amount, term_months, number; `-` для убывания; default -created_at | 10 строк, второй ключ id, NULL в конце; неизвестные параметры — 400 |
| Карточка | `GET staff/applications/{id}/` | current_revision_id, revisions, проверки, assessment/decision/offer/agreement/disbursement, available_actions | Текущая ревизия — максимальный revision_no |
| Взять в работу | `POST staff/applications/{id}/claim/` | `{lock_version}`; исполнитель берётся из сессии | checking/review/needs_info/offered/accepted/signed |
| Освободить | `POST staff/applications/{id}/release/` | `{lock_version}` | Только текущий исполнитель; чужая/свободная — 409 |
| Проверить данные | `POST staff/applications/{id}/request-information/` | `{lock_version, question}` → needs_info | Текущий исполнитель; review/checking |
| Решение по правилам | `POST staff/applications/{id}/decide/` | `{lock_version}` → revisions[0].assessment.decision | Текущий исполнитель; review; актуальные проверки/оценка |
| Выдача | `POST agreements/{id}/disburse/` | `{lock_version}` + `Idempotency-Key: <UUID>` | Новая выдача: текущий исполнитель, signed и целые условия |
| История | `GET applications/{id}/events/` | actor/event_type/from_status/to_status/details/created_at | Пагинация; company scope |

В строке очереди amount/term_months/risk_level относятся строго к одной последней ревизии. risk_level=null означает отсутствие оценки у неё, даже если старые оценки есть. Если ревизии нет, current_revision_id/amount/term_months тоже nullable. Клиентский `GET applications/` сохраняет прежний краткий контракт.

Без status очередь включает все сохранённые состояния, включая draft и терминальные. assignment=free означает именно отсутствие исполнителя; для рабочей вкладки комбинируйте его со status (например review). Терминальные заявки автоматически покидают «Мои», но остаются в общей очереди и истории.

`status_changed_at` — фактическое начало текущего кредитного состояния; для черновика — создания. Назначение, освобождение и правка черновика его не сбрасывают. Frontend может показывать длительность состояния; банковский SLA не установлен. Истечение предложения сверяется при чтении карточки/предложения и командой expire_offers; список отражает сохранённое состояние до такой сверки.

## Назначение

Назначение независимо от кредитного статуса. assigned_to — `{id, username, first_name, last_name}` либо null; assigned_at одновременно null либо дата. Все изменения блокируют строку Application и проверяют lock_version. Из двух claim с одной версией проходит один; второй — 409. Повтор claim тем же исполнителем с актуальной версией — 200 без нового события/версии, старая версия — 409. Переназначения нет: исполнитель делает release, затем другой сотрудник claim.

Назначение сохраняется при needs_info, offered, accepted, новой ревизии и подписи. Клиент отвечает, принимает/отклоняет предложение и подписывает независимо от назначения. issued/rejected/declined/expired автоматически его очищают. История: assignment_claimed и assignment_released; reason у освобождения — manual либо terminal_state. В двух ролях нет API административного переназначения деактивированного исполнителя; это ограничение демо.

request-information, decide, банковский retry-checks и новая disburse требуют текущего исполнителя. Клиентский retry-checks требует can_submit. Ответ через `POST applications/{id}/provide-information/` содержит полный набор полей новой ревизии и lock_version; запрос уточнения закрывается, проверки и оценка выполняются заново. `/revise/` из review/offered тоже создаёт новую ревизию и делает старое доступное предложение superseded.

## Доступные действия

Карточки обеих ролей возвращают `available_actions: [{action, allowed, reason_code, target_id}]`. reason_code=null у доступного действия. target_id — заявка для update_draft/submit/retry_checks/provide_information/revise/claim/release/request_information/decide; предложение для accept_offer/decline_offer; договор для sign_agreement/disburse. Если объект не создан, target_id=null. Кнопки строятся по action/allowed; маршруты описаны в OpenAPI.

| Причины | Подсказка |
|---|---|
| role_required / capability_required | Недостаточно роли / полномочий |
| assignment_required / assigned_to_other | Возьмите заявку / она занята другим |
| already_assigned / not_assigned | Уже ваша / назначения нет |
| needs_information | Ожидается ответ новой ревизией |
| technical_error / retry_limit | Ошибка проверки / лимит пяти попыток |
| waiting_for_client / offer_expired | Ожидается клиент / предложение или срок подписи недоступны |
| assessment_unavailable / assessment_outdated / checks_incomplete / no_current_revision | Нет пригодных данных для решения |
| product_unavailable / invalid_terms | Продукт недоступен / условия вне границ |
| terms_mismatch | Условия не совпадают с принятой версией |
| already_completed / invalid_state | Действие завершено / состояние не подходит |

Подсказка может устареть из-за параллельного запроса или времени; сервер повторно проверяет условия операции.

## Решение и JSON

Сотрудник запускает серверную demo-policy-1, не выбирает исход, ставку или сумму. Ответ: текущая ревизия → assessment (revision, checks_attempt, score, risk_level, factors, rules_version) → decision (assessment, outcome, reason_code, explanation, policy_version, offer). Исходы approved/counteroffer создают offer, rejected — offer=null. Повтор после результата — 409 без дублей. Полный набор registry/credit_history/financial должен относиться к той же ревизии/попытке, не содержать missing/error и предшествовать оценке; новая попытка делает старую оценку непригодной.

Деньги — десятичные строки рублей, срок — месяцы, timestamps — UTC ISO 8601. JSON schema_version=1 уточнён в OpenAPI:

- factors: failed_checks (виды проверок), monthly_cashflow, payment_capacity, capacity_fraction="0.50".
- checks.result: registry → registration_status/retryable; credit_history → overdue; financial → missing_fields из трёх финансовых полей.
- input_snapshot: в draft `{}`, после отправки company/product/financial. Сумма/срок/цель — поля самой ревизии.
- schedule: method=demo_annuity_monthly, fees="0.00", rows: month/payment/principal/interest/balance. Последняя строка корректирует копейки; календарных дат и банковских комиссий нет.
- terms_snapshot: принятые offer_id/company_id, сумма/ставка/срок/платёж/schedule и signature_mode=simulation.
- event.details: безопасный allowlist метаданных по event_type, обязательна schema_version; остальные ключи и границы описаны схемой, произвольные документы/секреты не допускаются.

## Session, CSRF и ошибки

1. `GET /api/v1/session/csrf/` с сохранением cookies; взять csrf_token.
2. `POST /api/v1/session/login/` с username/password, cookies и X-CSRFToken.
3. Вход вращает CSRF: использовать новый csrf_token из ответа. sessionid HttpOnly, JavaScript его не читает; запросы используют `credentials: 'include'`.
4. `GET /api/v1/me/` — system_role и memberships с active/can_submit/can_sign. Сервер повторяет проверки на действиях.
5. `POST /api/v1/session/logout/` с новым CSRF → 204; прежняя серверная сессия недействительна.

`/api/session/login/` — служебная HTML-форма для Swagger. `/api/v1/session/` — JSON API. Пути намеренно разные. Swagger/React используют session/CSRF без отключений; один origin обеспечивает будущий Nginx либо Vite proxy. Клиент не назначает себе роль, исполнителя, статус, риск, ставку или решение произвольными полями.

Прокси должен сохранять исходные Host/Origin. Если в разработке он меняет Host, укажите конкретный origin в DJANGO_CSRF_TRUSTED_ORIGINS; проверка CSRF остаётся включённой.

Сохранены форматы DRF: `{detail: string, code?: string}`, ошибки полей `{amount: ["..."]}` либо строки некоторых ручных проверок, non_field_errors; старые общие validation-ответы могут быть массивом строк. Error.anyOf описывает эти формы. API login возвращает JSON при CSRF-ошибке, служебный вход — HTML.

400 — поля/JSON/фильтры; 403 — сессия/права/CSRF; 404 — отсутствующий или скрытый company scope объект/страница; 409 — версия/состояние/назначение/идемпотентность; 429 — лимит, Retry-After; 503 — недоступная БД или таймаут блокировки. health имеет собственный ответ `{status: unavailable, database: unavailable}`. Техническая ошибка синтетической проверки — 200 с checking + check.error, не кредитный отказ. Секреты и traceback не возвращаются.

После изменения заявки берите lock_version из ответа (одно действие может увеличить его несколько раз). После sign/disburse, возвращающих договор/выдачу, выполните GET карточки. При 409 обновите карточку/кеш TanStack Query и дайте пользователю проверить условия; не повторяйте значимое действие автоматически.

Idempotency-Key выдачи обязателен и имеет формат UUID. Семантическое содержимое — договор и его зафиксированные условия. Тот же ключ/договор возвращает ту же запись даже со старым lock_version и после освобождения назначения; версия — токен конкурентности. Дополнительные amount/status запрещены с 400; ключ другого договора или новый ключ после выдачи — 409. UNIQUE ключа/договора и блокировка заявки защищают конкуренцию. Клиент не может выполнить банковскую выдачу.
