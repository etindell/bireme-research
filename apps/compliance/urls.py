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

    # --- Surveys & Certifications ---
    # Templates & Versions
    path('surveys/templates/', views.SurveyTemplateListView.as_view(), name='survey_template_list'),
    path('surveys/templates/<int:pk>/', views.SurveyTemplateDetailView.as_view(), name='survey_template_detail'),
    path('surveys/templates/<int:pk>/edit/', views.SurveyTemplateEditView.as_view(), name='survey_template_edit'),
    path('surveys/templates/<int:pk>/publish/', views.SurveyPublishVersionView.as_view(), name='survey_publish_version'),
    path('surveys/templates/<int:pk>/send/', views.SurveySendView.as_view(), name='survey_send'),

    # Public token-based completion (no login required)
    path('surveys/respond/<uuid:token>/', views.SurveyTokenCompleteView.as_view(), name='survey_token_complete'),

    # Assignments & Dashboard
    path('surveys/dashboard/', views.SurveyDashboardView.as_view(), name='survey_dashboard'),
    path('surveys/my/', views.MySurveysListView.as_view(), name='my_surveys'),
    path('surveys/assign/', views.SurveyAssignPeriodicView.as_view(), name='survey_assign_periodic'),
    
    # Completion & Review
    path('surveys/assignments/<int:pk>/', views.SurveyCompleteView.as_view(), name='survey_complete'),
    path('surveys/assignments/<int:pk>/review/', views.SurveyReviewView.as_view(), name='survey_review'),
    
    # Exceptions
    path('surveys/exceptions/', views.SurveyExceptionListView.as_view(), name='survey_exception_list'),
    path('surveys/exceptions/<int:pk>/', views.SurveyExceptionDetailView.as_view(), name='survey_exception_detail'),

    # Survey evidence download
    path('surveys/evidence/<int:pk>/download/', views.SurveyEvidenceDownloadView.as_view(), name='survey_evidence_download'),
    
    # Survey Exports
    path('surveys/export/<int:year>/csv/', views.ExportSurveyCSVView.as_view(), name='survey_export_csv'),
]
