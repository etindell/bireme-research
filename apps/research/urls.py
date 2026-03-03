"""
URL configuration for research app.
"""
from django.urls import path
from . import views

app_name = 'research'

urlpatterns = [
    path('<slug:slug>/modal/', views.ResearchModalView.as_view(), name='modal'),
    path('<slug:slug>/generate/', views.GeneratePromptView.as_view(), name='generate'),
    path('<slug:slug>/history/', views.ResearchJobListView.as_view(), name='history'),
    path('<slug:slug>/jobs/<int:job_id>/update/', views.UpdateJobStatusView.as_view(), name='update_job'),
]
