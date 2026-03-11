from django.contrib import admin
from .models import (
    ComplianceSettings, ComplianceTaskTemplate, ComplianceTask,
    ComplianceEvidence, ComplianceAuditLog, ComplianceDocument, SECNewsItem,
    SurveyTemplate, SurveyVersion, SurveyQuestion, SurveyAssignment,
    SurveyResponse, SurveyAnswer, SurveyException, EmployeeCertificationStatus
)


class QuestionInline(admin.TabularInline):
    model = SurveyQuestion
    extra = 1


class VersionInline(admin.TabularInline):
    model = SurveyVersion
    extra = 0
    show_change_link = True


@admin.register(SurveyTemplate)
class SurveyTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'cadence', 'audience_type', 'organization', 'is_active']
    list_filter = ['cadence', 'audience_type', 'organization']
    inlines = [VersionInline]


@admin.register(SurveyVersion)
class SurveyVersionAdmin(admin.ModelAdmin):
    list_display = ['template', 'version_number', 'is_published', 'effective_date']
    list_filter = ['is_published', 'template__organization']
    inlines = [QuestionInline]


@admin.register(SurveyAssignment)
class SurveyAssignmentAdmin(admin.ModelAdmin):
    list_display = ['user', 'version', 'status', 'due_date', 'year', 'quarter']
    list_filter = ['status', 'year', 'quarter', 'version__template']
    search_fields = ['user__email']


@admin.register(SurveyException)
class SurveyExceptionAdmin(admin.ModelAdmin):
    list_display = ['summary', 'severity', 'category', 'status', 'assignment']
    list_filter = ['severity', 'category', 'status']


admin.site.register(SurveyResponse)
admin.site.register(SurveyAnswer)
admin.site.register(EmployeeCertificationStatus)


@admin.register(ComplianceSettings)
class ComplianceSettingsAdmin(admin.ModelAdmin):
    list_display = ['organization', 'firm_name', 'monthly_close_due_day']
    list_filter = ['organization']


@admin.register(ComplianceTaskTemplate)
class ComplianceTaskTemplateAdmin(admin.ModelAdmin):
    list_display = ['title', 'frequency', 'organization', 'is_active', 'conditional_flag']
    list_filter = ['frequency', 'is_active', 'organization']
    search_fields = ['title']


@admin.register(ComplianceTask)
class ComplianceTaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'due_date', 'status', 'year', 'organization']
    list_filter = ['status', 'year', 'organization']
    search_fields = ['title']
    date_hierarchy = 'due_date'


@admin.register(ComplianceEvidence)
class ComplianceEvidenceAdmin(admin.ModelAdmin):
    list_display = ['original_filename', 'task', 'uploaded_by', 'created_at']
    list_filter = ['organization']


@admin.register(ComplianceAuditLog)
class ComplianceAuditLogAdmin(admin.ModelAdmin):
    list_display = ['task', 'action_type', 'user', 'created_at']
    list_filter = ['action_type', 'organization']
    readonly_fields = ['task', 'organization', 'action_type', 'old_value', 'new_value', 'description', 'user', 'created_at']


@admin.register(ComplianceDocument)
class ComplianceDocumentAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'organization', 'created_at']
    list_filter = ['category', 'organization']
    search_fields = ['name']


@admin.register(SECNewsItem)
class SECNewsItemAdmin(admin.ModelAdmin):
    list_display = ['title', 'source', 'published_at', 'is_read', 'is_relevant']
    list_filter = ['source', 'is_read', 'is_relevant', 'organization']
    search_fields = ['title']
