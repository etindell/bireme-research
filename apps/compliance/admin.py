from django.contrib import admin
from .models import (
    ComplianceSettings, ComplianceObligation, ComplianceTask,
    ComplianceEvidence, ComplianceAuditLog, ComplianceDocument, SECNewsItem,
    Fund, FundPrincipal, InvestorJurisdiction,
    SurveyTemplate, SurveyVersion, SurveyQuestion, SurveyAssignment,
    SurveyResponse, SurveyAnswer, SurveyException, EmployeeCertificationStatus
)


# ============ Survey Admin (dormant — kept for future RIA use) ============

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


# ============ ERA Compliance Admin ============

@admin.register(ComplianceSettings)
class ComplianceSettingsAdmin(admin.ModelAdmin):
    list_display = ['organization', 'firm_name', 'registration_type', 'firm_crd_number']
    list_filter = ['registration_type', 'organization']


@admin.register(Fund)
class FundAdmin(admin.ModelAdmin):
    list_display = ['name', 'entity_type', 'entity_jurisdiction', 'is_active', 'organization']
    list_filter = ['entity_type', 'is_active', 'organization']
    search_fields = ['name']


class PrincipalInline(admin.TabularInline):
    model = FundPrincipal
    extra = 0


class JurisdictionInline(admin.TabularInline):
    model = InvestorJurisdiction
    extra = 0


@admin.register(FundPrincipal)
class FundPrincipalAdmin(admin.ModelAdmin):
    list_display = ['name', 'title', 'fund', 'residency_jurisdiction', 'is_us_resident', 'requires_adv_nr']
    list_filter = ['is_us_resident', 'requires_adv_nr', 'organization']
    search_fields = ['name']


@admin.register(InvestorJurisdiction)
class InvestorJurisdictionAdmin(admin.ModelAdmin):
    list_display = ['jurisdiction_code', 'jurisdiction_name', 'fund', 'first_sale_date', 'blue_sky_filed']
    list_filter = ['country', 'blue_sky_filed', 'organization']
    search_fields = ['jurisdiction_code', 'jurisdiction_name']


@admin.register(ComplianceObligation)
class ComplianceObligationAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'frequency', 'jurisdiction', 'is_active', 'is_placeholder', 'organization']
    list_filter = ['category', 'frequency', 'is_active', 'is_placeholder', 'organization']
    search_fields = ['title']


@admin.register(ComplianceTask)
class ComplianceTaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'due_date', 'status', 'fund', 'delegated_to', 'year', 'organization']
    list_filter = ['status', 'delegated_to', 'year', 'organization']
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
