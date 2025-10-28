import os
from pathlib import Path
import dj_database_url
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'booknimbus-key')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = ['book-nimbus.onrender.com', 'localhost', '127.0.0.1']
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://postgres.arwnfwtjpjhegtgdrpmi:1MwqTio7vomkZLdx@aws-1-ap-south-1.pooler.supabase.com:5432/postgres'
)

# Add these to INSTALLED_APPS
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Third party apps
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    'app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Add this
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'app.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'app/templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'app.wsgi.application'

# Database (Supabase PostgreSQL)
DATABASES = {
    'default': dj_database_url.config(
        default=DATABASE_URL,
        conn_max_age=600,
        ssl_require=True
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Language & Timezone
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files configuration
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',  # Make sure this directory exists
    BASE_DIR / 'app' / 'static',  # Alternative location
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files configuration (for file uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# File upload settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50MB
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755

# Make sure you collect static files
# Run: python manage.py collectstatic

# Default field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CSRF - UPDATE THIS FOR RENDER
CSRF_TRUSTED_ORIGINS = [
    'https://book-nimbus.onrender.com',
    'http://localhost:8000',
    'http://127.0.0.1:8000'
]

# Session settings for production
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_TIMEOUT = 30
EMAIL_USE_SSL = False
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', 'booknimbus@gmail.com')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', 'cfpt bvtw cqmd ehja')

# Allauth Configuration
SITE_ID = 1

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Allauth settings
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_AUTHENTICATION_METHOD = 'username_email'
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_UNIQUE_EMAIL = True
LOGIN_REDIRECT_URL = '/home/'
LOGOUT_REDIRECT_URL = '/'

# Social Account settings - UPDATE WITH ENVIRONMENT VARIABLES
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        },
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID', '1098327710097-5mqs9s1linj3rqck41phtl7ibh18u5ra.apps.googleusercontent.com'),
            'secret': os.environ.get('GOOGLE_CLIENT_SECRET', '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'),
            'key': ''
        }
    }
}

# Auto-create users with social accounts
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'


# Supabase Configuration
SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://arwnfwtjpjhegtgdrpmi.supabase.co')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyd25md3RqcGpoZWd0Z2RycG1pIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjAwMTM5MjAsImV4cCI6MjA3NTU4OTkyMH0.JUf22-Rt6LLnGjWULe4VZYNg_tH5aVlgclxx7JKL3yA')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyd25md3RqcGpoZWd0Z2RycG1pIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MDAxMzkyMCwiZXhwIjoyMDc1NTg5OTIwfQ.FPYRFHub7dGv7zOuHitIbpcUYiVRd39WWuaK9vvD7pc')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFyd25md3RqcGpoZWd0Z2RycG1pIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MDk2ODQ0NDMsImV4cCI6MjAyNTI2MDQ0M30.17OFpqpV3TzV_f1z_v0DlZ5q2gVxx6AlEAq2O6xQb6M')

# Logging configuration - ADD THIS AT THE END
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
