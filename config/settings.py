"""
Django settings for the Smart Health Companion project.
Beginner notes:
  - This file is the "control room": it lists the apps, the database,
    templates, static files, and security keys.
  - Secrets (SECRET_KEY, DB password) are read from a .env file so they
    never get committed to GitHub. Copy .env.example to .env and fill it in.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# BASE_DIR = the project's top folder (where manage.py lives)
BASE_DIR = Path(__file__).resolve().parent.parent

# load variables from a local .env file (not committed to git)
load_dotenv(BASE_DIR / '.env')

# SECURITY: keep the secret key secret in production
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-insecure-change-me')

# DEBUG shows detailed errors; turn OFF (False) in production
DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# --- Applications ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # our apps:
    'accounts',
    'health',
    'providers',
    'core',
    'adminpanel',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # project-wide templates folder (holds base.html)
        'DIRS': [BASE_DIR / 'templates'],
        # also look inside each app's own templates/ folder
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

WSGI_APPLICATION = 'config.wsgi.application'

# --- Database ---
# Uses MySQL. For a quick test without MySQL, set USE_SQLITE=1 in your .env.
if os.getenv('USE_SQLITE', '0') == '1':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'smart_health_companion'),
            'USER': os.getenv('DB_USER', 'root'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Tell Django to use our custom user model (roles + unique_id)
AUTH_USER_MODEL = 'accounts.User'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# --- Static files (CSS, JavaScript, images) ---
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# where login/logout send users (used later)
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
