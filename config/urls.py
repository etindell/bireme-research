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

    # Todos
    path('todos/', include('apps.todos.urls', namespace='todos')),

    # Organizations
    path('organizations/', include('apps.organizations.urls', namespace='organizations')),

    # Search
    path('search/', include('apps.search.urls', namespace='search')),

    # Export
    path('export/', include('apps.export.urls', namespace='export')),

    # News
    path('news/', include('apps.news.urls', namespace='news')),

    # Pomodoros
    path('pomodoros/', include('apps.pomodoros.urls', namespace='pomodoros')),

    # Events
    path('events/', include('apps.events.urls', namespace='events')),

    # Share (public, no auth required)
    path('share/', include('apps.share.urls', namespace='share')),
]

# Development URLs
if settings.DEBUG:
    from django.conf.urls.static import static
    urlpatterns += [
        path('__reload__/', include('django_browser_reload.urls')),
    ]
    # Serve media files in development
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Serve media files in production (for small-scale use)
# Note: For high-traffic or persistent storage, configure cloud storage (S3, etc.)
if not settings.DEBUG:
    from django.views.static import serve
    from django.urls import re_path
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
