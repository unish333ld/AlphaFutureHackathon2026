import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        CLIENT = "client", "Представитель компании"
        SPECIALIST = "specialist", "Кредитный специалист"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    system_role = models.CharField(
        "Системная роль", max_length=16, choices=Role, default=Role.CLIENT
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(system_role__in=["client", "specialist"]),
                name="valid_system_role",
            )
        ]

    @property
    def is_credit_specialist(self):
        return self.is_active and self.system_role == self.Role.SPECIALIST
