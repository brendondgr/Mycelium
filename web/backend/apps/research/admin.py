from django.contrib import admin

from .models import Project, ProjectInvitation, ProjectMember


class ProjectMemberInline(admin.TabularInline):
    model = ProjectMember
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "scope", "created_at")
    search_fields = ("name",)
    inlines = (ProjectMemberInline,)


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ("project", "user", "created_at")
    search_fields = ("project__name", "user__username")


@admin.register(ProjectInvitation)
class ProjectInvitationAdmin(admin.ModelAdmin):
    list_display = ("project", "invitee", "inviter", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("project__name", "invitee__username", "inviter__username")
