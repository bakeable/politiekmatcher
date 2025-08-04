"""
Django settings for PolitiekMatcher project.

PolitiekMatcher stelt burgers in staat om verkiezingsprogramma's, partijstandpunten
en politiek nieuws op een toegankelijke en transparante manier te verkennen
via een AI-chatinterface en interactieve widgets.
"""

import environ
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Environment variables
env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party apps
    "corsheaders",
    "strawberry.django",
    # Local apps
    "apps.chat",
    "apps.content",
    "apps.scraping",
    "apps.api",
    "apps.profiles",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "politiekmatcher.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "politiekmatcher.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# Use PostgreSQL from environment
try:
    DATABASES = {"default": env.db()}
    # Ensure proper PostgreSQL configuration
    if DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
        DATABASES["default"].update(
            {
                "TEST": {
                    "NAME": "test_politiekmatcher_db",
                },
            }
        )
except Exception as e:
    # Fallback to SQLite for development if PostgreSQL not available
    print(f"⚠️  PostgreSQL not available ({e}), falling back to SQLite")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "nl-nl"

TIME_ZONE = "Europe/Amsterdam"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# OpenAI Configuration
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
TAVILY_API_KEY = env("TAVILY_API_KEY", default="")

# Redis Configuration
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

# Celery Configuration
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE

# Memory management for ML model tasks
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Reduce prefetching to avoid memory issues
CELERY_WORKER_MAX_TASKS_PER_CHILD = (
    10  # Restart workers after 10 tasks to prevent memory leaks
)
CELERY_TASK_TIME_LIMIT = 300  # 5 minutes timeout per task
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4 minutes soft timeout

# Task routing - use different queues for memory-intensive tasks
CELERY_TASK_ROUTES = {
    "apps.profiles.tasks.match_parties_async": {"queue": "ml_tasks"},
    "apps.profiles.tasks.classify_user_response_async": {"queue": "ml_tasks"},
}

# Default queue configuration
CELERY_TASK_DEFAULT_QUEUE = "default"

# CORS Settings (for React frontend)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",  # Vite default port
    "http://127.0.0.1:5173",
]

CORS_ALLOW_CREDENTIALS = True

# GraphQL Configuration
GRAPHQL_URL = "/graphql/"

# Increase request timeout for long-running operations like party matching
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10MB


PARTY_NAME_MAPPINGS = {
    # Common variations and full names to abbreviations
    "VVD": ["VVD", "Volkspartij voor Vrijheid en Democratie"],
    "D66": ["D66", "Democraten 66"],
    "CDA": [
        "CDA",
        "Christen-Democratisch Appèl",
        "Christen Democratisch Appèl",
    ],
    "SP": ["SP", "Socialistische Partij", "Socialistische Partij (SP)"],
    "PVV": ["PVV", "Partij voor de Vrijheid"],
    "CU": ["CU", "ChristenUnie", "Christen Unie"],
    "SGP": ["SGP", "Staatkundig Gereformeerde Partij"],
    "DENK": ["DENK", "Beweging DENK"],
    "FvD": [
        "FvD",
        "Forum voor Democratie",
        "FVD",
        "Forum voor Democratie (FvD)",
        "F.v.D.",
        "F.V.D.",
    ],
    "Volt": ["Volt", "Volt Nederland"],
    "JA21": ["JA21", "Juiste Antwoord 21", "Juiste Antwoord 2021", "Juiste Antwoord"],
    "BBB": ["BBB", "BoerBurgerBeweging", "Boer Burger Beweging"],
    "PvdD": ["PvdD", "Partij voor de Dieren", "P.v.d.D.", "pvddieren"],
    "50PLUS": ["50PLUS", "VijftigPLUS", "50+", "Vijftig Plus"],
    "VNL": ["VNL", "VoorNederland"],
    "Piratenpartij - De Groenen": [
        "PiratenPartij",
        "Piratenpartij",
        "Piraten Partij",
        "PP",
        "Groenen",
        "De Groenen",
        "Piratenpartij - De Groenen",
    ],
    "Partij voor de Sport": [
        "Partij voor de Sport",
        "PvdSport",
        "P.v.d.S.",
        "partijvdsport",
    ],
    "NIDA": ["NIDA"],
    "BIJ1": ["BIJ1", "Bij1", "Bij1 Nederland", "Bij 1"],
    "Code Oranje": ["Code Oranje"],
    "LP": ["LP", "Libertarische Partij", "Libertarian Party", "libertaire partij"],
    "BVNL": ["BVNL", "Belang van Nederland"],
    "Nederland met een plan": [
        "Nederland met een Plan",
        "Nederland met een Plan (NMP)",
        "Nederland met een Plan (NMP)",
        "Nederland met een Plan",
    ],
    "LEF": ["LEF", "Lef", "Lef Nederland"],
    "NSC": ["NSC", "Nieuw Sociaal Contract"],
    "Splinter": ["Splinter"],
    "Basisinkomenpartij": ["Basisinkomenpartij"],
    "GL-PvdA": [
        "Groenlinks / P.v.d.A.",
        "GroenLinks-PvdA",
        "GL-PvdA",
        "GroenLinks PvdA",
        "PvdA",
        "GroenLinks",
        "P.v.d.A.",
        "Partij van de Arbeid",
        "Partij van de Arbeid / GroenLinks",
        "Partij van de Arbeid/GroenLinks",
        "PVDA/GL",
        "pvda/gl",
    ],
}

PARTY_ABBREV_TO_NAME = {
    "VVD": "Volkspartij voor Vrijheid en Democratie",
    "D66": "Democraten 66",
    "CDA": "Christen-Democratisch Appèl",
    "SP": "Socialistische Partij",
    "PVV": "Partij voor de Vrijheid",
    "CU": "ChristenUnie",
    "SGP": "Staatkundig Gereformeerde Partij",
    "DENK": "Beweging DENK",
    "FvD": "Forum voor Democratie",
    "Volt": "Volt Nederland",
    "JA21": "Juiste Antwoord 21",
    "BBB": "BoerBurgerBeweging",
    "PvdD": "Partij voor de Dieren",
    "50PLUS": "VijftigPLUS",
    "VNL": "VoorNederland",
    "Piratenpartij - De Groenen": "Piratenpartij - De Groenen",
    "Partij voor de Sport": "Partij voor de Sport",
    "NIDA": "NIDA",
    "BIJ1": "BIJ1",
    "Code Oranje": "Code Oranje",
    "LP": "Libertarische Partij",
    "BVNL": "Belang van Nederland",
    "Nederland met een plan": "Nederland met een Plan",
    "LEF": "Lef Nederland",
    "NSC": "Nieuw Sociaal Contract",
    "Splinter": "Splinter",
    "Basisinkomenpartij": "Basisinkomenpartij",
    "GL-PvdA": "GroenLinks / P.v.d.A.",
}

# Email settings
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # For development
DEFAULT_FROM_EMAIL = "noreply@politiekmatcher.nl"

# Frontend URL for redirects
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:5173")
