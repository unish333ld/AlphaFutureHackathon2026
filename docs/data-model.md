# Модель данных

Стек и границы: [stack.md](stack.md). Семантика полей/назначений и JSON: [frontend-integration.md](frontend-integration.md), точные типы — [openapi.yaml](openapi.yaml).

Предметные идентификаторы — UUID. Денежные колонки — `NUMERIC(18,2)`, ставка — `NUMERIC(7,4)`, срок — месяцы, timestamps — timezone-aware UTC. API возвращает деньги десятичными строками. ИНН — строка; seeds используют заведомо синтетические номера.

```mermaid
erDiagram
    User ||--o{ CompanyMember : has
    Company ||--o{ CompanyMember : grants
    Company ||--o{ Application : submits
    User ||--o{ Application : creates
    User o|--o{ Application : assigned_to
    CreditProduct ||--o{ Application : configures
    Application ||--|{ ApplicationRevision : versions
    Application ||--|{ ApplicationEvent : records
    ApplicationRevision ||--o{ InformationRequest : receives
    ApplicationRevision ||--o{ CheckResult : checks
    ApplicationRevision ||--o| Assessment : assesses
    Assessment ||--o| CreditDecision : produces
    CreditDecision ||--o| Offer : offers
    CreditProduct ||--o{ Offer : identifies
    Offer ||--o| Agreement : accepts
    Agreement ||--o| Disbursement : simulates
    User ||--o{ Conversation : owns
    Company ||--o{ Conversation : scopes
    Application o|--o{ Conversation : contextualizes
    CreditProduct o|--o{ Conversation : selected_product
    Conversation ||--o{ Message : stores
    User ||--o| AssistantQuota : limits
```

| Модель | Поля и ограничения |
|---|---|
| User | UUID, username unique, system_role client/specialist, is_active. is_staff управляет Admin, а не кредитными действиями |
| Company | inn unique, name, kind, registered_at, status, is_existing_client, demo_scenario |
| CompanyMember | user/company PROTECT, unique(user,company), role, can_submit, can_sign, active |
| CreditProduct | code unique, min/max_amount, min/max_term_months, annual_rate, rules_version, active. CHECK границ и ставки 0–100% |
| Application | UUID, number unique AC- + 16 hex, company/product/created_by PROTECT, status, lock_version, status_changed_at, timestamps; assigned_to nullable User PROTECT, assigned_at nullable. CHECK пары назначения; индексы очереди, исполнителя/статуса/даты и списка компании |
| ApplicationRevision | unique(application,revision_no), amount/term/purpose, monthly_revenue/expenses/debt_payments, submitted_at, input_snapshot. CHECK положительных условий и неотрицательных финансов |
| InformationRequest | revision, requested_by, question, response_revision OneToOne nullable, responded_at |
| CheckResult | unique(revision,kind,attempt), status, result, source, is_mock, checked_at. error отделён от failed |
| Assessment | revision OneToOne, score 0–100, risk_level low/medium/high, factors, rules_version, checks_attempt>=1. Решение использует только актуальную полную попытку проверок своей ревизии |
| CreditDecision | assessment OneToOne, outcome, reason_code, explanation, decided_by SET_NULL, policy_version |
| Offer | decision OneToOne, product, amount/rate/term, monthly_payment, schedule, status, expires_at/accepted_at/sign_before |
| Agreement | offer OneToOne, number unique, terms_snapshot, document_hash, signed_by PROTECT, signed_at, signature_mode=simulation. CHECK согласованности подписи |
| Disbursement | agreement OneToOne, idempotency_key unique, amount>0, status=completed, issued_at, is_simulated=true |
| ApplicationEvent | application PROTECT, actor SET_NULL, event_type, from/to_status, details, created_at. Индекс истории |
| Conversation | user/company PROTECT, application nullable PROTECT, selected_product nullable SET_NULL; UUID, version, created_at/updated_at. Только владелец с действующим членством видит историю |
| Message | conversation PROTECT, role user/assistant, content, facts, suggested_draft, reply_type, questions, application_version, model_status. Append-only до явного сервисного удаления диалога/очистки истории |
| AssistantQuota | user OneToOne CASCADE, window_start, requests. Транзакционная квота, общая для workers, без содержания сообщений |

JSON-снимки имеют `schema_version=1`, формируются сервером из валидированных полей и не принимают произвольное содержимое от клиента. `input_snapshot` фиксирует компанию, настройки продукта и месячные финансы. Сумма/цель/срок остаются колонками ревизии. `schedule` содержит метод расчёта, комиссии и строки по номерам месяцев. `terms_snapshot` фиксирует принятое предложение и график; SHA-256 вычисляется по каноническому JSON с сортировкой ключей.

Миграция applications.0002 добавляет поля без сброса существующих заявок: каждому присваивается уникальный номер, status_changed_at восстанавливается по последнему кредитному переходу (иначе created_at), назначение изначально пустое. decisions.0002 восстанавливает checks_attempt по последней попытке до создания оценки. Начальные миграции не переписывались. Номер — серверный идентификатор для отображения/поиска, не последовательность и не рейтинг.

Межтабличные инварианты выполняют транзакционные сервисы: членство автора, актуальная ревизия, принятие и подпись конкретных условий, равенство суммы выдачи договору. Блокировка `Application` сериализует переходы. Уникальные ограничения дополнительно защищают оценки, решения, договоры и выдачи.

Отправленная ревизия и зафиксированные условия защищены от обычного `save`; проверки/оценки/решения/события/выдачи используют append-only поведение. История не редактируется API или Admin. Удаление компании/пользователя не каскадирует финансовую историю. Прямой SQL/QuerySet.update остаётся привилегированной операцией и может обойти Python-защиту; физическая неизменяемость БД не заявляется.

Миграции assistant.0001–0003 добавляют диалоги, типизированные метаданные и квоты без изменения кредитного процесса. Финансовые payload из чата в Web Storage не сохраняются. Переписка имеет отдельную политику хранения: 7 дней неактивности по умолчанию, явное удаление пользователем и `purge_assistant_history`; это не удаляет кредитные события. Подробности — [assistant.md](assistant.md).
