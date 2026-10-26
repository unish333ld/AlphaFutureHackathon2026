import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY to a random string of at least 50 characters."
    )
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
CSRF_TRUSTED_ORIGINS = [x for x in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if x]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "accounts",
    "companies",
    "products",
    "applications",
    "checks",
    "decisions",
    "offers",
    "agreements",
    "assistant",
    "api",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "alfa_credit"),
        "USER": os.getenv("DB_USER", "alfa_credit"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "55432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"options": "-c statement_timeout=10000 -c lock_timeout=5000"},
    }
}
AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 60 * 60 * 8
SESSION_COOKIE_SECURE = os.getenv("DJANGO_COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
CSRF_FAILURE_VIEW = "common.exceptions.csrf_failure"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 262144
LOGIN_REDIRECT_URL = "/api/docs/"
LOGOUT_REDIRECT_URL = "/api/docs/"
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
DEMO_SIGNATURE_ENABLED = os.getenv("DEMO_SIGNATURE_ENABLED", "true").lower() == "true"
PDF_RENDER_TIMEOUT_SECONDS = 15

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "api.schema.ContractAutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "COERCE_DECIMAL_TO_STRING": True,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "user": "300/min",
        "login": "10/min",
        "assistant": os.getenv("AI_USER_RATE", "10/min"),
    },
    "EXCEPTION_HANDLER": "common.exceptions.exception_handler",
}

AI_ENABLED = os.getenv("AI_ENABLED", "false").lower() == "true"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "compatible").lower()
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://host.docker.internal:11434/v1").rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", "") or (
    os.getenv("OPENROUTER_API_KEY", "") if LLM_PROVIDER == "openrouter" else ""
)
LLM_OPENROUTER_FREE_ONLY = os.getenv("LLM_OPENROUTER_FREE_ONLY", "true").lower() == "true"
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
LLM_FALLBACK_MODELS = tuple(
    model.strip() for model in os.getenv("LLM_FALLBACK_MODELS", "").split(",") if model.strip()
)
LLM_LOCAL_FALLBACK_BASE_URL = os.getenv("LLM_LOCAL_FALLBACK_BASE_URL", "").rstrip("/")
LLM_LOCAL_FALLBACK_MODEL = os.getenv("LLM_LOCAL_FALLBACK_MODEL", "qwen3:4b-instruct-2507-q4_K_M")
LLM_TIMEOUT_SECONDS = min(max(float(os.getenv("LLM_TIMEOUT_SECONDS", "40")), 1), 40)
LLM_TOTAL_TIMEOUT_SECONDS = min(max(float(os.getenv("LLM_TOTAL_TIMEOUT_SECONDS", "70")), 1), 75)
LLM_MAX_OUTPUT_TOKENS = min(max(int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "768")), 128), 2048)
LLM_MAX_CONTEXT_CHARS = min(max(int(os.getenv("LLM_MAX_CONTEXT_CHARS", "20000")), 4000), 40000)
AI_MAX_MESSAGE_LENGTH = min(max(int(os.getenv("AI_MAX_MESSAGE_LENGTH", "2000")), 100), 4000)
AI_HISTORY_DAYS = min(max(int(os.getenv("AI_HISTORY_DAYS", "7")), 1), 30)
SPECTACULAR_SETTINGS = {
    "TITLE": "Умный кредитный кабинет предпринимателя",
    "DESCRIPTION": (
        "Хакатонный backend: синтетические компании, локальные проверки, условная подпись "
        "и моделируемая выдача. Деньги передаются строками в рублях, сроки — в месяцах. "
        "Для Try it out [войдите в сессию](/api/session/login/) в той же вкладке. "
        "Swagger передаёт session cookie и X-CSRFToken автоматически. "
        "Изменяющие действия требуют актуальный lock_version из карточки заявки."
    ),
    "VERSION": "1.4.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "displayRequestDuration": True,
        "persistAuthorization": False,
    },
    "ENUM_NAME_OVERRIDES": {
        "DemoAssumptionEnum": ["demo_assumption"],
        "ApplicationStatusEnum": "applications.models.Application.Status",
        "OfferStatusEnum": "offers.models.Offer.Status",
        "CheckStatusEnum": "checks.models.CheckResult.Status",
        "CompanyStatusEnum": "companies.models.Company.Status",
    },
}
