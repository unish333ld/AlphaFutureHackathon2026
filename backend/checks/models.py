from django.db import models

from common.models import AppendOnlyModel


class CheckResult(AppendOnlyModel):
    class Kind(models.TextChoices):
        REGISTRY = "registry", "Регистрационный статус"
        CREDIT_HISTORY = "credit_history", "Кредитная история"
        FINANCIAL = "financial", "Финансовые данные"

    class Status(models.TextChoices):
        PASSED = "passed", "Проверка пройдена"
        FAILED = "failed", "Негативный результат"
        MISSING = "missing", "Недостаточно данных"
        ERROR = "error", "Техническая ошибка"

    revision = models.ForeignKey(
        "applications.ApplicationRevision", on_delete=models.PROTECT, related_name="checks"
    )
    kind = models.CharField("Тип", max_length=20, choices=Kind)
    status = models.CharField("Результат", max_length=10, choices=Status)
    attempt = models.PositiveIntegerField("Попытка", default=1)
    result = models.JSONField("Результат адаптера (v1)", default=dict)
    source = models.CharField("Источник", max_length=64, default="local-synthetic-v1")
    is_mock = models.BooleanField("Локальный мок", default=True)
    checked_at = models.DateTimeField("Проверено", auto_now_add=True)

    class Meta:
        ordering = ["attempt", "kind"]
        verbose_name = "Результат проверки"
        verbose_name_plural = "Результаты проверок"
        constraints = [
            models.UniqueConstraint(
                fields=["revision", "kind", "attempt"], name="unique_check_attempt"
            ),
            models.CheckConstraint(
                condition=models.Q(attempt__gte=1), name="check_positive_attempt"
            ),
        ]
