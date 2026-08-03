"""
Django settings for the CareNest project.
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
    'nursing',
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
                # live counts for the Admin sidebar
                'adminpanel.context_processors.platform_stats',
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

# where login/logout send users
LOGIN_URL = 'login'  # used by @login_required when a page needs a real session
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'home'

# --- Document extraction (process-and-discard) ---
# Django normally streams uploads larger than 2.5 MB to a temporary FILE on
# disk. That would silently break the promise that an uploaded prescription
# is never written to storage, so we force every upload to stay in memory and
# cap the size instead. Anything larger is rejected rather than spilled.
FILE_UPLOAD_HANDLERS = ['django.core.files.uploadhandler.MemoryFileUploadHandler']
FILE_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024   # 15 MB
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

# Path to the Tesseract binary. Windows installs usually need this set in .env,
# e.g. TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
TESSERACT_CMD = os.getenv('TESSERACT_CMD', '')

# --- LLM used to structure OCR text (Phase 2) ---
# PRIVACY: when a key is configured, the OCR *text* of a prescription is sent
# to this provider. The image itself never leaves the machine. With no key,
# the system falls back to the local rule-based parser and nothing is sent.
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'gemini')
LLM_API_KEY = os.getenv('LLM_API_KEY', '')
LLM_MODEL = os.getenv('LLM_MODEL', 'gemini-2.0-flash')
LLM_TIMEOUT_SECONDS = int(os.getenv('LLM_TIMEOUT_SECONDS', '20'))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField' 
