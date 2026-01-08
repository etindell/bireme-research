"""
Admin configuration for Organization models.
"""
from django.contrib import admin

from .models import Organization, OrganizationMembership


class OrganizationMembershipInline(admin.TabularInline):
    model = OrganizationMembership
    extra = 1
    raw_id_fields = ['user']
    fields = ['user', 'role', 'is_default', 'is_deleted']


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'get_member_count', 'created_at', 'is_deleted']
    list_filter = ['is_deleted', 'created_at']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'deleted_at', 'deleted_by']
    inlines = [OrganizationMembershipInline]

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description')
        }),
        ('Settings', {
            'fields': ('settings',),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by', 'updated_at', 'is_deleted', 'deleted_at', 'deleted_by'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrganizationMembership)
class OrganizationMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'role', 'is_default', 'created_at', 'is_deleted']
    list_filter = ['role', 'is_default', 'is_deleted', 'organization']
    search_fields = ['user__email', 'organization__name']
    raw_id_fields = ['user', 'organization']
    readonly_fields = ['created_at', 'updated_at', 'created_by', 'deleted_at', 'deleted_by']
