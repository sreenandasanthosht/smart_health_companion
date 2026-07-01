"""
Top-level URL routing (the "waiter" that maps web addresses to code).
/admin/ -> Django's built-in admin site (used by the single superuser)
/       -> handled by the core app
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]
