"""Completeness hints; these do not predict approval or replace action checks."""

from decimal import Decimal, InvalidOperation

from applications.actions import available_actions, latest_revision

FINANCIAL_LABELS = {
    "monthly_revenue": "Выручка за месяц",
    "monthly_expenses": "Операционные расходы за месяц, включая налоги, без долгового сервиса",
    "monthly_debt_payments": "Платежи по действующим обязательствам за тот же месяц",
}


def application_readiness(app, user, *, actions=None):
    revision = latest_revision(app)

    def state(field):
        value = getattr(revision, field) if revision else None
        if value is None:
            return "missing"
        try:
            number = Decimal(str(value))
            return "ready" if number.is_finite() and number >= 0 else "invalid"
        except InvalidOperation:
            return "invalid"

    verification = "not_checked"
    checked_at = None
    if revision and revision.submitted_at:
        checks = list(revision.checks.all())
        attempt = max((check.attempt for check in checks), default=0)
        financial = next(
            (check for check in checks if check.attempt == attempt and check.kind == "financial"),
            None,
        )
        assessment = getattr(revision, "assessment", None)
        if not financial:
            verification = "pending"
        elif financial.status == "error":
            verification = "technical_error"
        elif financial.status == "missing":
            verification = "needs_information"
        elif assessment and assessment.checks_attempt != attempt:
            verification = "outdated"
        else:
            verification = "checked"
        checked_at = financial.checked_at.isoformat() if financial else None
    messages = {
        "not_checked": "Сведения пока не проверены: это черновик.",
        "pending": "Проверка актуальной ревизии ещё не завершена.",
        "technical_error": "Техническая ошибка проверки — это не кредитный отказ.",
        "needs_information": "Для проверки нужны сведения клиента.",
        "outdated": "Результаты не соответствуют текущей попытке; требуется актуальная оценка.",
        "checked": "Финансовая проверка этой ревизии смоделирована; это не подтверждение реальных данных банка.",
    }
    items = [
        {
            "field": field,
            "state": state(field),
            "label": label,
            "message": "Некорректный показатель: уточните число не меньше нуля."
            if state(field) == "invalid"
            else "Указано клиентом; проверяется в кредитном процессе."
            if revision is not None and getattr(revision, field) is not None
            else "Уточните показатель в форме. Неизвестное значение нельзя заменять нулём.",
        }
        for field, label in FINANCIAL_LABELS.items()
    ]
    actions = available_actions(app, user) if actions is None else actions
    submit = next((a for a in actions if a["action"] == "submit"), None)
    return {
        "schema_version": 1,
        "revision_id": str(revision.pk) if revision else None,
        "lock_version": app.lock_version,
        "can_submit": bool(submit and submit["allowed"]),
        "submit_reason_code": submit["reason_code"] if submit else "invalid_state",
        "financial_data_complete": all(item["state"] == "ready" for item in items),
        "items": items,
        "verification_state": verification,
        "verification_message": messages[verification],
        "checked_at": checked_at,
        "disclosure": "Это заполненность месячных показателей, не вероятность одобрения. Заявку можно отправить с неизвестными показателями: банк запросит уточнение.",
    }
