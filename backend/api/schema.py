from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import OpenApiExample, OpenApiResponse

from api.serializers import ErrorSerializer


class ErrorSchemaExtension(OpenApiSerializerExtension):
    target_class = "api.serializers.ErrorSerializer"

    def map_serializer(self, auto_schema, direction):
        message = {"type": "string"}
        return {
            "description": "Сохраняет формат DRF: общая ошибка detail и необязательный code; ошибки по именам полей (строка или массив строк), non_field_errors; в старых общих validation-ответах возможен массив строк.",
            "anyOf": [
                {
                    "type": "object",
                    "properties": {"detail": message, "code": message},
                    "required": ["detail"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "minProperties": 1,
                    "additionalProperties": {
                        "oneOf": [message, {"type": "array", "items": message}]
                    },
                },
                {"type": "array", "items": message},
            ],
        }


class ContractAutoSchema(AutoSchema):
    def _get_response_bodies(self, direction="response"):
        responses = super()._get_response_bodies(direction)
        errors = {
            "400": (
                "Неверный JSON, поля или параметры. Исправьте форму.",
                {"amount": ["Сумма вне границ продукта."]},
            ),
            "403": (
                "Нет сессии, полномочий или корректного CSRF.",
                {"detail": "Действие недоступно.", "code": "permission_denied"},
            ),
            "404": (
                "Ресурс не существует или скрыт company scope; также страница пагинации вне диапазона.",
                {"detail": "Не найдено."},
            ),
            "429": (
                "Лимит запросов. Учитывайте Retry-After.",
                {"detail": "Слишком много запросов.", "code": "throttled"},
            ),
            "503": (
                "PostgreSQL временно недоступен или истёк таймаут блокировки. Проверьте карточку перед повтором значимого действия.",
                {"detail": "Сервис временно недоступен.", "code": "dependency_unavailable"},
            ),
        }
        if self.method in {"POST", "PATCH"} and self.path not in {
            "/api/v1/session/login/",
            "/api/v1/session/logout/",
            "/api/v1/calculator/payment/",
        }:
            errors["409"] = (
                "Конфликт версии, назначения или состояния. GET карточки, проверка пользователем; не повторяйте действие автоматически.",
                {"detail": "Загрузите заявку заново.", "code": "stale_version"},
            )
        for status, (description, example) in errors.items():
            if status not in responses or status in {"400", "403", "404", "409", "429"}:
                responses[status] = self._get_response_for_code(
                    OpenApiResponse(
                        response=ErrorSerializer,
                        description=description,
                        examples=[OpenApiExample("Пример ошибки", value=example)],
                    ),
                    status,
                    direction=direction,
                )
        return responses
