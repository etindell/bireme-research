"""
Admin configuration for Note models.
"""
from django.contrib import admin

from .models import Note, NoteType


@admin.register(NoteType)
class NoteTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'color', 'order', 'is_default']
    list_filter = ['organization', 'is_default']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['organization', 'order', 'name']


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ['title', 'company', 'note_type', 'created_by', 'created_at', 'is_pinned', 'is_deleted']
    list_filter = ['note_type', 'is_pinned', 'is_deleted', 'organization']
    search_fields = ['title', 'content']
    raw_id_fields = ['organization', 'company', 'parent', 'created_by', 'updated_by', 'deleted_by']
    readonly_fields = ['search_vector', 'created_at', 'updated_at', 'deleted_at']
    filter_horizontal = ['referenced_companies']

    fieldsets = (
        (None, {
            'fields': ('organization', 'company', 'title', 'content')
        }),
        ('Classification', {
            'fields': ('note_type', 'note_date', 'referenced_companies')
        }),
        ('Hierarchy', {
            'fields': ('parent', 'order'),
            'classes': ('collapse',)
        }),
        ('State', {
            'fields': ('is_collapsed', 'is_pinned')
        }),
        ('Search', {
            'fields': ('search_vector',),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by', 'updated_at', 'is_deleted', 'deleted_at', 'deleted_by'),
            'classes': ('collapse',)
        }),
    )
