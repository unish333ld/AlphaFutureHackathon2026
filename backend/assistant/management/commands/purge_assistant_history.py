from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from assistant.models import Conversation


class Command(BaseCommand):
    help = "Delete assistant conversations inactive for AI_HISTORY_DAYS (default 7)."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=settings.AI_HISTORY_DAYS)
        count = 0
        while True:
            with transaction.atomic():
                rows = list(
                    Conversation.objects.select_for_update().filter(updated_at__lt=cutoff)[:100]
                )
                if not rows:
                    break
                for conversation in rows:
                    conversation.messages.all().delete()
                    conversation.delete()
                    count += 1
        self.stdout.write(f"Deleted {count} expired assistant conversations.")
