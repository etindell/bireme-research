"""
Django admin configuration for todos app.
"""
from django.contrib import admin
from .models import Todo, TodoCategory, WatchlistQuickAdd


@admin.register(TodoCategory)
class TodoCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'category_type', 'color', 'order']
    list_filter = ['organization', 'category_type']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    ordering = ['organization', 'order', 'name']


class WatchlistQuickAddInline(admin.TabularInline):
    model = WatchlistQuickAdd
    extra = 0
    readonly_fields = ['created_at', 'created_company']
    fields = ['ticker', 'alert_price', 'note', 'is_processed', 'created_company', 'created_at']


@admin.register(Todo)
class TodoAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'organization', 'company', 'category',
        'todo_type', 'is_completed', 'is_auto_generated', 'created_at'
    ]
    list_filter = [
        'organization', 'category', 'todo_type',
        'is_completed', 'is_auto_generated', 'is_deleted'
    ]
    search_fields = ['title', 'description', 'company__name']
    date_hierarchy = 'created_at'
    readonly_fields = ['completed_at', 'completed_by', 'created_at', 'updated_at']
    raw_id_fields = ['organization', 'company', 'category', 'created_by', 'updated_by', 'deleted_by']
    inlines = [WatchlistQuickAddInline]

    fieldsets = (
        (None, {
            'fields': ('organization', 'title', 'description', 'company')
        }),
        ('Categorization', {
            'fields': ('category', 'todo_type', 'quarter', 'fiscal_year')
        }),
        ('Status', {
            'fields': ('is_completed', 'completed_at', 'completed_by')
        }),
        ('Investor Letter', {
            'fields': ('investor_letter_notes',),
            'classes': ('collapse',),
        }),
        ('Metadata', {
            'fields': ('is_auto_generated', 'is_deleted'),
            'classes': ('collapse',),
        }),
        ('Audit', {
            'fields': ('created_at', 'updated_at', 'created_by', 'updated_by'),
            'classes': ('collapse',),
        }),
    )


@admin.register(WatchlistQuickAdd)
class WatchlistQuickAddAdmin(admin.ModelAdmin):
    list_display = ['ticker', 'todo', 'alert_price', 'is_processed', 'created_at']
    list_filter = ['is_processed']
    search_fields = ['ticker', 'note']
    raw_id_fields = ['todo', 'created_company']
    readonly_fields = ['created_at']
