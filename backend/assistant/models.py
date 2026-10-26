from django.conf import settings
from django.db import models

from common.models import AppendOnlyModel, CreatedModel


class AssistantQuota(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, primary_key=True
    )
    window_start = models.DateTimeField()
    requests = models.PositiveIntegerField(default=0)


class Conversation(CreatedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assistant_conversations"
    )
    company = models.ForeignKey(
        "companies.Company", on_delete=models.PROTECT, related_name="assistant_conversations"
    )
    application = models.ForeignKey(
        "applications.Application",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assistant_conversations",
    )
    version = models.PositiveIntegerField(default=0)
    selected_product = models.ForeignKey(
        "products.CreditProduct", on_delete=models.SET_NULL, null=True, blank=True
    )
    flow_context = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "id"]
        indexes = [
            models.Index(fields=["user", "company", "-updated_at"], name="assistant_owner_time_idx")
        ]
        verbose_name = "Диалог Савелия"
        verbose_name_plural = "Диалоги Савелия"


class Message(AppendOnlyModel):
    class Role(models.TextChoices):
        USER = "user", "Клиент"
        ASSISTANT = "assistant", "Савелий"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.PROTECT, related_name="messages"
    )
    role = models.CharField(max_length=16, choices=Role)
    content = models.TextField()
    facts = models.JSONField(default=list, blank=True)
    suggested_draft = models.JSONField(default=dict, blank=True)
    reply_type = models.CharField(max_length=24, default="answer")
    questions = models.JSONField(default=list, blank=True)
    application_version = models.PositiveIntegerField(null=True, blank=True)
    model_status = models.CharField(max_length=16, default="available")

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="assistant_message_time_idx")
        ]
        verbose_name = "Сообщение Савелия"
        verbose_name_plural = "Сообщения Савелия"


class Interaction(CreatedModel):
    """Persist intent before calling a provider so a lost response is reconcilable."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="interactions"
    )
    request_id = models.UUIDField()
    step_id = models.UUIDField()
    payload = models.JSONField()
    state = models.CharField(
        max_length=16,
        choices=[("pending", "Выполняется"), ("completed", "Завершён"), ("failed", "Ошибка")],
        default="pending",
    )
    error_code = models.CharField(max_length=40, blank=True)
    finished_at = models.DateTimeField(null=True)
    message = models.ForeignKey(Message, on_delete=models.SET_NULL, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "request_id"], name="assistant_request_once"
            )
        ]
