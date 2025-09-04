from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    Patient, Image, Message, Profile, Comment, Model3D, Video, Branch
)

# --- User + Profile inline (role/branches) ---
class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fk_name = "user"
    fields = ("role", "branches", "avatar_url")
    filter_horizontal = ("branches",)

class UserAdmin(BaseUserAdmin):
    inlines = (ProfileInline,)
    list_select_related = ("profile",)
    list_display = (
        "username", "email", "first_name", "last_name",
        "get_role", "get_branches", "is_staff", "is_superuser",
    )
    list_filter = BaseUserAdmin.list_filter + ("profile__role", "profile__branches")
    search_fields = ("username", "email", "first_name", "last_name")

    def get_role(self, obj):
        return getattr(obj.profile, "role", "")
    get_role.short_description = "Role"

    def get_branches(self, obj):
        try:
            return ", ".join(b.name for b in obj.profile.branches.all())
        except Profile.DoesNotExist:
            return ""
    get_branches.short_description = "Branches"

# Replace default User admin
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# --- Branch ---
@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

# --- Patient ---
@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("id", "ptnName", "ptnLastname", "ptnDOB", "usrID", "visibility")
    search_fields = ("ptnName", "ptnLastname")
    list_filter = ("usrID", "visibility")

# --- Image ---
@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ("id", "imgDesc", "ptnID", "usrID")
    search_fields = ("imgDesc",)
    list_filter = ("ptnID", "usrID")

# --- Profile ---
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role", "branches")
    search_fields = ("user__username", "user__email")
    filter_horizontal = ("branches",)

# --- Other models ---
admin.site.register(Message)
admin.site.register(Comment)
admin.site.register(Model3D)
admin.site.register(Video)
