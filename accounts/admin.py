from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


class CustomUserAdmin(UserAdmin):
    """
    Our User model adds two extra fields on top of Django's normal user
    (role, unique_id), so we extend Django's built-in UserAdmin instead of
    using the plain admin.ModelAdmin. This way the admin panel still knows
    how to handle passwords/permissions correctly, and also shows our
    extra fields.
    """
    model = User

    # columns shown on the "Users" list page in /admin/
    list_display = ('username', 'email', 'role', 'unique_id', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'unique_id')
    ordering = ('username',)

    # unique_id is auto-generated in User.save(), so it shouldn't be hand-edited
    readonly_fields = ('unique_id',)

    # add our fields to the "view/edit user" page
    fieldsets = UserAdmin.fieldsets + (
        ('Smart Health Companion info', {'fields': ('role', 'unique_id')}),
    )
    # add our fields to the "add new user" page
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Smart Health Companion info', {'fields': ('role',)}),
    )


admin.site.register(User, CustomUserAdmin)
