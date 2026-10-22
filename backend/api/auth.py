from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from api.serializers import (
    CsrfSerializer,
    LoginRequestSerializer,
    LoginResponseSerializer,
    UserSerializer,
)


class LoginThrottle(SimpleRateThrottle):
    scope = "login"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class BrowserLoginView(LoginView):
    template_name = "registration/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST" and not LoginThrottle().allow_request(request, self):
            return HttpResponse("Слишком много попыток. Повторите через минуту.", status=429)
        return super().dispatch(request, *args, **kwargs)


class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Сессия"], responses=CsrfSerializer, summary="Получить CSRF-токен и cookie"
    )
    def get(self, request):
        return Response({"csrf_token": get_token(request._request)})


@method_decorator(csrf_protect, name="dispatch")
class SessionLoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    @extend_schema(
        tags=["Сессия"],
        request=LoginRequestSerializer,
        responses={200: LoginResponseSerializer},
        auth=[],
        summary="Войти: session cookie + CSRF",
        description="Сначала GET /session/csrf/, затем передайте X-CSRFToken. Вход вращает токен; используйте новый из ответа.",
    )
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request._request, **serializer.validated_data)
        if user is None:
            raise AuthenticationFailed("Неверные учётные данные.")
        login(request._request, user)
        return Response(
            {"user": UserSerializer(user).data, "csrf_token": get_token(request._request)}
        )


class SessionLogoutView(APIView):
    @extend_schema(tags=["Сессия"], request=None, responses={204: None}, summary="Завершить сессию")
    def post(self, request):
        logout(request._request)
        return Response(status=204)


class MeView(APIView):
    @extend_schema(
        tags=["Сессия"], responses=UserSerializer, summary="Текущий пользователь и его полномочия"
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)
