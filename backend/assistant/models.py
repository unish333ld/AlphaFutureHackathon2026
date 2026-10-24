from django.conf import settings
from django.db import models

from common.models import AppendOnlyModel, CreatedModel


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

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="assistant_message_time_idx")
        ]
        verbose_name = "Сообщение Савелия"
        verbose_name_plural = "Сообщения Савелия"
