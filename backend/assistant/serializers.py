from django.conf import settings
from rest_framework import serializers

from api.serializers import StrictSerializer
from assistant.models import Conversation, Message
from assistant.schema import DraftField, FactsField


class CreateConversationSerializer(StrictSerializer):
    company_id = serializers.UUIDField()
    application_id = serializers.UUIDField(required=False, allow_null=True)


class SendMessageSerializer(StrictSerializer):
    text = serializers.CharField(max_length=settings.AI_MAX_MESSAGE_LENGTH, trim_whitespace=True)
    expected_version = serializers.IntegerField(min_value=0)


class ConversationSerializer(serializers.ModelSerializer):
    application_number = serializers.CharField(
        source="application.number", read_only=True, allow_null=True
    )

    class Meta:
        model = Conversation
        fields = [
            "id",
            "company",
            "application",
            "application_number",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    facts = FactsField(read_only=True)
    suggested_draft = DraftField(read_only=True)
    reply_type = serializers.ChoiceField(
        choices=["answer", "missing_information", "draft_suggestion"], read_only=True
    )
    model_status = serializers.ChoiceField(choices=["available", "degraded"], read_only=True)
    questions = serializers.ListField(child=serializers.CharField(), read_only=True)
    application_id = serializers.UUIDField(
        source="conversation.application_id", allow_null=True, read_only=True
    )

    def to_representation(self, instance):
        result = super().to_representation(instance)
        facts = result["facts"]
        if result["role"] == "assistant" and (
            not isinstance(facts, list)
            or any(
                not isinstance(fact, dict) or not {"id", "source", "data"}.issubset(fact)
                for fact in facts
            )
        ):
            # Pre-review messages used an unversioned, unverified fact envelope.
            # Keep the stored history, but do not present it as current trusted data.
            result.update(
                content="Архивный ответ создан до обновления проверок. Задайте вопрос заново для получения актуальных данных.",
                facts=[],
                suggested_draft={},
                questions=[],
                reply_type="answer",
                model_status="degraded",
            )
        return result

    class Meta:
        model = Message
        fields = [
            "id",
            "role",
            "content",
            "facts",
            "suggested_draft",
            "reply_type",
            "questions",
            "application_id",
            "application_version",
            "model_status",
            "created_at",
        ]
        read_only_fields = fields


class AssistantReplySerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField()
    version = serializers.IntegerField()
    model_status = serializers.ChoiceField(choices=["available", "degraded"])
    message = MessageSerializer()


class MessagePageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = MessageSerializer(many=True)
