from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.csrf, name="auth-csrf"),
    path("csrf", views.csrf, name="auth-csrf-no-slash"),
    path("login/", views.login_view, name="auth-login"),
    path("login", views.login_view, name="auth-login-no-slash"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("logout", views.logout_view, name="auth-logout-no-slash"),
    path("me/", views.me, name="auth-me"),
    path("me", views.me, name="auth-me-no-slash"),
]
