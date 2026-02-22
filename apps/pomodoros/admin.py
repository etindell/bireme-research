"""
Django admin configuration for pomodoros app.
"""
from django.contrib import admin
from .models import Pomodoro


@admin.register(Pomodoro)
class PomodoroAdmin(admin.ModelAdmin):
    list_display = [
        'topic_label', 'user', 'organization', 'is_completed',
        'was_focused', 'duration_minutes', 'started_at', 'completed_at',
    ]
    list_filter = ['organization', 'is_completed', 'was_focused']
    search_fields = ['topic_label', 'user__email']
    date_hierarchy = 'started_at'
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['organization', 'user', 'company', 'created_by', 'updated_by']

    fieldsets = (
        (None, {
            'fields': ('organization', 'user', 'company', 'topic_label')
        }),
        ('Timer', {
            'fields': ('started_at', 'completed_at', 'duration_minutes', 'is_completed')
        }),
        ('Focus', {
            'fields': ('was_focused',)
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',),
        }),
    )
