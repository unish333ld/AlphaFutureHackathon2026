import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from common.models import AppendOnlyModel, CreatedModel


def application_number():
    return f"AC-{uuid.uuid4().hex[:16].upper()}"


class Application(CreatedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SUBMITTED = "submitted", "Отправлена"
        CHECKING = "checking", "Выполняются проверки"
        REVIEW = "review", "Рассмотрение специалистом"
        NEEDS_INFO = "needs_info", "Нужно уточнение"
        OFFERED = "offered", "Есть предложение"
        ACCEPTED = "accepted", "Предложение принято"
        SIGNED = "signed", "Условно подписана"
        ISSUED = "issued", "Моделируемая выдача выполнена"
        REJECTED = "rejected", "Отказ"
        DECLINED = "declined", "Клиент отклонил"
        EXPIRED = "expired", "Срок предложения истёк"

    number = models.CharField(
        "Номер заявки", max_length=19, unique=True, default=application_number, editable=False
    )
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="applications"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="applications"
    )
    product = models.ForeignKey(
        "products.CreditProduct", on_delete=models.PROTECT, related_name="applications"
    )
    status = models.CharField("Состояние", max_length=16, choices=Status, default=Status.DRAFT)
    lock_version = models.PositiveIntegerField("Версия для конкурентных изменений", default=0)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assigned_applications",
        editable=False,
    )
    assigned_at = models.DateTimeField("Назначена", null=True, blank=True, editable=False)
    status_changed_at = models.DateTimeField(
        "Начало текущего состояния", default=timezone.now, editable=False
    )
    updated_at = models.DateTimeField("Изменена", auto_now=True)

    class Meta:
        ordering = ["-created_at", "id"]
        verbose_name = "Кредитная заявка"
        verbose_name_plural = "Кредитные заявки"
        indexes = [
            models.Index(fields=["company", "-created_at"], name="app_company_created_idx"),
            models.Index(fields=["status", "created_at"], name="app_queue_idx"),
            models.Index(
                fields=["assigned_to", "status", "-created_at"], name="app_assignee_queue_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(assigned_to__isnull=True, assigned_at__isnull=True)
                    | models.Q(assigned_to__isnull=False, assigned_at__isnull=False)
                ),
                name="application_assignment_pair",
            ),
        ]

    def __str__(self):
        return f"{self.id} — {self.get_status_display()}"


class ApplicationRevision(CreatedModel):
    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name="revisions")
    revision_no = models.PositiveIntegerField("Номер ревизии", validators=[MinValueValidator(1)])
    amount = models.DecimalField(
        "Запрошенная сумма, ₽",
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    term_months = models.PositiveSmallIntegerField(
        "Срок, месяцев", validators=[MinValueValidator(1), MaxValueValidator(120)]
    )
    purpose = models.CharField("Назначение", max_length=500)
    monthly_revenue = models.DecimalField(
        "Месячная выручка, ₽",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    monthly_expenses = models.DecimalField(
        "Месячные расходы, ₽",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    monthly_debt_payments = models.DecimalField(
        "Месячные платежи по обязательствам, ₽",
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    input_snapshot = models.JSONField(
        "Снимок компании, продукта и входных данных (v1)", default=dict, blank=True, editable=False
    )
    submitted_at = models.DateTimeField("Отправлена", null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-revision_no"]
        verbose_name = "Ревизия заявки"
        verbose_name_plural = "Ревизии заявок"
        constraints = [
            models.UniqueConstraint(
                fields=["application", "revision_no"], name="unique_application_revision"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    revision_no__gte=1, amount__gt=0, term_months__gte=1, term_months__lte=120
                ),
                name="revision_positive_terms",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(monthly_revenue__isnull=True) | models.Q(monthly_revenue__gte=0)
                )
                & (models.Q(monthly_expenses__isnull=True) | models.Q(monthly_expenses__gte=0))
                & (
                    models.Q(monthly_debt_payments__isnull=True)
                    | models.Q(monthly_debt_payments__gte=0)
                ),
                name="revision_nonnegative_finances",
            ),
        ]

    def save(self, *args, **kwargs):
        if (
            not self._state.adding
            and type(self).objects.filter(pk=self.pk, submitted_at__isnull=False).exists()
        ):
            raise ValidationError("Отправленную ревизию нельзя менять. Создайте новую.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.application_id} / ревизия {self.revision_no}"


class InformationRequest(CreatedModel):
    revision = models.ForeignKey(
        ApplicationRevision, on_delete=models.PROTECT, related_name="information_requests"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="information_requests",
    )
    question = models.CharField("Запрошенные сведения", max_length=1000)
    response_revision = models.OneToOneField(
        ApplicationRevision,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="answers_request",
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Запрос уточнения"
        verbose_name_plural = "Запросы уточнений"


class ApplicationEvent(AppendOnlyModel):
    application = models.ForeignKey(Application, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="application_events",
    )
    event_type = models.CharField("Событие", max_length=50)
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16)
    details = models.JSONField("Безопасные сведения (v1)", default=dict)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name = "Событие заявки"
        verbose_name_plural = "История заявок"
        indexes = [
            models.Index(fields=["application", "created_at"], name="event_application_time_idx")
        ]
