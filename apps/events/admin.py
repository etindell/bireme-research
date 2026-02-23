from django.contrib import admin

from .models import Event, EventDate, Guest, GuestAvailability, GuestScreenshot


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['name', 'event_type', 'date', 'location', 'organization', 'created_at']
    list_filter = ['organization', 'event_type', 'date']
    search_fields = ['name', 'location']


@admin.register(EventDate)
class EventDateAdmin(admin.ModelAdmin):
    list_display = ['event', 'date', 'label', 'created_at']
    list_filter = ['event']
    search_fields = ['label']


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'event', 'rsvp_status', 'food_preference', 'email_sent']
    list_filter = ['rsvp_status', 'food_preference', 'email_sent']
    search_fields = ['name', 'email']
    readonly_fields = ['rsvp_token']


@admin.register(GuestAvailability)
class GuestAvailabilityAdmin(admin.ModelAdmin):
    list_display = ['guest', 'event_date', 'is_available']
    list_filter = ['is_available']


@admin.register(GuestScreenshot)
class GuestScreenshotAdmin(admin.ModelAdmin):
    list_display = ['event', 'is_processed', 'created_at']
    list_filter = ['is_processed']
