from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

from common.models import CreatedModel


class Company(CreatedModel):
    class Kind(models.TextChoices):
        SOLE_PROPRIETOR = "ip", "Индивидуальный предприниматель"
        LEGAL_ENTITY = "legal", "Юридическое лицо"

    class Status(models.TextChoices):
        ACTIVE = "active", "Действует"
        INACTIVE = "inactive", "Деятельность прекращена"

    class DemoScenario(models.TextChoices):
        STANDARD = "standard", "Стандартный"
        CHECK_ERROR = "check_error", "Ошибка регистрационной проверки"
        BAD_HISTORY = "bad_history", "Негативная кредитная история"

    inn = models.CharField(
        "Синтетический ИНН",
        max_length=12,
        unique=True,
        validators=[RegexValidator(r"\A(?:[0-9]{10}|[0-9]{12})\Z", "ИНН: 10 или 12 цифр.")],
    )
    name = models.CharField("Название", max_length=255)
    kind = models.CharField("Тип", max_length=8, choices=Kind)
    registered_at = models.DateField("Дата регистрации")
    status = models.CharField("Статус", max_length=16, choices=Status, default=Status.ACTIVE)
    is_existing_client = models.BooleanField("Действующий клиент банка", default=True)
    demo_scenario = models.CharField(
        "Сценарий локального мока",
        max_length=20,
        choices=DemoScenario,
        default=DemoScenario.STANDARD,
    )

    class Meta:
        ordering = ["name", "id"]
        verbose_name = "Компания"
        verbose_name_plural = "Компании"

    def __str__(self):
        return f"{self.name} ({self.inn})"


class CompanyMember(CreatedModel):
    class Role(models.TextChoices):
        OWNER = "owner", "Собственник"
        DIRECTOR = "director", "Директор"
        ACCOUNTANT = "accountant", "Бухгалтер"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships"
    )
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="memberships")
    role = models.CharField("Роль в компании", max_length=16, choices=Role)
    can_submit = models.BooleanField("Может отправлять заявки", default=False)
    can_sign = models.BooleanField("Может условно подписывать договор", default=False)
    active = models.BooleanField("Действующее членство", default=True)

    class Meta:
        verbose_name = "Полномочие в компании"
        verbose_name_plural = "Полномочия в компаниях"
        constraints = [
            models.UniqueConstraint(fields=["user", "company"], name="unique_company_member")
        ]

    def __str__(self):
        return f"{self.user} → {self.company}"
