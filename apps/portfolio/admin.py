from django.contrib import admin
from .models import PortfolioSnapshot, PortfolioPosition


class PortfolioPositionInline(admin.TabularInline):
    model = PortfolioPosition
    extra = 0
    readonly_fields = ('irr', 'irr_source')


@admin.register(PortfolioSnapshot)
class PortfolioSnapshotAdmin(admin.ModelAdmin):
    list_display = ('name', 'as_of_date', 'organization', 'total_irr', 'created_at')
    list_filter = ('organization', 'as_of_date')
    inlines = [PortfolioPositionInline]


@admin.register(PortfolioPosition)
class PortfolioPositionAdmin(admin.ModelAdmin):
    list_display = ('ticker', 'name_extracted', 'current_weight', 'proposed_weight', 'irr', 'snapshot')
    list_filter = ('snapshot',)
