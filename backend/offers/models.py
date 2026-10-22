from django.core.exceptions import ValidationError
from django.db import models

from common.models import CreatedModel


class Offer(CreatedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Доступно"
        ACCEPTED = "accepted", "Принято"
        DECLINED = "declined", "Отклонено"
        EXPIRED = "expired", "Истекло"
        SUPERSEDED = "superseded", "Заменено новой ревизией"

    decision = models.OneToOneField(
        "decisions.CreditDecision", on_delete=models.PROTECT, related_name="offer"
    )
    product = models.ForeignKey(
        "products.CreditProduct", on_delete=models.PROTECT, related_name="offers"
    )
    amount = models.DecimalField("Сумма, ₽", max_digits=18, decimal_places=2)
    annual_rate = models.DecimalField("Годовая ставка, %", max_digits=7, decimal_places=4)
    term_months = models.PositiveSmallIntegerField("Срок, месяцев")
    monthly_payment = models.DecimalField("Регулярный платёж, ₽", max_digits=18, decimal_places=2)
    schedule = models.JSONField("Упрощённый график по номерам месяцев (v1)")
    status = models.CharField("Состояние", max_length=16, choices=Status, default=Status.AVAILABLE)
    expires_at = models.DateTimeField("Принять до")
    accepted_at = models.DateTimeField(null=True, blank=True)
    sign_before = models.DateTimeField("Условно подписать до", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = "Предложение"
        verbose_name_plural = "Предложения"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    amount__gt=0,
                    monthly_payment__gt=0,
                    term_months__gte=1,
                    term_months__lte=120,
                    annual_rate__gte=0,
                    annual_rate__lte=100,
                ),
                name="offer_valid_terms",
            ),
        ]
        indexes = [models.Index(fields=["status", "expires_at"], name="offer_expiration_idx")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            fields = [
                "decision_id",
                "product_id",
                "amount",
                "annual_rate",
                "term_months",
                "monthly_payment",
                "schedule",
                "expires_at",
            ]
            old = type(self).objects.values(*fields).get(pk=self.pk)
            if any(old[field] != getattr(self, field) for field in fields):
                raise ValidationError("Условия выпущенного предложения неизменяемы.")
        return super().save(*args, **kwargs)
