from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from api.auth import BrowserLoginView, CsrfView, MeView, SessionLoginView, SessionLogoutView
from api.views import (
    AgreementViewSet,
    ApplicationViewSet,
    CalculatorView,
    CompanyViewSet,
    DisbursementViewSet,
    HealthView,
    OfferViewSet,
    ProductViewSet,
    StaffApplicationViewSet,
)
from assistant.views import ConversationMessagesView, ConversationViewSet

router = DefaultRouter()
router.register("companies", CompanyViewSet, basename="company")
router.register("products", ProductViewSet, basename="product")
router.register("applications", ApplicationViewSet, basename="application")
router.register("staff/applications", StaffApplicationViewSet, basename="staff-application")
router.register("offers", OfferViewSet, basename="offer")
router.register("agreements", AgreementViewSet, basename="agreement")
router.register("disbursements", DisbursementViewSet, basename="disbursement")
router.register("assistant/conversations", ConversationViewSet, basename="assistant-conversation")

urlpatterns = [
    path("", RedirectView.as_view(url="/api/docs/", permanent=False)),
    path("admin/", admin.site.urls),
    path("api/session/login/", BrowserLoginView.as_view(), name="browser-login"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("api/v1/health/", HealthView.as_view(), name="health"),
    path("api/v1/session/csrf/", CsrfView.as_view(), name="csrf"),
    path("api/v1/session/login/", SessionLoginView.as_view(), name="session-login"),
    path("api/v1/session/logout/", SessionLogoutView.as_view(), name="session-logout"),
    path("api/v1/me/", MeView.as_view(), name="me"),
    path(
        "api/v1/assistant/conversations/<uuid:conversation_id>/messages/",
        ConversationMessagesView.as_view(),
        name="assistant-messages",
    ),
    path("api/v1/calculator/payment/", CalculatorView.as_view(), name="calculator"),
    path("api/v1/", include(router.urls)),
]
