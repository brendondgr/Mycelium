from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.csrf, name="auth-csrf"),
    path("csrf", views.csrf, name="auth-csrf-no-slash"),
    path("login/", views.login_view, name="auth-login"),
    path("login", views.login_view, name="auth-login-no-slash"),
    path("register/", views.register_view, name="auth-register"),
    path("register", views.register_view, name="auth-register-no-slash"),
    path("verify-email/", views.verify_email_view, name="auth-verify-email"),
    path("verify-email", views.verify_email_view, name="auth-verify-email-no-slash"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("logout", views.logout_view, name="auth-logout-no-slash"),
    path("me/", views.me, name="auth-me"),
    path("me", views.me, name="auth-me-no-slash"),
    # Interest-profile read/update (object-level permissions).
    path("profile/me/", views.MyProfileView.as_view(), name="profile-me"),
    path(
        "labs/<slug:slug>/profile/",
        views.LabProfileView.as_view(),
        name="lab-profile",
    ),
    path(
        "departments/<uuid:pk>/profile/",
        views.DeptProfileView.as_view(),
        name="dept-profile",
    ),
    # Author import + intake session.
    path("intake/import/", views.ImportAuthorView.as_view(), name="intake-import"),
    path(
        "intake/synthesize/",
        views.SynthesizeView.as_view(),
        name="intake-synthesize",
    ),
    path("intake/session/", views.IntakeSessionView.as_view(), name="intake-session"),
    path("intake/confirm/", views.ConfirmIntakeView.as_view(), name="intake-confirm"),
]
