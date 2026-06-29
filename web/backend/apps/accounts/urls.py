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
    # The caller's lab memberships (workspace switcher) + a lab's member roster.
    path("labs/", views.MyLabsView.as_view(), name="my-labs"),
    path("labs", views.MyLabsView.as_view(), name="my-labs-no-slash"),
    path(
        "labs/<slug:slug>/members/",
        views.LabMembersView.as_view(),
        name="lab-members",
    ),
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
    # What Milo keeps an eye on (own only).
    path("watch/me/", views.MyWatchView.as_view(), name="watch-me"),
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
