"""Insecure-for-production simulator: no phone, delivery or second factor."""

import hashlib
import hmac

from django.conf import settings
from rest_framework.exceptions import PermissionDenied


def require_demo_codes():
    if not settings.DEMO_MODE or not settings.DEMO_SIGNATURE_ENABLED:
        raise PermissionDenied("Подтверждение кодом доступно только в явно включённом демо-режиме.")


class DemoCodeAdapter:
    @staticmethod
    def code(attempt_id):
        require_demo_codes()
        digest = hmac.new(
            settings.SECRET_KEY.encode(), f"demo-signature:{attempt_id}".encode(), hashlib.sha256
        ).digest()
        return f"{int.from_bytes(digest[:8]) % 1000000:06d}"

    @staticmethod
    def digest(attempt_id, code):
        return hashlib.sha256(f"{attempt_id}:{code}".encode()).hexdigest()
