from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from assistant import services
from assistant.models import Conversation
from assistant.serializers import (
    AssistantReplySerializer,
    ConversationSerializer,
    CreateConversationSerializer,
    MessageSerializer,
    SendMessageSerializer,
)
from assistant.throttles import AssistantRateThrottle


class IsClient(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.is_active
            and not request.user.is_credit_specialist
        )


def visible_conversations(user):
    return Conversation.objects.filter(
        user=user, company__memberships__user=user, company__memberships__active=True
    ).distinct()


@extend_schema_view(
    list=extend_schema(tags=["Савелий"], summary="Мои диалоги"),
    retrieve=extend_schema(tags=["Савелий"], summary="Мой диалог"),
)
class ConversationViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsClient]
    serializer_class = ConversationSerializer
    queryset = Conversation.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Conversation.objects.none()
        return visible_conversations(self.request.user)

    @extend_schema(
        tags=["Савелий"],
        request=CreateConversationSerializer,
        responses={201: ConversationSerializer},
        summary="Начать диалог для своей компании",
    )
    def create(self, request, *args, **kwargs):
        serializer = CreateConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation = services.create_conversation(request.user, serializer.validated_data)
        return Response(ConversationSerializer(conversation).data, status=201)


class ConversationMessagesView(APIView):
    permission_classes = [IsClient]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method == "POST":
            throttles.append(AssistantRateThrottle())
        return throttles

    def get_conversation(self, request, conversation_id):
        return get_object_or_404(visible_conversations(request.user), pk=conversation_id)

    @extend_schema(
        tags=["Савелий"],
        responses=MessageSerializer(many=True),
        summary="Сообщения моего диалога",
    )
    def get(self, request, conversation_id):
        conversation = self.get_conversation(request, conversation_id)
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(conversation.messages.all(), request, view=self)
        return paginator.get_paginated_response(MessageSerializer(page, many=True).data)

    @extend_schema(
        tags=["Савелий"],
        request=SendMessageSerializer,
        responses={200: AssistantReplySerializer},
        summary="Спросить Савелия",
        description=(
            "Требует session cookie, CSRF и актуальную версию диалога. "
            "Помощник не меняет заявку и не принимает кредитное решение."
        ),
    )
    def post(self, request, conversation_id):
        conversation = self.get_conversation(request, conversation_id)
        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reply, version = services.reply(
            request.user,
            conversation.id,
            serializer.validated_data["expected_version"],
            serializer.validated_data["text"],
        )
        return Response(
            {
                "conversation_id": conversation.id,
                "version": version,
                "model_status": "available",
                "message": MessageSerializer(reply).data,
            }
        )
