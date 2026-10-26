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


class AgreementDocument(AppendOnlyModel):
    """Private immutable bytes, deliberately not a public MEDIA_URL file."""

    class Kind(models.TextChoices):
        ORIGINAL = "original", "Исходный договор"
        SIGNED_COPY = "signed_copy", "Копия с отметкой демо-подтверждения"

    agreement = models.ForeignKey(Agreement, on_delete=models.PROTECT, related_name="documents")
    kind = models.CharField(max_length=16, choices=Kind)
    version = models.PositiveIntegerField(default=1)
    template_version = models.CharField(max_length=48)
    calculator_version = models.CharField(max_length=48)
    snapshot = models.JSONField()
    terms_hash = models.CharField(max_length=64)
    pdf_sha256 = models.CharField(max_length=64)
    pdf_data = models.BinaryField(editable=False)
    source_document = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, related_name="copies"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["agreement", "kind", "version"], name="unique_agreement_document"
            ),
            models.CheckConstraint(condition=models.Q(version=1), name="agreement_document_v1"),
            models.CheckConstraint(
                condition=(
                    models.Q(kind="original", source_document__isnull=True)
                    | models.Q(kind="signed_copy", source_document__isnull=False)
                ),
                name="agreement_document_source",
            ),
        ]


class SignatureAttempt(CreatedModel):
    class State(models.TextChoices):
        PENDING = "pending", "Ожидает код"
        CANCELLED = "cancelled", "Отменена"
        EXPIRED = "expired", "Истекла"
        LOCKED = "locked", "Попытки исчерпаны"
        USED = "used", "Использована"

    agreement = models.ForeignKey(
        Agreement, on_delete=models.PROTECT, related_name="signature_attempts"
    )
    document = models.ForeignKey(AgreementDocument, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT)
    lock_version = models.PositiveIntegerField()
    document_hash = models.CharField(max_length=64)
    pdf_sha256 = models.CharField(max_length=64)
    code_digest = models.CharField(max_length=64, editable=False)
    expires_at = models.DateTimeField()
    state = models.CharField(max_length=16, choices=State, default=State.PENDING)
    failures = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["agreement", "user"],
                condition=models.Q(state="pending"),
                name="one_pending_signature_attempt",
            ),
            models.CheckConstraint(
                condition=models.Q(failures__lte=5), name="signature_attempt_limit"
            ),
            models.CheckConstraint(
                condition=models.Q(state__in=["pending", "cancelled", "expired", "locked", "used"]),
                name="signature_attempt_state",
            ),
        ]
        indexes = [models.Index(fields=["user", "created_at"])]


class SignatureConfirmation(AppendOnlyModel):
    agreement = models.OneToOneField(
        Agreement, on_delete=models.PROTECT, related_name="confirmation"
    )
    document = models.OneToOneField(
        AgreementDocument, on_delete=models.PROTECT, related_name="confirmation"
    )
    attempt = models.OneToOneField(SignatureAttempt, on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    company = models.ForeignKey("companies.Company", on_delete=models.PROTECT)
    confirmed_at = models.DateTimeField()
    document_hash = models.CharField(max_length=64)
    pdf_sha256 = models.CharField(max_length=64)
    mode = models.CharField(max_length=24, default="demo_code", editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(mode="demo_code"), name="signature_confirmation_demo_only"
            )
        ]
