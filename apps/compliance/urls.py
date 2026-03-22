from django.urls import path
from . import views

app_name = 'compliance'

urlpatterns = [
    # Dashboard
    path('', views.ComplianceDashboardView.as_view(), name='dashboard'),

    # Settings
    path('settings/', views.ComplianceSettingsView.as_view(), name='settings'),

    # Templates
    path('templates/', views.TemplateListView.as_view(), name='template_list'),
    path('templates/create/', views.TemplateCreateView.as_view(), name='template_create'),
    path('templates/<int:pk>/edit/', views.TemplateUpdateView.as_view(), name='template_update'),
    path('templates/<int:pk>/delete/', views.TemplateDeleteView.as_view(), name='template_delete'),

    # Task generation
    path('generate/', views.GenerateTasksView.as_view(), name='generate_tasks'),

    # Tasks
    path('tasks/', views.TaskListView.as_view(), name='task_list'),
    path('tasks/create/', views.TaskCreateView.as_view(), name='task_create'),
    path('tasks/<int:pk>/', views.TaskDetailView.as_view(), name='task_detail'),
    path('tasks/<int:pk>/edit/', views.TaskUpdateView.as_view(), name='task_update'),
    path('tasks/<int:pk>/delete/', views.TaskDeleteView.as_view(), name='task_delete'),
    path('tasks/<int:pk>/status/', views.TaskStatusUpdateView.as_view(), name='task_status_update'),

    # Evidence
    path('tasks/<int:pk>/evidence/', views.EvidenceUploadView.as_view(), name='evidence_upload'),
    path('tasks/<int:pk>/evidence/paste/', views.EvidencePasteUploadView.as_view(), name='evidence_paste'),
    path('tasks/<int:pk>/evidence/<int:evidence_pk>/delete/', views.EvidenceDeleteView.as_view(), name='evidence_delete'),
    path('tasks/<int:pk>/evidence/<int:evidence_pk>/download/', views.EvidenceDownloadView.as_view(), name='evidence_download'),

    # Calendar
    path('calendar/', views.CalendarMonthView.as_view(), name='calendar'),
    path('calendar/year/', views.CalendarYearView.as_view(), name='calendar_year'),

    # Documents
    path('documents/', views.DocumentListView.as_view(), name='document_list'),
    path('documents/upload/', views.DocumentUploadView.as_view(), name='document_upload'),
    path('documents/<int:pk>/download/', views.DocumentDownloadView.as_view(), name='document_download'),
    path('documents/<int:pk>/delete/', views.DocumentDeleteView.as_view(), name='document_delete'),

    # SEC News
    path('news/', views.SECNewsListView.as_view(), name='news_list'),
    path('news/refresh/', views.SECNewsRefreshView.as_view(), name='news_refresh'),
    path('news/<int:pk>/toggle-read/', views.SECNewsMarkReadView.as_view(), name='news_toggle_read'),
    path('news/mark-all-read/', views.SECNewsMarkAllReadView.as_view(), name='news_mark_all_read'),

    # Exports
    path('export/<int:year>/csv/', views.ExportCSVView.as_view(), name='export_csv'),
    path('export/<int:year>/zip/', views.ExportZIPView.as_view(), name='export_zip'),
    path('export/<int:year>/pdf/', views.ExportPDFView.as_view(), name='export_pdf'),

    # Funds
    path('funds/', views.FundListView.as_view(), name='fund_list'),
    path('funds/create/', views.FundCreateView.as_view(), name='fund_create'),
    path('funds/<int:pk>/', views.FundDetailView.as_view(), name='fund_detail'),
    path('funds/<int:pk>/edit/', views.FundUpdateView.as_view(), name='fund_update'),

    # Fund Principals
    path('funds/<int:fund_pk>/principals/create/', views.FundPrincipalCreateView.as_view(), name='principal_create'),
    path('funds/<int:fund_pk>/principals/<int:pk>/edit/', views.FundPrincipalUpdateView.as_view(), name='principal_update'),
    path('funds/<int:fund_pk>/principals/<int:pk>/delete/', views.FundPrincipalDeleteView.as_view(), name='principal_delete'),

    # Investor Jurisdictions
    path('funds/<int:fund_pk>/jurisdictions/create/', views.InvestorJurisdictionCreateView.as_view(), name='jurisdiction_create'),
    path('funds/<int:fund_pk>/jurisdictions/<int:pk>/edit/', views.InvestorJurisdictionUpdateView.as_view(), name='jurisdiction_update'),
    path('funds/<int:fund_pk>/jurisdictions/<int:pk>/delete/', views.InvestorJurisdictionDeleteView.as_view(), name='jurisdiction_delete'),

    # Obligations (renamed from templates)
    path('obligations/', views.TemplateListView.as_view(), name='obligation_list'),
    path('obligations/create/', views.TemplateCreateView.as_view(), name='obligation_create'),
    path('obligations/<int:pk>/edit/', views.TemplateUpdateView.as_view(), name='obligation_update'),
    path('obligations/<int:pk>/delete/', views.TemplateDeleteView.as_view(), name='obligation_delete'),

    # --- Surveys & Certifications ---
    # Templates & Versions
    path('surveys/templates/', views.SurveyTemplateListView.as_view(), name='survey_template_list'),
    path('surveys/templates/<int:pk>/', views.SurveyTemplateDetailView.as_view(), name='survey_template_detail'),
    path('surveys/templates/<int:pk>/publish/', views.SurveyPublishVersionView.as_view(), name='survey_publish_version'),
    
    # Assignments & Dashboard
    path('surveys/dashboard/', views.SurveyDashboardView.as_view(), name='survey_dashboard'),
    path('surveys/my/', views.MySurveysListView.as_view(), name='my_surveys'),
    path('surveys/assign/', views.SurveyAssignPeriodicView.as_view(), name='survey_assign_periodic'),
    
    # Completion & Review
    path('surveys/assignments/<int:pk>/', views.SurveyCompleteView.as_view(), name='survey_complete'),
    path('surveys/assignments/<int:pk>/review/', views.SurveyReviewView.as_view(), name='survey_review'),
    
    # Exceptions
    path('surveys/exceptions/', views.SurveyExceptionListView.as_view(), name='survey_exception_list'),
    
    # Survey Exports
    path('surveys/export/<int:year>/csv/', views.ExportSurveyCSVView.as_view(), name='survey_export_csv'),
]
