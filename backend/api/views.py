from django.db import DatabaseError, connection
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from agreements import services as deal
from agreements.models import Agreement, Disbursement
from api.selectors import application_queryset
from api.serializers import (
    AgreementSerializer,
    ApplicationCreateSerializer,
    ApplicationListSerializer,
    ApplicationSerializer,
    CompanySerializer,
    DisbursementSerializer,
    DraftUpdateSerializer,
    ErrorSerializer,
    EventSerializer,
    HealthSerializer,
    InformationRequestInputSerializer,
    OfferSerializer,
    PaymentRequestSerializer,
    PaymentResponseSerializer,
    ProductSerializer,
    RevisionSubmitSerializer,
    SignRequestSerializer,
    VersionSerializer,
)
from applications import services
from applications.models import Application
from common.access import company_scope
from companies.models import Company
from offers.models import Offer
from products.calculations import payment_schedule
from products.models import CreditProduct

ACTION_RESPONSES = {
    200: ApplicationSerializer,
    400: ErrorSerializer,
    403: ErrorSerializer,
    404: ErrorSerializer,
    409: ErrorSerializer,
}


class IsSpecialist(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_credit_specialist


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Система"],
        auth=[],
        responses={200: HealthSerializer, 503: HealthSerializer},
        summary="Готовность сервиса и PostgreSQL",
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError:
            return Response({"status": "unavailable", "database": "unavailable"}, status=503)
        return Response({"status": "ok", "database": "ok"})


@extend_schema_view(
    list=extend_schema(tags=["Компании"], summary="Доступные компании"),
    retrieve=extend_schema(tags=["Компании"], summary="Профиль компании"),
)
class CompanyViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CompanySerializer
    queryset = Company.objects.all()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Company.objects.none()
        if self.request.user.is_credit_specialist:
            return Company.objects.all()
        return Company.objects.filter(memberships__user=self.request.user, memberships__active=True)


@extend_schema_view(
    list=extend_schema(tags=["Продукты"], summary="Демонстрационный каталог"),
    retrieve=extend_schema(tags=["Продукты"], summary="Условия демо-продукта"),
)
class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CreditProduct.objects.filter(active=True)
    serializer_class = ProductSerializer


class CalculatorView(APIView):
    @extend_schema(
        tags=["Продукты"],
        request=PaymentRequestSerializer,
        responses=PaymentResponseSerializer,
        summary="Предварительный аннуитетный расчёт",
        description="Демо: равные месячные периоды, без комиссий. Итоговый последний платёж корректирует округление. Не является кредитным предложением.",
        examples=[
            OpenApiExample(
                "Пример",
                value={"amount": "1000000.00", "annual_rate": "18.0000", "term_months": 24},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        serializer = PaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment, schedule = payment_schedule(**serializer.validated_data)
        return Response(
            PaymentResponseSerializer({"monthly_payment": payment, "schedule": schedule}).data
        )


class ApplicationQueryMixin:
    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Application.objects.none()
        queryset = application_queryset(self.request.user, detail=self.action != "list")
        status = self.request.query_params.get("status")
        if status:
            if status not in Application.Status.values:
                raise serializers.ValidationError({"status": "Неизвестное состояние."})
            queryset = queryset.filter(status=status)
        return queryset

    def get_object(self):
        obj = super().get_object()
        services.expire_application_if_due(obj.id)
        return get_object_or_404(self.get_queryset(), pk=obj.id)

    def application_response(self, app, status=200):
        fresh = get_object_or_404(application_queryset(self.request.user), pk=app.id)
        return Response(ApplicationSerializer(fresh).data, status=status)


@extend_schema_view(
    list=extend_schema(
        tags=["Заявки"],
        summary="Заявки доступных компаний",
        parameters=[OpenApiParameter("status", str, enum=Application.Status.values)],
    ),
    retrieve=extend_schema(
        tags=["Заявки"], summary="Заявка со всеми ревизиями, проверками и решениями"
    ),
)
class ApplicationViewSet(
    ApplicationQueryMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Application.objects.none()
    serializer_class = ApplicationSerializer

    def get_serializer_class(self):
        return ApplicationListSerializer if self.action == "list" else ApplicationSerializer

    @extend_schema(
        tags=["Заявки"],
        request=ApplicationCreateSerializer,
        responses={201: ApplicationSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
        summary="Создать черновик",
        examples=[
            OpenApiExample(
                "Заявка",
                request_only=True,
                value={
                    "company": "00000000-0000-0000-0000-000000000001",
                    "product": "00000000-0000-0000-0000-000000000101",
                    "amount": "1000000.00",
                    "term_months": 24,
                    "purpose": "Пополнение оборотных средств",
                    "monthly_revenue": "1500000.00",
                    "monthly_expenses": "900000.00",
                    "monthly_debt_payments": "50000.00",
                },
            )
        ],
    )
    def create(self, request, *args, **kwargs):
        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.application_response(
            services.create_application(request.user, serializer.validated_data), status=201
        )

    @extend_schema(
        tags=["Заявки"],
        request=DraftUpdateSerializer,
        responses=ACTION_RESPONSES,
        summary="Изменить поля черновика",
    )
    def partial_update(self, request, pk=None):
        app = self.get_object()
        serializer = DraftUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.application_response(
            services.update_draft(request.user, app.id, serializer.validated_data)
        )

    @extend_schema(
        tags=["Заявки"],
        request=VersionSerializer,
        responses=ACTION_RESPONSES,
        summary="Отправить заявку и выполнить локальные проверки",
        description="Требует can_submit. Возвращает review, needs_info или checking с check.error; техническая ошибка не является отказом.",
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        app = self.get_object()
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.application_response(
            services.submit_application(
                request.user, app.id, serializer.validated_data["lock_version"]
            )
        )

    @extend_schema(
        tags=["Заявки"],
        request=VersionSerializer,
        responses=ACTION_RESPONSES,
        summary="Повторить проверку после технической ошибки",
    )
    @action(detail=True, methods=["post"], url_path="retry-checks")
    def retry_checks(self, request, pk=None):
        app = self.get_object()
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.application_response(
            services.retry_checks(request.user, app.id, serializer.validated_data["lock_version"])
        )

    @extend_schema(
        tags=["Заявки"],
        request=RevisionSubmitSerializer,
        responses=ACTION_RESPONSES,
        summary="Ответить на уточнение новой ревизией",
    )
    @action(detail=True, methods=["post"], url_path="provide-information")
    def provide_information(self, request, pk=None):
        return self._revise(request, answering=True)

    @extend_schema(
        tags=["Заявки"],
        request=RevisionSubmitSerializer,
        responses=ACTION_RESPONSES,
        summary="Пересмотреть заявку новой ревизией",
        description="Доступно из review/offered. Предыдущее предложение становится superseded, проверки запускаются заново.",
    )
    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        return self._revise(request, answering=False)

    def _revise(self, request, answering):
        app = self.get_object()
        serializer = RevisionSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.application_response(
            services.revise_application(
                request.user, app.id, serializer.validated_data, answering=answering
            )
        )

    @extend_schema(
        tags=["Заявки"], responses=EventSerializer(many=True), summary="История переходов заявки"
    )
    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        app = self.get_object()
        page = self.paginate_queryset(app.events.all())
        return self.get_paginated_response(EventSerializer(page, many=True).data)


@extend_schema_view(
    list=extend_schema(
        tags=["Банк"],
        summary="Очередь специалиста",
        parameters=[OpenApiParameter("status", str, enum=Application.Status.values)],
    ),
    retrieve=extend_schema(tags=["Банк"], summary="Карточка специалиста"),
)
class StaffApplicationViewSet(
    ApplicationQueryMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    queryset = Application.objects.none()
    permission_classes = [IsSpecialist]
    serializer_class = ApplicationSerializer

    def get_serializer_class(self):
        return ApplicationListSerializer if self.action == "list" else ApplicationSerializer

    @extend_schema(
        tags=["Банк"],
        request=InformationRequestInputSerializer,
        responses=ACTION_RESPONSES,
        summary="Запросить уточнение у компании",
    )
    @action(detail=True, methods=["post"], url_path="request-information")
    def request_information(self, request, pk=None):
        app = self.get_object()
        serializer = InformationRequestInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self.application_response(
            services.request_information(
                request.user, app.id, data["lock_version"], data["question"]
            )
        )

    @extend_schema(
        tags=["Банк"],
        request=VersionSerializer,
        responses=ACTION_RESPONSES,
        summary="Принять решение по демонстрационной политике",
        description="Только specialist. Сервер использует сохранённую оценку текущей ревизии: одобрение, уменьшенная сумма или отказ. Ставку и решение нельзя назначить в теле запроса.",
    )
    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        app = self.get_object()
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.application_response(
            services.make_decision(request.user, app.id, serializer.validated_data["lock_version"])
        )


@extend_schema_view(
    list=extend_schema(tags=["Предложения"], summary="Доступные предложения"),
    retrieve=extend_schema(tags=["Предложения"], summary="Условия предложения и договор"),
)
class OfferViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Offer.objects.none()
    serializer_class = OfferSerializer

    def get_queryset(self):
        queryset = Offer.objects.select_related(
            "decision__assessment__revision", "agreement__disbursement"
        )
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        return company_scope(
            queryset, self.request.user, "decision__assessment__revision__application__company"
        )

    def get_object(self):
        offer = super().get_object()
        services.expire_application_if_due(offer.decision.assessment.revision.application_id)
        return get_object_or_404(self.get_queryset(), pk=offer.id)

    def _respond(self, request, accept):
        offer = self.get_object()
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        app = deal.respond_to_offer(
            request.user, offer.id, serializer.validated_data["lock_version"], accept=accept
        )
        return Response(
            ApplicationSerializer(
                get_object_or_404(application_queryset(request.user), pk=app.id)
            ).data
        )

    @extend_schema(
        tags=["Предложения"],
        request=VersionSerializer,
        responses=ACTION_RESPONSES,
        summary="Принять предложение и сформировать демо-договор",
    )
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        return self._respond(request, True)

    @extend_schema(
        tags=["Предложения"],
        request=VersionSerializer,
        responses=ACTION_RESPONSES,
        summary="Отклонить предложение",
    )
    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        return self._respond(request, False)


@extend_schema_view(
    list=extend_schema(tags=["Договоры"], summary="Доступные демо-договоры"),
    retrieve=extend_schema(tags=["Договоры"], summary="Зафиксированные условия и SHA-256"),
)
class AgreementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Agreement.objects.none()
    serializer_class = AgreementSerializer

    def get_queryset(self):
        queryset = Agreement.objects.select_related(
            "offer__decision__assessment__revision", "disbursement"
        )
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        return company_scope(
            queryset,
            self.request.user,
            "offer__decision__assessment__revision__application__company",
        )

    @extend_schema(
        tags=["Договоры"],
        request=SignRequestSerializer,
        responses={
            200: AgreementSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        summary="Условно подписать принятую версию договора",
        description="Требует can_sign, document_hash и confirm_simulation=true. Юридически значимая электронная подпись не выполняется.",
    )
    @action(detail=True, methods=["post"])
    def sign(self, request, pk=None):
        agreement = self.get_object()
        services.expire_application_if_due(
            agreement.offer.decision.assessment.revision.application_id
        )
        serializer = SignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = deal.sign_agreement(
            request.user, agreement.id, data["lock_version"], data["document_hash"]
        )
        return Response(AgreementSerializer(result).data)

    @extend_schema(
        tags=["Выдачи"],
        request=VersionSerializer,
        responses={
            200: DisbursementSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        parameters=[
            OpenApiParameter(
                "Idempotency-Key",
                str,
                OpenApiParameter.HEADER,
                required=True,
                description="UUID. Повтор того же ключа и договора возвращает ту же выдачу даже при старом lock_version.",
            )
        ],
        summary="Выполнить моделируемую выдачу",
        description="Только specialist. Денежных переводов нет. Один договор — одна выдача; повторный ключ с другим договором даёт 409.",
    )
    @action(detail=True, methods=["post"], permission_classes=[IsSpecialist])
    def disburse(self, request, pk=None):
        agreement = self.get_object()
        serializer = VersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key = serializers.UUIDField().run_validation(request.headers.get("Idempotency-Key"))
        result = deal.disburse(
            request.user, agreement.id, serializer.validated_data["lock_version"], key
        )
        return Response(DisbursementSerializer(result).data)


@extend_schema_view(
    list=extend_schema(tags=["Выдачи"], summary="История моделируемых выдач"),
    retrieve=extend_schema(tags=["Выдачи"], summary="Результат моделируемой выдачи"),
)
class DisbursementViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Disbursement.objects.none()
    serializer_class = DisbursementSerializer

    def get_queryset(self):
        queryset = Disbursement.objects.all()
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        return company_scope(
            queryset,
            self.request.user,
            "agreement__offer__decision__assessment__revision__application__company",
        )
