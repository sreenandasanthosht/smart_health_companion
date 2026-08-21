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

# DEBUG shows detailed errors; turn OFF (False) in production.
# The fallback below only matters if DEBUG is unset in .env -- your own
# .env currently sets DEBUG=True explicitly for local development, which
# still wins over this default. Before your final demo/submission, set
# DEBUG=False in .env itself (not just here) -- that's the switch that
# actually matters; this fallback is just a safety net for anyone who
# clones the repo without a DEBUG line in their .env at all.
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Separate from ALLOWED_HOSTS: Django's CSRF protection checks the Origin
# header of every POST (login, register, any form) against this list too.
# Without it, forms fail with "CSRF verification failed" even though the
# page itself loads fine -- as happened when accessing through a Cloudflare
# quick tunnel. Empty by default (plain localhost needs nothing extra);
# set e.g. CSRF_TRUSTED_ORIGINS=https://*.trycloudflare.com in .env to
# allow a tunnel domain, wildcard included since the random subdomain
# changes every time the tunnel restarts.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]

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
    'datascience',
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
    # Connection options. utf8mb4 is the full Unicode charset (emoji, Malayalam,
    # anything a patient might type). connect_timeout stops the app hanging for
    # a minute when the database is unreachable -- it fails fast instead.
    DB_OPTIONS = {'charset': 'utf8mb4', 'connect_timeout': 10}

    # A hosted database (Aiven, PlanetScale, RDS...) refuses plain-text
    # connections, so we hand the driver the provider's CA certificate. Set
    # DB_SSL_CA in .env to the certificate's filename; a bare filename is
    # looked up next to manage.py. Leave it empty for a local MySQL, which
    # needs no certificate.
    _ssl_ca = os.getenv('DB_SSL_CA', '').strip()
    if _ssl_ca:
        _ssl_path = Path(_ssl_ca)
        if not _ssl_path.is_absolute():
            _ssl_path = BASE_DIR / _ssl_ca
        DB_OPTIONS['ssl'] = {'ca': str(_ssl_path)}

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.getenv('DB_NAME', 'smart_health_companion'),
            'USER': os.getenv('DB_USER', 'root'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '3306'),
            'OPTIONS': DB_OPTIONS,
            # Reuse each database connection for a minute instead of opening a
            # fresh one per request. Negligible locally; a real speed-up when
            # the database is in a data centre and every handshake costs a
            # round trip over the internet.
            'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', '60')),
            'CONN_HEALTH_CHECKS': True,
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

# --- Session & CSRF cookie security ---
# None of this was set explicitly before -- Django's own defaults are
# reasonable but not health-app-appropriate, and one of them (SECURE) can't
# just be switched on blindly: a cookie marked Secure is refused by the
# browser over plain HTTP, which is exactly how this project runs locally
# (http://127.0.0.1:8000). Tying it to `not DEBUG` means it's off for local
# development and on automatically once DEBUG=False is set for the real
# demo/submission -- see the DEBUG comment above.
SESSION_COOKIE_HTTPONLY = True          # JavaScript can never read the session cookie
SESSION_COOKIE_SECURE = not DEBUG       # HTTPS-only once DEBUG is off
CSRF_COOKIE_SECURE = not DEBUG          # same reasoning, for the CSRF cookie
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7   # a session is valid for 1 week
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # ...and survives closing the browser within that week

# --- Email (password reset) ---
# No real mail server is configured for this project, so by default every
# "sent" email is printed to the runserver console instead -- that's enough
# to demo and test the reset flow end-to-end without an SMTP account. Set
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend in .env (plus
# the EMAIL_HOST_* values below) to send real email later; nothing else in
# the reset views needs to change.
EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'CareNest <no-reply@carenest.local>')
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'

# How long a password-reset link stays valid, in seconds. 3 days is
# Django's own default -- set explicitly here so it's a decision on record,
# not an implicit default someone has to go look up.
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24 * 3

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
