"""
Django development settings for Bireme Research platform.
"""
from .base import *

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1']

# Development-specific apps
INSTALLED_APPS += [
    'django_browser_reload',
]

MIDDLEWARE += [
    'django_browser_reload.middleware.BrowserReloadMiddleware',
]

# Use console email backend in development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Make email verification optional in development
ACCOUNT_EMAIL_VERIFICATION = 'optional'

# Database - use SQLite for development if PostgreSQL not available
# For full-text search, you'll need PostgreSQL
USE_SQLITE = env.bool('USE_SQLITE', default=True)

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env('DB_NAME', default='bireme_research'),
            'USER': env('DB_USER', default='postgres'),
            'PASSWORD': env('DB_PASSWORD', default='postgres'),
            'HOST': env('DB_HOST', default='localhost'),
            'PORT': env('DB_PORT', default='5432'),
        }
    }

# Disable WhiteNoise compression in development
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

# More verbose logging in development
LOGGING['root']['level'] = 'DEBUG'
