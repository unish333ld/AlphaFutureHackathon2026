from django.db.models import OuterRef, Prefetch, Subquery

from agreements.models import AgreementDocument
from applications.models import Application, ApplicationRevision
from common.access import company_scope


def application_queryset(user, *, detail=True):
    queryset = company_scope(
        Application.objects.select_related("company", "product", "assigned_to"), user, "company"
    )
    if detail:
        revisions = (
            ApplicationRevision.objects.select_related(
                "assessment__decision__offer__agreement__disbursement",
                "assessment__decision__offer__agreement__confirmation",
            )
            .prefetch_related(
                "checks",
                "information_requests",
                Prefetch(
                    "assessment__decision__offer__agreement__documents",
                    queryset=AgreementDocument.objects.defer("pdf_data", "snapshot"),
                ),
            )
            .order_by("-revision_no")
        )
        queryset = queryset.prefetch_related(Prefetch("revisions", queryset=revisions))
    return queryset


def staff_queue_queryset(user):
    latest = ApplicationRevision.objects.filter(application_id=OuterRef("pk")).order_by(
        "-revision_no"
    )
    return application_queryset(user, detail=False).annotate(
        queue_revision_id=Subquery(latest.values("id")[:1]),
        amount=Subquery(latest.values("amount")[:1]),
        term_months=Subquery(latest.values("term_months")[:1]),
        risk_level=Subquery(latest.values("assessment__risk_level")[:1]),
    )
