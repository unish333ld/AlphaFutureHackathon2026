"""Private PDF delivery and the explicit demo-code preparation actions."""

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from agreements.demo_codes import DemoCodeAdapter
from agreements.documents import assert_integrity, generate_document
from agreements.services import cancel_signature_attempt, start_signature_attempt
from api.serializers import (
    AgreementDocumentSerializer,
    CancelSignatureRequestSerializer,
    DocumentGenerationRequestSerializer,
    ErrorSerializer,
    SignatureAttemptRequestSerializer,
    SignatureAttemptSerializer,
)

ERRORS = {
    400: ErrorSerializer,
    403: ErrorSerializer,
    404: ErrorSerializer,
    409: ErrorSerializer,
    429: ErrorSerializer,
    503: ErrorSerializer,
}


class AgreementDocumentsMixin:
    @extend_schema(
        tags=["Договоры"],
        request=DocumentGenerationRequestSerializer,
        responses={200: AgreementDocumentSerializer, **ERRORS},
        summary="Сформировать неизменяемый исходный PDF",
        description="Только can_sign. Повтор возвращает тот же артефакт и байты. Стороны фиксируются для этой версии. document_hash — канонические условия; pdf_sha256 — отдельный хеш байтов. Рендеринг вне транзакции; при изменении lock_version — 409. Нет подписи и выдачи.",
    )
    @action(detail=True, methods=["post"], url_path="generate-document")
    def generate_document(self, request, pk=None):
        agreement = self.get_object()
        serializer = DocumentGenerationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = generate_document(
            request.user,
            agreement.pk,
            version=serializer.validated_data["lock_version"],
            document_hash=serializer.validated_data["document_hash"],
        )
        return Response(AgreementDocumentSerializer(doc).data)

    @extend_schema(
        tags=["Договоры"],
        request=DocumentGenerationRequestSerializer,
        responses={200: AgreementDocumentSerializer, **ERRORS},
        summary="Сформировать отдельную копию с отметкой демо-подписи",
        description="Только после сохранённой SignatureConfirmation. Ошибка копии не отменяет подпись; повтор создаёт только копию, не подписывает снова. Исходные PDF-байты неизменны.",
    )
    @action(detail=True, methods=["post"], url_path="signed-document")
    def signed_document(self, request, pk=None):
        agreement = self.get_object()
        serializer = DocumentGenerationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = generate_document(
            request.user,
            agreement.pk,
            kind="signed_copy",
            version=serializer.validated_data["lock_version"],
            document_hash=serializer.validated_data["document_hash"],
        )
        return Response(AgreementDocumentSerializer(doc).data)

    @extend_schema(
        tags=["Договоры"],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY, **ERRORS},
        parameters=[
            OpenApiParameter(
                "kind", str, enum=["original", "signed_copy"], description="По умолчанию original"
            ),
            OpenApiParameter("download", bool, description="true: attachment; иначе inline"),
        ],
        summary="Открыть или скачать сохранённый приватный PDF",
        description="Авторизованный company scope; специалист может читать доступный ему договор. Повтор отдаёт те же сохранённые байты. Cache-Control: private, no-store; Vary: Cookie. Публичного media URL нет. Несформированный документ — 404.",
    )
    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        agreement = self.get_object()
        kind = request.query_params.get("kind", "original")
        if kind not in {"original", "signed_copy"}:
            raise serializers.ValidationError({"kind": ["Допустимы original и signed_copy."]})
        download = serializers.BooleanField().run_validation(
            request.query_params.get("download", False)
        )
        document = get_object_or_404(agreement.documents, kind=kind, version=1)
        assert_integrity(document)
        response = HttpResponse(bytes(document.pdf_data), content_type="application/pdf")
        disposition = "attachment" if download else "inline"
        response["Content-Disposition"] = (
            f'{disposition}; filename="agreement-{agreement.pk}-v{document.version}-{kind}.pdf"'
        )
        response["Cache-Control"] = "private, no-store, max-age=0"
        response["Vary"] = "Cookie"
        response["X-Frame-Options"] = "SAMEORIGIN"
        response["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'self'"
        response["X-Content-Type-Options"] = "nosniff"
        response["X-PDF-SHA256"] = document.pdf_sha256
        return response

    @extend_schema(
        tags=["Договоры"],
        request=SignatureAttemptRequestSerializer,
        responses={200: SignatureAttemptSerializer, **ERRORS},
        summary="Начать демонстрационное подтверждение кодом",
        description="Только can_sign после явного ознакомления с конкретным PDF. Срок 2 минуты, до 5 проверок, до 10 новых попыток в час на участника и договор. Повтор открытия возвращает допустимую pending-попытку; устаревшая отменяется. Код возвращается браузеру только при DEMO_MODE и DEMO_SIGNATURE_ENABLED. Это не SMS, второй фактор или настоящая ЭП. signed ещё не установлен.",
    )
    @action(detail=True, methods=["post"], url_path="signature-attempt")
    def signature_attempt(self, request, pk=None):
        agreement = self.get_object()
        serializer = SignatureAttemptRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        attempt = start_signature_attempt(
            request.user,
            agreement.pk,
            data["lock_version"],
            data["document_hash"],
            data["document_id"],
            data["pdf_sha256"],
        )
        response = Response(
            SignatureAttemptSerializer(
                {
                    "id": attempt.pk,
                    "document_id": attempt.document_id,
                    "expires_at": attempt.expires_at,
                    "state": attempt.state,
                    "demo_code": DemoCodeAdapter.code(attempt.pk),
                    "simulation": True,
                }
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        tags=["Договоры"],
        request=CancelSignatureRequestSerializer,
        responses={204: None, **ERRORS},
        summary="Отменить собственную ещё не использованную попытку",
        description="Отмена не откатывает уже сохранённую подпись. USED даёт 409: сначала перечитайте договор.",
    )
    @action(detail=True, methods=["post"], url_path="cancel-signature")
    def cancel_signature(self, request, pk=None):
        agreement = self.get_object()
        serializer = CancelSignatureRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_signature_attempt(
            request.user, agreement.pk, serializer.validated_data["attempt_id"]
        )
        return Response(status=204)
