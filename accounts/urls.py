"""URL map for the accounts app (register, login, onboarding)."""
from django.urls import path
from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('onboarding/<str:role>/', views.onboarding_view, name='onboarding'),
]
