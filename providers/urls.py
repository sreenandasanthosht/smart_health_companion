"""URL map for the providers app (directory, appointments, provider dashboard)."""
from django.urls import path
from . import views

urlpatterns = [
    path('directory/', views.directory, name='provider_directory'),
    path('appointments/', views.appointments, name='provider_appointments'),
    path('dashboard/', views.dashboard, name='provider_dashboard'),
    path('pending/', views.pending, name='provider_pending'),
]
