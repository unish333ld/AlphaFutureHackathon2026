from rest_framework.throttling import UserRateThrottle


class AssistantRateThrottle(UserRateThrottle):
    scope = "assistant"
