from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from common.models import AppendOnlyModel, CreatedModel


class Agreement(CreatedModel):
    offer = models.OneToOneField("offers.Offer", on_delete=models.PROTECT, related_name="agreement")
    number = models.CharField("Номер демо-договора", max_length=48, unique=True)
    terms_snapshot = models.JSONField("Зафиксированные условия (v1)")
    document_hash = models.CharField("SHA-256 условий", max_length=64)
    signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="signed_agreements",
    )
    signed_at = models.DateTimeField("Условно подписан", null=True, blank=True)
    signature_mode = models.CharField(
        "Способ подписи", max_length=16, default="simulation", editable=False
    )

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = "Демо-договор"
        verbose_name_plural = "Демо-договоры"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(signature_mode="simulation"), name="agreement_simulation_only"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(signed_by__isnull=True, signed_at__isnull=True)
                    | models.Q(signed_by__isnull=False, signed_at__isnull=False)
                ),
                name="agreement_signature_pair",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            fields = ["offer_id", "number", "terms_snapshot", "document_hash", "signature_mode"]
            if old.signed_at or any(
                getattr(old, field) != getattr(self, field) for field in fields
            ):
                raise ValidationError("Зафиксированные условия и подписанный договор неизменяемы.")
        return super().save(*args, **kwargs)


class Disbursement(AppendOnlyModel):
    agreement = models.OneToOneField(
        Agreement, on_delete=models.PROTECT, related_name="disbursement"
    )
    amount = models.DecimalField("Моделируемая сумма выдачи, ₽", max_digits=18, decimal_places=2)
    status = models.CharField("Состояние", max_length=16, default="completed", editable=False)
    idempotency_key = models.UUIDField("Ключ идемпотентности", unique=True)
    issued_at = models.DateTimeField("Моделируемая выдача", auto_now_add=True)
    is_simulated = models.BooleanField(default=True, editable=False)

    class Meta:
        ordering = ["-issued_at", "id"]
        verbose_name = "Моделируемая выдача"
        verbose_name_plural = "Моделируемые выдачи"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0, is_simulated=True, status="completed"),
                name="disbursement_demo_only",
            )
        ]
