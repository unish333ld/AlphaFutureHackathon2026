from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import CreatedModel


class CreditProduct(CreatedModel):
    code = models.SlugField("Код", unique=True)
    name = models.CharField("Название", max_length=120)
    description = models.TextField("Описание")
    min_amount = models.DecimalField(
        "Минимальная сумма, ₽",
        max_digits=18,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    max_amount = models.DecimalField("Максимальная сумма, ₽", max_digits=18, decimal_places=2)
    min_term_months = models.PositiveSmallIntegerField(
        "Минимальный срок", validators=[MinValueValidator(1)]
    )
    max_term_months = models.PositiveSmallIntegerField(
        "Максимальный срок", validators=[MaxValueValidator(120)]
    )
    annual_rate = models.DecimalField(
        "Демонстрационная годовая ставка, %",
        max_digits=7,
        decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    rules_version = models.CharField("Версия правил", max_length=32, default="demo-1")
    catalog_reference = models.JSONField("Публичный ориентир и допущения", null=True, blank=True)
    active = models.BooleanField("Доступен для заявок", default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Кредитный продукт (демо)"
        verbose_name_plural = "Кредитные продукты (демо)"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(min_amount__gt=0, max_amount__gte=models.F("min_amount")),
                name="product_amount_bounds",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    min_term_months__gte=1,
                    max_term_months__gte=models.F("min_term_months"),
                    max_term_months__lte=120,
                ),
                name="product_term_bounds",
            ),
            models.CheckConstraint(
                condition=models.Q(annual_rate__gte=0, annual_rate__lte=100),
                name="product_rate_bounds",
            ),
        ]

    def __str__(self):
        return self.name
