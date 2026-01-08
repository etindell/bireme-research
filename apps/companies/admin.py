"""
Admin configuration for Company models.
"""
from django.contrib import admin

from .models import Company, CompanyTicker, CompanyValuation


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


@admin.register(CompanyValuation)
class CompanyValuationAdmin(admin.ModelAdmin):
    list_display = [
        'company', 'as_of_date', 'effective_price', 'calculated_irr',
        'is_active', 'created_at'
    ]
    list_filter = ['is_active', 'as_of_date', 'company__organization']
    search_fields = ['company__name']
    raw_id_fields = ['company', 'created_by', 'updated_by', 'deleted_by']
    readonly_fields = [
        'calculated_irr', 'irr_last_calculated', 'price_last_updated',
        'created_at', 'updated_at'
    ]

    fieldsets = (
        (None, {
            'fields': ('company', 'is_active', 'as_of_date')
        }),
        ('Share Data', {
            'fields': ('shares_outstanding',)
        }),
        ('Price', {
            'fields': ('current_price', 'price_override', 'price_last_updated')
        }),
        ('FCF Forecasts', {
            'fields': ('fcf_year_1', 'fcf_year_2', 'fcf_year_3', 'fcf_year_4', 'fcf_year_5')
        }),
        ('Terminal Value', {
            'fields': ('terminal_value',)
        }),
        ('Calculated Results', {
            'fields': ('calculated_irr', 'irr_last_calculated'),
            'classes': ('collapse',)
        }),
        ('Notes', {
            'fields': ('notes',)
        }),
        ('Audit', {
            'fields': ('created_at', 'created_by', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
