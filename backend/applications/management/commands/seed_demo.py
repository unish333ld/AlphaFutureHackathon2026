import os
import uuid
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User
from applications.services import create_application
from companies.models import Company, CompanyMember
from products.catalog import product_defaults
from products.models import CreditProduct


class Command(BaseCommand):
    help = "Создать синтетические демо-профили, продукты и пять черновиков. Повтор безопасен."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Обновить пароли только четырёх демо-пользователей из DEMO_PASSWORD.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEMO_MODE:
            raise CommandError("Для synthetic seeds установите DEMO_MODE=true.")
        password = os.getenv("DEMO_PASSWORD", "")
        if len(password) < 12:
            raise CommandError("Установите DEMO_PASSWORD длиной не менее 12 символов.")
        validate_password(password)
        users = {}
        for username, role in [
            ("client", User.Role.CLIENT),
            ("specialist", User.Role.SPECIALIST),
            ("outsider", User.Role.CLIENT),
            ("accountant", User.Role.CLIENT),
        ]:
            user, created = User.objects.get_or_create(
                username=username, defaults={"system_role": role}
            )
            if created or options["reset_passwords"]:
                user.set_password(password)
                user.save(update_fields=["password"])
            users[username] = user
        product, _ = CreditProduct.objects.get_or_create(
            code="working-capital",
            defaults={"id": uuid.UUID(int=101), **product_defaults("working-capital")},
        )
        CreditProduct.objects.get_or_create(
            code="equipment",
            defaults={"id": uuid.UUID(int=102), **product_defaults("equipment")},
        )
        scenarios = [
            (1, "Демо · Рост", "standard", "approval", "1500000", "900000", "50000"),
            (2, "Демо · Мастерская", "standard", "counteroffer", "500000", "400000", "20000"),
            (3, "Демо · Уточнение", "standard", "needs_info", None, None, None),
            (4, "Демо · Проверка риска", "bad_history", "rejected", "1500000", "900000", "50000"),
            (
                5,
                "Демо · Повтор проверки",
                "check_error",
                "check_error",
                "1500000",
                "900000",
                "50000",
            ),
            (6, "Демо · Другая компания", "standard", None, "1000000", "600000", "0"),
        ]
        for index, name, scenario, purpose, revenue, expenses, debt in scenarios:
            company, _ = Company.objects.get_or_create(
                inn=f"{index:010d}",
                defaults={
                    "id": uuid.UUID(int=index),
                    "name": name,
                    "kind": Company.Kind.LEGAL_ENTITY,
                    "registered_at": date(2020, 1, 1),
                    "demo_scenario": scenario,
                },
            )
            owner = users["outsider"] if index == 6 else users["client"]
            CompanyMember.objects.get_or_create(
                user=owner,
                company=company,
                defaults={
                    "role": CompanyMember.Role.OWNER,
                    "can_submit": True,
                    "can_sign": True,
                },
            )
            if index == 1:
                CompanyMember.objects.get_or_create(
                    user=users["accountant"],
                    company=company,
                    defaults={
                        "role": CompanyMember.Role.ACCOUNTANT,
                        "can_submit": True,
                        "can_sign": False,
                    },
                )
            if purpose and not company.applications.exists():
                create_application(
                    owner,
                    {
                        "company": company.id,
                        "product": product.id,
                        "amount": Decimal("1000000.00"),
                        "term_months": 24,
                        "purpose": f"Демонстрационный сценарий: {purpose}",
                        "monthly_revenue": Decimal(revenue) if revenue is not None else None,
                        "monthly_expenses": Decimal(expenses) if expenses is not None else None,
                        "monthly_debt_payments": Decimal(debt) if debt is not None else None,
                    },
                )
        self.stdout.write(
            self.style.SUCCESS(
                "Готово: client, specialist, accountant, outsider; 6 компаний; 2 продукта. Пароль взят из DEMO_PASSWORD."
            )
        )
