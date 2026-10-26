from datetime import datetime

from django.core import signing
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from applications.models import Application, ApplicationEvent
from common.access import company_scope


class ResultNotificationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    application_id = serializers.UUIDField()
    number = serializers.CharField()
    kind = serializers.ChoiceField(
        choices=["needs_info", "approved", "counteroffer", "rejected", "offered"]
    )
    created_at = serializers.DateTimeField()


class NotificationBatchSerializer(serializers.Serializer):
    cursor = serializers.CharField()
    has_more = serializers.BooleanField()
    results = ResultNotificationSerializer(many=True)


class NotificationsMixin:
    @extend_schema(
        tags=["Заявки"],
        summary="Новые результаты рассмотрения",
        parameters=[
            OpenApiParameter(
                "cursor",
                str,
                description="Указатель из предыдущего ответа. Без него возвращается только исходная отметка, без старых уведомлений.",
            )
        ],
        responses=NotificationBatchSerializer,
    )
    @action(detail=False, methods=["get"], url_path="notifications")
    def notifications(self, request):
        if request.user.system_role != "client":
            raise PermissionDenied("Уведомления доступны представителю компании.")
        apps = company_scope(Application.objects.all(), request.user, "company")
        events = ApplicationEvent.objects.filter(
            application_id__in=apps.values("id"),
            to_status__in=["needs_info", "offered", "rejected"],
        ).select_related("application")
        cursor = request.query_params.get("cursor")
        if cursor:
            try:
                mark = signing.loads(cursor, salt="result-notifications", max_age=7 * 86400)
                if mark["user"] != str(request.user.pk):
                    raise ValueError("wrong user")
                stamp = datetime.fromisoformat(mark["time"])
                if stamp.tzinfo is None:
                    raise ValueError("naive time")
                events = events.filter(
                    Q(created_at__gt=stamp) | Q(created_at=stamp, id__gt=mark["id"])
                )
            except (signing.BadSignature, KeyError, TypeError, ValueError) as error:
                raise serializers.ValidationError(
                    {"cursor": "Начните получение уведомлений заново."}
                ) from error
            rows = list(events.order_by("created_at", "id")[:11])
            has_more = len(rows) > 10
            rows = rows[:10]
            if rows:
                mark = {
                    "user": str(request.user.pk),
                    "time": rows[-1].created_at.isoformat(),
                    "id": str(rows[-1].pk),
                }
        else:
            latest = events.order_by("-created_at", "-id").first()
            mark = {
                "user": str(request.user.pk),
                "time": latest.created_at.isoformat() if latest else "1970-01-01T00:00:00+00:00",
                "id": str(latest.pk) if latest else "00000000-0000-0000-0000-000000000000",
            }
            rows, has_more = [], False
        results = [
            {
                "id": event.pk,
                "application_id": event.application_id,
                "number": event.application.number,
                "kind": "counteroffer"
                if event.details.get("outcome") == "counteroffer"
                else "approved"
                if event.details.get("outcome") == "approved"
                else event.to_status,
                "created_at": event.created_at,
            }
            for event in rows
        ]
        response = Response(
            NotificationBatchSerializer(
                {
                    "cursor": cursor
                    if cursor and not rows
                    else signing.dumps(mark, salt="result-notifications"),
                    "has_more": has_more,
                    "results": results,
                }
            ).data
        )
        response["Cache-Control"] = "private, no-store"
        return response
