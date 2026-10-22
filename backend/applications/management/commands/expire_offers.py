from django.core.management.base import BaseCommand

from applications.models import Application
from applications.services import expire_application_if_due


class Command(BaseCommand):
    help = "Обновить истёкшие предложения/сроки условного подписания. Также выполняется при чтении карточки."

    def handle(self, *args, **options):
        for application_id in (
            Application.objects.filter(status__in=["offered", "accepted"])
            .values_list("id", flat=True)
            .iterator()
        ):
            expire_application_if_due(application_id)
        self.stdout.write("Истёкшие предложения обновлены.")
