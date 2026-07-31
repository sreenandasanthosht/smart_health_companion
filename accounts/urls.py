"""URL map for the accounts app (register, login, logout, onboarding, profile)."""
from django.urls import path

from . import views

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('onboarding/<str:role>/', views.onboarding_view, name='onboarding'),
    path('profile/', views.profile_view, name='profile'),
]
