from decimal import Decimal

from rest_framework import serializers
from rest_framework.settings import api_settings

from accounts.models import User
from agreements.models import Agreement, Disbursement
from applications.models import (
    Application,
    ApplicationEvent,
    ApplicationRevision,
    InformationRequest,
)
from checks.models import CheckResult
from companies.models import Company, CompanyMember
from decisions.models import Assessment, CreditDecision
from offers.models import Offer
from products.models import CreditProduct


class StrictSerializer(serializers.Serializer):
    """Reject extra fields instead of silently dropping status/rate/role injection."""

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError(
                {api_settings.NON_FIELD_ERRORS_KEY: ["Ожидается JSON-объект."]}
            )
        unknown = set(data) - set(self.fields)
        if unknown:
            raise serializers.ValidationError(
                {field: "Поле не разрешено для этого действия." for field in unknown}
            )
        return super().to_internal_value(data)


class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField(
        help_text="Описание ошибки. При валидации ответ содержит ошибки по именам полей."
    )


class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyMember
        fields = ["company", "role", "can_submit", "can_sign", "active"]
        read_only_fields = fields


class UserSerializer(serializers.ModelSerializer):
    memberships = MemberSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "system_role", "memberships"]
        read_only_fields = fields


class LoginRequestSerializer(StrictSerializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(
        max_length=256, write_only=True, style={"input_type": "password"}
    )


class CsrfSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class LoginResponseSerializer(serializers.Serializer):
    user = UserSerializer()
    csrf_token = serializers.CharField(help_text="Обновлённый CSRF-токен после входа.")


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    database = serializers.CharField()


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            "id",
            "inn",
            "name",
            "kind",
            "registered_at",
            "status",
            "is_existing_client",
            "demo_scenario",
        ]
        read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditProduct
        fields = [
            "id",
            "code",
            "name",
            "description",
            "min_amount",
            "max_amount",
            "min_term_months",
            "max_term_months",
            "annual_rate",
            "rules_version",
            "active",
        ]
        read_only_fields = fields


class VersionSerializer(StrictSerializer):
    lock_version = serializers.IntegerField(
        min_value=0, help_text="Актуальное значение из GET заявки."
    )


class RevisionInputSerializer(StrictSerializer):
    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="Рубли, десятичная строка.",
    )
    term_months = serializers.IntegerField(min_value=1, max_value=120)
    purpose = serializers.CharField(max_length=500)
    monthly_revenue = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, allow_null=True, default=None
    )
    monthly_expenses = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, allow_null=True, default=None
    )
    monthly_debt_payments = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, allow_null=True, default=None
    )


class ApplicationCreateSerializer(RevisionInputSerializer):
    company = serializers.UUIDField()
    product = serializers.UUIDField()


class DraftUpdateSerializer(RevisionInputSerializer):
    lock_version = serializers.IntegerField(min_value=0)
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal("0.01"), required=False
    )
    term_months = serializers.IntegerField(min_value=1, max_value=120, required=False)
    purpose = serializers.CharField(max_length=500, required=False)
    monthly_revenue = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, allow_null=True, required=False
    )
    monthly_expenses = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, allow_null=True, required=False
    )
    monthly_debt_payments = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0, allow_null=True, required=False
    )


class RevisionSubmitSerializer(RevisionInputSerializer):
    lock_version = serializers.IntegerField(min_value=0)


class InformationRequestInputSerializer(VersionSerializer):
    question = serializers.CharField(max_length=1000)


class SignRequestSerializer(VersionSerializer):
    document_hash = serializers.RegexField(
        r"\A[0-9a-f]{64}\Z", help_text="SHA-256 условий из GET договора."
    )
    confirm_simulation = serializers.BooleanField(help_text="Явное подтверждение условной подписи.")

    def validate_confirm_simulation(self, value):
        if not value:
            raise serializers.ValidationError("Нужно подтвердить условное подписание.")
        return value


class DisbursementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Disbursement
        fields = [
            "id",
            "agreement",
            "amount",
            "status",
            "idempotency_key",
            "issued_at",
            "is_simulated",
        ]
        read_only_fields = fields


class AgreementSerializer(serializers.ModelSerializer):
    disbursement = DisbursementSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Agreement
        fields = [
            "id",
            "offer",
            "number",
            "terms_snapshot",
            "document_hash",
            "signed_by",
            "signed_at",
            "signature_mode",
            "created_at",
            "disbursement",
        ]
        read_only_fields = fields


class OfferSerializer(serializers.ModelSerializer):
    agreement = AgreementSerializer(read_only=True, allow_null=True)
    application_id = serializers.UUIDField(
        source="decision.assessment.revision.application_id", read_only=True
    )

    class Meta:
        model = Offer
        fields = [
            "id",
            "application_id",
            "decision",
            "product",
            "amount",
            "annual_rate",
            "term_months",
            "monthly_payment",
            "schedule",
            "status",
            "expires_at",
            "accepted_at",
            "sign_before",
            "created_at",
            "agreement",
        ]
        read_only_fields = fields


class CreditDecisionSerializer(serializers.ModelSerializer):
    offer = OfferSerializer(read_only=True, allow_null=True)

    class Meta:
        model = CreditDecision
        fields = [
            "id",
            "outcome",
            "reason_code",
            "explanation",
            "decided_by",
            "policy_version",
            "created_at",
            "offer",
        ]
        read_only_fields = fields


class AssessmentSerializer(serializers.ModelSerializer):
    decision = CreditDecisionSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Assessment
        fields = ["id", "score", "risk_level", "factors", "rules_version", "created_at", "decision"]
        read_only_fields = fields


class CheckSerializer(serializers.ModelSerializer):
    class Meta:
        model = CheckResult
        fields = ["id", "kind", "status", "attempt", "result", "source", "is_mock", "checked_at"]
        read_only_fields = fields


class InformationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = InformationRequest
        fields = [
            "id",
            "question",
            "requested_by",
            "created_at",
            "response_revision",
            "responded_at",
        ]
        read_only_fields = fields


class RevisionSerializer(serializers.ModelSerializer):
    checks = CheckSerializer(many=True, read_only=True)
    assessment = AssessmentSerializer(read_only=True, allow_null=True)
    information_requests = InformationRequestSerializer(many=True, read_only=True)

    class Meta:
        model = ApplicationRevision
        fields = [
            "id",
            "revision_no",
            "amount",
            "term_months",
            "purpose",
            "monthly_revenue",
            "monthly_expenses",
            "monthly_debt_payments",
            "input_snapshot",
            "submitted_at",
            "created_at",
            "checks",
            "assessment",
            "information_requests",
        ]
        read_only_fields = fields


class ApplicationListSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source="company.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = Application
        fields = [
            "id",
            "company",
            "company_name",
            "created_by",
            "product",
            "product_name",
            "status",
            "lock_version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ApplicationSerializer(ApplicationListSerializer):
    revisions = RevisionSerializer(many=True, read_only=True)

    class Meta(ApplicationListSerializer.Meta):
        fields = ApplicationListSerializer.Meta.fields + ["revisions"]
        read_only_fields = fields


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationEvent
        fields = ["id", "actor", "event_type", "from_status", "to_status", "details", "created_at"]
        read_only_fields = fields


class PaymentRequestSerializer(StrictSerializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal("1.00"))
    annual_rate = serializers.DecimalField(
        max_digits=7, decimal_places=4, min_value=0, max_value=100
    )
    term_months = serializers.IntegerField(min_value=1, max_value=120)


class PaymentResponseSerializer(serializers.Serializer):
    monthly_payment = serializers.DecimalField(max_digits=18, decimal_places=2)
    schedule = serializers.JSONField(
        help_text="График v1: месяц, платёж, основной долг, проценты, остаток; без комиссий."
    )
