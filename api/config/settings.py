import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Off unless asked for. manage.py turns it on for local runserver/test; gunicorn (wsgi.py) leaves it off.
DEBUG = os.environ.get('DEBUG', '0').lower() in ('1', 'true')

# Required when DEBUG is off.
SECRET_KEY = (os.environ.get('SECRET_KEY') or 'django-insecure-@as1j&jcv9^qpj5z1ca2&(k-r$m)96b7#r0*vrm2seeu6vg$0s') if DEBUG else os.environ['SECRET_KEY']

ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]

INSTALLED_APPS = ['routing']

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'APP_DIRS': True,
        'OPTIONS': {'context_processors': ['django.template.context_processors.request']},
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',  # ponytail: one box; Redis if >1
        'LOCATION': os.environ.get('CACHE_DIR', BASE_DIR / '.cache'),
        'TIMEOUT': 24 * 3600,
    }
}

# Behind Caddy / the Next.js proxy: build map_url from the client-facing scheme and host.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
