"""
URL configuration for Bireme Research platform.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),

    # Authentication (django-allauth)
    path('accounts/', include('allauth.urls')),

    # Core (dashboard)
    path('', include('core.urls')),

    # Companies
    path('companies/', include('apps.companies.urls', namespace='companies')),

    # Notes
    path('notes/', include('apps.notes.urls', namespace='notes')),

    # Organizations
    path('organizations/', include('apps.organizations.urls', namespace='organizations')),

    # Search
    path('search/', include('apps.search.urls', namespace='search')),

    # Export
    path('export/', include('apps.export.urls', namespace='export')),
]

# Development URLs
if settings.DEBUG:
    urlpatterns += [
        path('__reload__/', include('django_browser_reload.urls')),
    ]
