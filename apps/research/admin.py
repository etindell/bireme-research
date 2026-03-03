from django.contrib import admin
from .models import ResearchProfile, ResearchJob


@admin.register(ResearchProfile)
class ResearchProfileAdmin(admin.ModelAdmin):
    list_display = ('company', 'ir_url', 'ceo_name', 'cfo_name')
    search_fields = ('company__name', 'ceo_name', 'cfo_name')
    raw_id_fields = ('company',)


@admin.register(ResearchJob)
class ResearchJobAdmin(admin.ModelAdmin):
    list_display = ('company', 'status', 'files_found', 'videos_found', 'created_at')
    list_filter = ('status',)
    search_fields = ('company__name',)
    raw_id_fields = ('company',)
    readonly_fields = ('prompt_text', 'config_snapshot')
