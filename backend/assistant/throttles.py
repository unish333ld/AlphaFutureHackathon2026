from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.throttling import UserRateThrottle

from assistant.models import AssistantQuota


class AssistantRateThrottle(UserRateThrottle):
    scope = "assistant"

    def get_rate(self):
        return settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"][self.scope]

    def allow_request(self, request, view):
        if not request.user.is_authenticated:
            return True
        now = timezone.now()
        with transaction.atomic():
            AssistantQuota.objects.get_or_create(user=request.user, defaults={"window_start": now})
            quota = AssistantQuota.objects.select_for_update().get(user=request.user)
            now = timezone.now()
            elapsed = max(0, (now - quota.window_start).total_seconds())
            if elapsed >= self.duration:
                quota.window_start, quota.requests = now, 0
            if quota.requests >= self.num_requests:
                self.retry_seconds = max(1, self.duration - elapsed)
                return False
            quota.requests += 1
            quota.save(update_fields=["window_start", "requests"])
        return True

    def wait(self):
        return self.retry_seconds
