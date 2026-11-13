from django.urls import path

from . import views

urlpatterns = [
    path("csrf/", views.csrf, name="auth-csrf"),
    path("csrf", views.csrf, name="auth-csrf-no-slash"),
    path("login/", views.login_view, name="auth-login"),
    path("login", views.login_view, name="auth-login-no-slash"),
    path("signup-policy/", views.signup_policy_view, name="auth-signup-policy"),
    path("signup-policy", views.signup_policy_view),
    path("register/", views.register_view, name="auth-register"),
    path("register", views.register_view, name="auth-register-no-slash"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("logout", views.logout_view, name="auth-logout-no-slash"),
    path("me/", views.me, name="auth-me"),
    path("me", views.me, name="auth-me-no-slash"),
    # Account management: who the user is, and the two things that need their
    # own proof — the address (a code to the new mailbox) and the password (the
    # current one, or an emailed link when it has been lost).
    path("account/", views.AccountView.as_view(), name="account"),
    path("account", views.AccountView.as_view(), name="account-no-slash"),
    # Privacy rights: a copy of everything the account holds, and erasure
    # (DELETE account/ with the password and a code from delete/request/).
    path("account/export/", views.AccountExportView.as_view(), name="account-export"),
    path(
        "account/export",
        views.AccountExportView.as_view(),
        name="account-export-no-slash",
    ),
    path(
        "account/delete/request/",
        views.AccountDeleteRequestView.as_view(),
        name="account-delete-request",
    ),
    path(
        "account/delete/request",
        views.AccountDeleteRequestView.as_view(),
        name="account-delete-request-no-slash",
    ),
    # Sign out everywhere else.
    path(
        "sessions/revoke/", views.SessionsRevokeView.as_view(), name="sessions-revoke"
    ),
    path(
        "sessions/revoke",
        views.SessionsRevokeView.as_view(),
        name="sessions-revoke-no-slash",
    ),
    # Two steps: ask for a code mailed to the account's own address, then spend
    # it. A signed-in session is not authority to change a password.
    path(
        "password/change/request/",
        views.PasswordChangeRequestView.as_view(),
        name="password-change-request",
    ),
    path("password/change/request", views.PasswordChangeRequestView.as_view()),
    path(
        "password/change/",
        views.PasswordChangeView.as_view(),
        name="password-change",
    ),
    path("password/change", views.PasswordChangeView.as_view()),
    path(
        "password/reset/",
        views.password_reset_request_view,
        name="password-reset",
    ),
    path("password/reset", views.password_reset_request_view),
    path(
        "password/reset/verify/",
        views.password_reset_verify_view,
        name="password-reset-verify",
    ),
    path("password/reset/verify", views.password_reset_verify_view),
    path(
        "password/reset/confirm/",
        views.password_reset_confirm_view,
        name="password-reset-confirm",
    ),
    path("password/reset/confirm", views.password_reset_confirm_view),
    path("email/change/", views.EmailChangeView.as_view(), name="email-change"),
    path("email/change", views.EmailChangeView.as_view(), name="email-change-no-slash"),
    path("email/verify/", views.email_verify_view, name="email-verify"),
    path("email/verify", views.email_verify_view, name="email-verify-no-slash"),
    path("email/resend/", views.email_resend_view, name="email-resend"),
    path("email/resend", views.email_resend_view, name="email-resend-no-slash"),
    path("email/check/", views.email_check_view, name="email-check"),
    path("email/check", views.email_check_view),
    # Interest-profile read/update (object-level permissions).
    path("profile/me/", views.MyProfileView.as_view(), name="profile-me"),
    path("profile/me", views.MyProfileView.as_view(), name="profile-me-no-slash"),
    # The caller's lab memberships (workspace switcher) + a lab's member roster.
    path("labs/", views.MyLabsView.as_view(), name="my-labs"),
    path("labs", views.MyLabsView.as_view(), name="my-labs-no-slash"),
    path(
        "labs/<slug:slug>/members/",
        views.LabMembersView.as_view(),
        name="lab-members",
    ),
    path(
        "labs/<slug:slug>/members",
        views.LabMembersView.as_view(),
        name="lab-members-no-slash",
    ),
    path(
        "labs/<slug:slug>/members/<str:username>/",
        views.LabMemberDetailView.as_view(),
        name="lab-member-detail",
    ),
    path(
        "labs/<slug:slug>/members/<str:username>",
        views.LabMemberDetailView.as_view(),
        name="lab-member-detail-no-slash",
    ),
    # Handing a lab over is its own route, not a role edit: the in-between state
    # — two owners, or none — is one nobody should be able to leave a lab in.
    path(
        "labs/<slug:slug>/transfer-ownership/",
        views.LabTransferOwnershipView.as_view(),
        name="lab-transfer-ownership",
    ),
    path(
        "labs/<slug:slug>/transfer-ownership",
        views.LabTransferOwnershipView.as_view(),
        name="lab-transfer-ownership-no-slash",
    ),
    # Any member leaves a lab themselves (Settings → Your membership).
    path("labs/<slug:slug>/leave/", views.LabLeaveView.as_view(), name="lab-leave"),
    path(
        "labs/<slug:slug>/leave",
        views.LabLeaveView.as_view(),
        name="lab-leave-no-slash",
    ),
    # Both slash and no-slash variants: the browser reaches these through the
    # Next `/api` proxy, which strips the trailing slash — and Django's
    # APPEND_SLASH cannot redirect a POST/PATCH, so a slash-only route 500s.
    path(
        "labs/<slug:slug>/profile/",
        views.LabProfileView.as_view(),
        name="lab-profile",
    ),
    path(
        "labs/<slug:slug>/profile",
        views.LabProfileView.as_view(),
        name="lab-profile-no-slash",
    ),
    # What the department's heads see of the lab's projects (PI sets it).
    path(
        "labs/<slug:slug>/department-sees/",
        views.LabDepartmentSeesView.as_view(),
        name="lab-department-sees",
    ),
    path(
        "labs/<slug:slug>/department-sees",
        views.LabDepartmentSeesView.as_view(),
        name="lab-department-sees-no-slash",
    ),
    # Who can create projects in the lab (PI sets it; any member reads it).
    path(
        "labs/<slug:slug>/project-creation/",
        views.LabProjectCreationView.as_view(),
        name="lab-project-creation",
    ),
    path(
        "labs/<slug:slug>/project-creation",
        views.LabProjectCreationView.as_view(),
        name="lab-project-creation-no-slash",
    ),
    # Lab logo: any member reads (GET streams it); lead/owner/admin upload/clear.
    path(
        "labs/<slug:slug>/logo/",
        views.LabLogoView.as_view(),
        name="lab-logo",
    ),
    path(
        "labs/<slug:slug>/logo",
        views.LabLogoView.as_view(),
        name="lab-logo-no-slash",
    ),
    # What Mylo keeps an eye on for a lab (members read; lead/admin edit).
    path(
        "labs/<slug:slug>/watch/",
        views.LabWatchView.as_view(),
        name="lab-watch",
    ),
    path(
        "labs/<slug:slug>/watch",
        views.LabWatchView.as_view(),
        name="lab-watch-no-slash",
    ),
    # LLM-assisted lab profile synthesis from the PI's free text (no save).
    path(
        "labs/<slug:slug>/intake/synthesize/",
        views.LabIntakeSynthesizeView.as_view(),
        name="lab-intake-synthesize",
    ),
    path(
        "labs/<slug:slug>/intake/synthesize",
        views.LabIntakeSynthesizeView.as_view(),
        name="lab-intake-synthesize-no-slash",
    ),
    # Lab invitations: managers invite + list; invitees see and answer their own.
    path(
        "labs/<slug:slug>/invitations/",
        views.LabInvitationsView.as_view(),
        name="lab-invitations",
    ),
    path(
        "labs/<slug:slug>/invitations",
        views.LabInvitationsView.as_view(),
        name="lab-invitations-no-slash",
    ),
    path(
        "labs/<slug:slug>/invitations/<uuid:pk>/cancel/",
        views.LabInvitationCancelView.as_view(),
        name="lab-invitation-cancel",
    ),
    path(
        "labs/<slug:slug>/invitations/<uuid:pk>/cancel",
        views.LabInvitationCancelView.as_view(),
        name="lab-invitation-cancel-no-slash",
    ),
    path("invitations/", views.MyInvitationsView.as_view(), name="my-invitations"),
    path(
        "invitations",
        views.MyInvitationsView.as_view(),
        name="my-invitations-no-slash",
    ),
    path(
        "invitations/<uuid:pk>/respond/",
        views.InvitationRespondView.as_view(),
        name="invitation-respond",
    ),
    path(
        "invitations/<uuid:pk>/respond",
        views.InvitationRespondView.as_view(),
        name="invitation-respond-no-slash",
    ),
    # Departments: the caller's own, and standing a new one up. Sign-up no longer
    # offers a department account, so this is where one comes from.
    path("departments/", views.MyDepartmentsView.as_view(), name="my-departments"),
    path("departments", views.MyDepartmentsView.as_view()),
    path(
        "departments/<uuid:pk>/profile/",
        views.DeptProfileView.as_view(),
        name="dept-profile",
    ),
    # No-slash twin: the department General page saves through the Next proxy,
    # which strips the slash, and APPEND_SLASH cannot redirect a PATCH.
    path("departments/<uuid:pk>/profile", views.DeptProfileView.as_view()),
    # Department members (effective roster) + direct-member management.
    # Who can create department projects (owner / admin set it).
    path(
        "departments/<uuid:pk>/project-creation/",
        views.DepartmentProjectCreationView.as_view(),
        name="department-project-creation",
    ),
    path(
        "departments/<uuid:pk>/project-creation",
        views.DepartmentProjectCreationView.as_view(),
        name="department-project-creation-no-slash",
    ),
    path(
        "departments/<uuid:pk>/members/",
        views.DeptMembersView.as_view(),
        name="dept-members",
    ),
    path(
        "departments/<uuid:pk>/members",
        views.DeptMembersView.as_view(),
        name="dept-members-no-slash",
    ),
    path(
        "departments/<uuid:pk>/members/<str:username>/",
        views.DeptMemberDetailView.as_view(),
        name="dept-member-detail",
    ),
    path(
        "departments/<uuid:pk>/members/<str:username>",
        views.DeptMemberDetailView.as_view(),
        name="dept-member-detail-no-slash",
    ),
    # Handing a department to a new head moves Department.owner and both
    # membership rows at once — its own route, as for a lab.
    path(
        "departments/<uuid:pk>/transfer-ownership/",
        views.DeptTransferOwnershipView.as_view(),
        name="dept-transfer-ownership",
    ),
    path(
        "departments/<uuid:pk>/transfer-ownership",
        views.DeptTransferOwnershipView.as_view(),
        name="dept-transfer-ownership-no-slash",
    ),
    # A direct member gives up their place (Settings → Your membership).
    path(
        "departments/<uuid:pk>/leave/",
        views.DeptLeaveView.as_view(),
        name="dept-leave",
    ),
    path(
        "departments/<uuid:pk>/leave",
        views.DeptLeaveView.as_view(),
        name="dept-leave-no-slash",
    ),
    # Labs under a department: list, attach an existing lab / create one, detach.
    path(
        "departments/<uuid:pk>/labs/",
        views.DeptLabsView.as_view(),
        name="dept-labs",
    ),
    path(
        "departments/<uuid:pk>/labs",
        views.DeptLabsView.as_view(),
        name="dept-labs-no-slash",
    ),
    path(
        "departments/<uuid:pk>/labs/<slug:slug>/",
        views.DeptLabDetailView.as_view(),
        name="dept-lab-detail",
    ),
    path(
        "departments/<uuid:pk>/labs/<slug:slug>",
        views.DeptLabDetailView.as_view(),
        name="dept-lab-detail-no-slash",
    ),
    # What Mylo keeps an eye on (own only).
    path("watch/me/", views.MyWatchView.as_view(), name="watch-me"),
    path("watch/me", views.MyWatchView.as_view(), name="watch-me-no-slash"),
    # Author import + intake session. Both slash forms so a dev proxy that strips
    # the trailing slash still resolves the POST (matches profile/me + watch/me).
    path("intake/import/", views.ImportAuthorView.as_view(), name="intake-import"),
    path("intake/import", views.ImportAuthorView.as_view()),
    path(
        "intake/synthesize/",
        views.SynthesizeView.as_view(),
        name="intake-synthesize",
    ),
    path("intake/synthesize", views.SynthesizeView.as_view()),
    path("intake/session/", views.IntakeSessionView.as_view(), name="intake-session"),
    path("intake/session", views.IntakeSessionView.as_view()),
    path("intake/confirm/", views.ConfirmIntakeView.as_view(), name="intake-confirm"),
    path("intake/confirm", views.ConfirmIntakeView.as_view()),
    path(
        "intake/clusters/",
        views.ProposeClustersView.as_view(),
        name="intake-clusters",
    ),
    path("intake/clusters", views.ProposeClustersView.as_view()),
    # Join invitations — an emailed invite bound to one address, or a share link
    # with a usage budget and an expiry. Managers create and withdraw them; the
    # last two routes are what the person holding the link talks to.
    path(
        "labs/<slug:slug>/invites/",
        views.LabInvitesView.as_view(),
        name="lab-invites",
    ),
    path("labs/<slug:slug>/invites", views.LabInvitesView.as_view()),
    path(
        "labs/<slug:slug>/invites/<uuid:pk>/revoke/",
        views.LabInviteRevokeView.as_view(),
        name="lab-invite-revoke",
    ),
    path(
        "labs/<slug:slug>/invites/<uuid:pk>/revoke",
        views.LabInviteRevokeView.as_view(),
    ),
    path(
        "labs/<slug:slug>/invites/<uuid:pk>/regenerate/",
        views.LabInviteRegenerateView.as_view(),
        name="lab-invite-regenerate",
    ),
    path(
        "labs/<slug:slug>/invites/<uuid:pk>/regenerate",
        views.LabInviteRegenerateView.as_view(),
    ),
    path(
        "labs/<slug:slug>/attach-requests/",
        views.LabAttachRequestsView.as_view(),
        name="lab-attach-requests",
    ),
    path("labs/<slug:slug>/attach-requests", views.LabAttachRequestsView.as_view()),
    path(
        "labs/<slug:slug>/attach-requests/<uuid:pk>/accept/",
        views.LabAttachRequestRespondView.as_view(),
        name="lab-attach-request-accept",
    ),
    path(
        "labs/<slug:slug>/attach-requests/<uuid:pk>/accept",
        views.LabAttachRequestRespondView.as_view(),
    ),
    path(
        "labs/<slug:slug>/attach-requests/<uuid:pk>/decline/",
        views.LabAttachRequestDeclineView.as_view(),
        name="lab-attach-request-decline",
    ),
    path(
        "labs/<slug:slug>/attach-requests/<uuid:pk>/decline",
        views.LabAttachRequestDeclineView.as_view(),
    ),
    path(
        "departments/<uuid:pk>/invites/",
        views.DeptInvitesView.as_view(),
        name="dept-invites",
    ),
    path("departments/<uuid:pk>/invites", views.DeptInvitesView.as_view()),
    path(
        "departments/<uuid:pk>/invites/<uuid:invite_id>/revoke/",
        views.DeptInviteRevokeView.as_view(),
        name="dept-invite-revoke",
    ),
    path(
        "departments/<uuid:pk>/invites/<uuid:invite_id>/revoke",
        views.DeptInviteRevokeView.as_view(),
    ),
    path(
        "departments/<uuid:pk>/invites/<uuid:invite_id>/regenerate/",
        views.DeptInviteRegenerateView.as_view(),
        name="dept-invite-regenerate",
    ),
    path(
        "departments/<uuid:pk>/invites/<uuid:invite_id>/regenerate",
        views.DeptInviteRegenerateView.as_view(),
    ),
    path("invites/<str:token>/", views.invite_preview_view, name="invite-preview"),
    path("invites/<str:token>", views.invite_preview_view),
    path(
        "invites/<str:token>/accept/",
        views.InviteAcceptView.as_view(),
        name="invite-accept",
    ),
    path(
        "invites/<str:token>/accept",
        views.InviteAcceptView.as_view(),
        name="invite-accept-no-slash",
    ),
]
