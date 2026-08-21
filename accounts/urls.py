"""URL map for the accounts app (register, login, logout, onboarding, profile, password reset)."""
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import PasswordResetForm, SetPasswordForm

urlpatterns = [
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('onboarding/<str:role>/', views.onboarding_view, name='onboarding'),
    path('profile/', views.profile_view, name='profile'),

    # Password reset -- Django's built-in views handle the token generation,
    # one-time-use link and expiry; only the forms and templates are ours.
    # Four steps, in the order a user walks through them:
    #   1. request  -> enter your email
    #   2. done     -> "check your email" (shown either way -- doesn't
    #                  confirm or deny whether that address is registered)
    #   3. confirm  -> the link from the email; set a new password
    #   4. complete -> success, link back to login
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        form_class=PasswordResetForm,
        email_template_name='accounts/password_reset_email.txt',
        subject_template_name='accounts/password_reset_subject.txt',
        success_url=reverse_lazy('password_reset_done'),
    ), name='password_reset'),

    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html',
    ), name='password_reset_done'),

    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        form_class=SetPasswordForm,
        success_url=reverse_lazy('password_reset_complete'),
    ), name='password_reset_confirm'),

    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    ), name='password_reset_complete'),
]
