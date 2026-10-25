from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import AppendOnlyModel


class Assessment(AppendOnlyModel):
    class Risk(models.TextChoices):
        LOW = "low", "Низкий"
        MEDIUM = "medium", "Средний"
        HIGH = "high", "Высокий"

    revision = models.OneToOneField(
        "applications.ApplicationRevision", on_delete=models.PROTECT, related_name="assessment"
    )
    score = models.PositiveSmallIntegerField(
        "Демо-скор", validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    risk_level = models.CharField("Риск", max_length=8, choices=Risk)
    factors = models.JSONField("Факторы оценки (v1)", default=dict)
    rules_version = models.CharField("Версия скоринга", max_length=32)
    checks_attempt = models.PositiveIntegerField("Использованная попытка проверок", default=1)

    class Meta:
        verbose_name = "Оценка риска"
        verbose_name_plural = "Оценки риска"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(score__lte=100), name="assessment_score_bounds"
            ),
            models.CheckConstraint(
                condition=models.Q(checks_attempt__gte=1), name="assessment_attempt_positive"
            ),
        ]


class CreditDecision(AppendOnlyModel):
    class Outcome(models.TextChoices):
        APPROVED = "approved", "Одобрение"
        COUNTEROFFER = "counteroffer", "Встречные условия"
        REJECTED = "rejected", "Отказ"

    assessment = models.OneToOneField(Assessment, on_delete=models.PROTECT, related_name="decision")
    outcome = models.CharField("Решение", max_length=16, choices=Outcome)
    reason_code = models.CharField("Код причины", max_length=64)
    explanation = models.TextField("Объяснение")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="credit_decisions",
    )
    policy_version = models.CharField("Версия кредитной политики", max_length=32)

    class Meta:
        verbose_name = "Кредитное решение"
        verbose_name_plural = "Кредитные решения"
