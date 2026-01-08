"""
Admin configuration for Company models.
"""
from django.contrib import admin

from .models import Company, CompanyTicker


class CompanyTickerInline(admin.TabularInline):
    model = CompanyTicker
    extra = 1


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'status', 'sector', 'updated_at', 'is_deleted']
    list_filter = ['status', 'sector', 'organization', 'is_deleted']
    search_fields = ['name', 'description', 'thesis']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['search_vector', 'created_at', 'updated_at', 'created_by', 'deleted_at', 'deleted_by']
    inlines = [CompanyTickerInline]
    raw_id_fields = ['organization', 'created_by', 'updated_by', 'deleted_by']

    fieldsets = (
        (None, {
            'fields': ('organization', 'name', 'slug', 'description', 'website')
        }),
        ('Classification', {
            'fields': ('status', 'sector', 'country')
        }),
        ('Investment', {
            'fields': ('thesis', 'market_cap')
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


@admin.register(CompanyTicker)
class CompanyTickerAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'exchange', 'company', 'is_primary']
    list_filter = ['exchange', 'is_primary']
    search_fields = ['symbol', 'company__name']
    raw_id_fields = ['company']
