from rest_framework import serializers

from api.serializers import StrictSerializer
from assistant.models import Conversation, Message


class CreateConversationSerializer(StrictSerializer):
    company_id = serializers.UUIDField()
    application_id = serializers.UUIDField(required=False, allow_null=True)


class SendMessageSerializer(StrictSerializer):
    text = serializers.CharField(max_length=2000, trim_whitespace=True)
    expected_version = serializers.IntegerField(min_value=0)


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ["id", "company", "application", "version", "created_at", "updated_at"]
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ["id", "role", "content", "facts", "suggested_draft", "created_at"]
        read_only_fields = fields


class AssistantReplySerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField()
    version = serializers.IntegerField()
    model_status = serializers.ChoiceField(choices=["available"])
    message = MessageSerializer()
