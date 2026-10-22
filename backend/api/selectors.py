from django.db.models import Prefetch

from applications.models import Application, ApplicationRevision
from common.access import company_scope


def application_queryset(user, *, detail=True):
    queryset = company_scope(
        Application.objects.select_related("company", "product"), user, "company"
    )
    if detail:
        revisions = (
            ApplicationRevision.objects.select_related(
                "assessment__decision__offer__agreement__disbursement",
            )
            .prefetch_related("checks", "information_requests")
            .order_by("-revision_no")
        )
        queryset = queryset.prefetch_related(Prefetch("revisions", queryset=revisions))
    return queryset
