"""Concrete, read-only contracts for product evidence and monetary disclosures."""

from rest_framework import serializers


class CatalogReferenceSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    value_type = serializers.ChoiceField(choices=["public_product"])
    source_url = serializers.URLField()
    source_title = serializers.CharField()
    observed_at = serializers.DateField()
    effective_from = serializers.DateField(allow_null=True)
    access_mode = serializers.ChoiceField(choices=["search_index", "direct"])
    currency = serializers.ChoiceField(choices=["RUB"])
    min_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    max_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    min_term_months = serializers.IntegerField()
    max_term_months = serializers.IntegerField()
    advertised_rate_from = serializers.DecimalField(max_digits=7, decimal_places=4)
    minimum_business_age_months = serializers.IntegerField()
    rate_note = serializers.CharField()
    demo_rate_type = serializers.ChoiceField(choices=["demo_assumption"])
    demo_cost_policy = serializers.ChoiceField(choices=["no_fees_no_services"])
    limitations = serializers.CharField()


class CostBreakdownSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    calculation_version = serializers.CharField()
    value_type = serializers.ChoiceField(choices=["derived"])
    pricing_basis = serializers.ChoiceField(choices=["demo_assumption"])
    currency = serializers.ChoiceField(choices=["RUB"])
    is_complete = serializers.BooleanField()
    principal = serializers.DecimalField(max_digits=18, decimal_places=2)
    net_disbursement = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    interest_total = serializers.DecimalField(max_digits=20, decimal_places=2)
    fees_total = serializers.DecimalField(max_digits=20, decimal_places=2, allow_null=True)
    services_total = serializers.DecimalField(max_digits=20, decimal_places=2, allow_null=True)
    known_payments_total = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_repayment = serializers.DecimalField(max_digits=20, decimal_places=2, allow_null=True)
    total_cost = serializers.DecimalField(max_digits=20, decimal_places=2, allow_null=True)
    first_payment = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    last_payment = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    max_payment = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    disclosure = serializers.CharField()


class ComparisonTermsSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    annual_rate = serializers.DecimalField(max_digits=7, decimal_places=4)
    term_months = serializers.IntegerField()
    monthly_payment = serializers.DecimalField(max_digits=18, decimal_places=2)
    cost_breakdown = CostBreakdownSerializer()


class OfferComparisonSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    source_revision_id = serializers.UUIDField()
    catalog_version = serializers.CharField()
    policy_version = serializers.CharField()
    reason_code = serializers.CharField()
    explanation = serializers.CharField()
    requested = ComparisonTermsSerializer()
    proposed = ComparisonTermsSerializer()
    changed_fields = serializers.ListField(
        child=serializers.ChoiceField(
            choices=["amount", "annual_rate", "term_months", "monthly_payment"]
        )
    )


class ReadinessItemSerializer(serializers.Serializer):
    field = serializers.ChoiceField(
        choices=["monthly_revenue", "monthly_expenses", "monthly_debt_payments"]
    )
    state = serializers.ChoiceField(choices=["ready", "missing", "invalid"])
    label = serializers.CharField()
    message = serializers.CharField()


class ApplicationReadinessSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    revision_id = serializers.UUIDField(allow_null=True)
    lock_version = serializers.IntegerField()
    can_submit = serializers.BooleanField()
    submit_reason_code = serializers.CharField(allow_null=True)
    financial_data_complete = serializers.BooleanField()
    items = ReadinessItemSerializer(many=True)
    verification_state = serializers.ChoiceField(
        choices=[
            "not_checked",
            "pending",
            "technical_error",
            "needs_information",
            "outdated",
            "checked",
        ]
    )
    verification_message = serializers.CharField()
    checked_at = serializers.DateTimeField(allow_null=True)
    disclosure = serializers.CharField()
