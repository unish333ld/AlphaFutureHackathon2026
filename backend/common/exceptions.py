from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import OperationalError
from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler


class Conflict(APIException):
    status_code = 409
    default_detail = "Состояние или версия записи изменились. Обновите карточку."
    default_code = "conflict"


class DependencyUnavailable(APIException):
    status_code = 503
    default_detail = "Сервис временно недоступен. Обновите карточку перед повтором действия."
    default_code = "dependency_unavailable"


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/v1/"):
        return JsonResponse(
            {"detail": "CSRF-проверка не пройдена.", "code": "csrf_failed"}, status=403
        )
    return django_csrf_failure(request, reason=reason)


def exception_handler(exc, context):
    if isinstance(exc, OperationalError):
        exc = DependencyUnavailable()
    if isinstance(exc, DjangoValidationError):
        exc = ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages)
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, APIException) and isinstance(response.data, dict):
        if isinstance(response.data.get("detail"), str) and isinstance(exc.get_codes(), str):
            response.data["code"] = exc.get_codes()
    return response
