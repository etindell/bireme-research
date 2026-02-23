from django.contrib import admin

from .models import Event, Guest, GuestScreenshot


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'location', 'organization', 'created_at']
    list_filter = ['organization', 'date']
    search_fields = ['name', 'location']


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'event', 'rsvp_status', 'food_preference', 'email_sent']
    list_filter = ['rsvp_status', 'food_preference', 'email_sent']
    search_fields = ['name', 'email']
    readonly_fields = ['rsvp_token']


@admin.register(GuestScreenshot)
class GuestScreenshotAdmin(admin.ModelAdmin):
    list_display = ['event', 'is_processed', 'created_at']
    list_filter = ['is_processed']
