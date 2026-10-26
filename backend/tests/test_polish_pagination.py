from datetime import timedelta

from django.utils import timezone

from applications.models import Application, ApplicationEvent


def get(api, user, path):
    api.force_authenticate(user=user)
    return api.get(f"/api/v1/{path}")


def new_application(demo):
    source = demo["applications"]["approval"]
    return Application.objects.create(
        company=source.company,
        created_by=demo["client"],
        product=source.product,
    )


def event(app, status="needs_info", details=None):
    return ApplicationEvent.objects.create(
        application=app,
        event_type="information_requested",
        to_status=status,
        details=details or {},
    )


def test_history_page_size_and_stable_ties(demo, api):
    app = new_application(demo)
    user = demo["client"]
    assert get(api, user, f"applications/{app.pk}/events/").data["count"] == 0
    first = event(app)
    assert get(api, user, f"applications/{app.pk}/events/").data["results"][0]["id"] == str(
        first.pk
    )
    created = [event(app) for _ in range(9)]
    ten = get(api, user, f"applications/{app.pk}/events/").data
    assert ten["count"] == len(ten["results"]) == 10 and ten["next"] is None
    created.append(event(app))
    eleven = get(api, user, f"applications/{app.pk}/events/?page=2").data
    assert eleven["count"] == 11 and len(eleven["results"]) == 1
    created.extend(event(app) for _ in range(10))
    shared_time = timezone.now() - timedelta(minutes=1)
    ApplicationEvent.objects.filter(pk__in=[first.pk, *(item.pk for item in created)]).update(
        created_at=shared_time
    )
    pages = [get(api, user, f"applications/{app.pk}/events/?page={number}") for number in (1, 2, 3)]
    assert [len(page.data["results"]) for page in pages] == [10, 10, 1]
    ids = [item["id"] for page in pages for item in page.data["results"]]
    assert len(ids) == len(set(ids)) == 21
    assert ids == sorted(ids)
    assert get(api, user, f"applications/{app.pk}/events/?page=4").status_code == 404


def test_staff_queue_returns_exactly_ten_rows(demo, api):
    user = demo["specialist"]
    for _ in range(13):
        new_application(demo)
    first = get(api, user, "staff/applications/?ordering=created_at&page=1")
    second = get(api, user, "staff/applications/?ordering=created_at&page=2")
    assert first.status_code == second.status_code == 200
    assert len(first.data["results"]) == 10
    assert len(second.data["results"]) >= 3
    assert not (
        {row["id"] for row in first.data["results"]} & {row["id"] for row in second.data["results"]}
    )


def test_notifications_baseline_cursor_results_scope_and_ties(demo, api):
    app = new_application(demo)
    user = demo["client"]
    event(app, "rejected")
    baseline = get(api, user, "applications/notifications/")
    assert baseline.status_code == 200
    assert baseline.data["results"] == []
    stamp = timezone.now()
    rows = [
        event(app, "needs_info"),
        event(app, "offered", {"outcome": "approved"}),
        event(app, "offered", {"outcome": "counteroffer"}),
        event(app, "rejected"),
    ]
    ApplicationEvent.objects.filter(pk__in=[row.pk for row in rows]).update(created_at=stamp)
    result = get(api, user, f"applications/notifications/?cursor={baseline.data['cursor']}")
    assert result.status_code == 200, result.data
    assert len(result.data["results"]) == 4
    assert {row["kind"] for row in result.data["results"]} == {
        "needs_info",
        "approved",
        "counteroffer",
        "rejected",
    }
    assert [str(row["id"]) for row in result.data["results"]] == sorted(str(row.pk) for row in rows)
    again = get(api, user, f"applications/notifications/?cursor={result.data['cursor']}")
    assert again.data["results"] == []
    assert again.data["cursor"] == result.data["cursor"]
    assert (
        get(
            api, demo["outsider"], f"applications/notifications/?cursor={result.data['cursor']}"
        ).status_code
        == 400
    )
    assert get(api, demo["specialist"], "applications/notifications/").status_code == 403
