"""
Forms for events app.
"""
from django import forms

from .models import Event, Guest


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['name', 'date', 'location', 'description', 'email_subject', 'email_body_template']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Annual Dinner 2026',
            }),
            'date': forms.DateTimeInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'type': 'datetime-local',
            }),
            'location': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Restaurant Name, City',
            }),
            'description': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'rows': 3,
                'placeholder': 'Brief description of the event...',
            }),
            'email_subject': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': "You're Invited!",
            }),
            'email_body_template': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'rows': 4,
                'placeholder': 'Optional custom template. Leave blank to auto-generate with AI.',
            }),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class ScreenshotUploadForm(forms.Form):
    image = forms.ImageField(
        widget=forms.FileInput(attrs={
            'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100',
            'accept': 'image/*',
        })
    )


class GuestForm(forms.ModelForm):
    class Meta:
        model = Guest
        fields = ['name', 'email']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Full name',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'email@example.com',
            }),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class RsvpForm(forms.Form):
    """Public RSVP form - no authentication required."""

    rsvp_status = forms.ChoiceField(
        choices=[
            ('yes', 'Yes, I will attend'),
            ('no', 'No, I cannot attend'),
        ],
        widget=forms.RadioSelect(attrs={
            'class': 'h-4 w-4 border-gray-300 text-primary-600 focus:ring-primary-600',
        }),
    )
    food_preference = forms.ChoiceField(
        choices=Guest.FOOD_PREFERENCE_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': 'h-4 w-4 border-gray-300 text-primary-600 focus:ring-primary-600',
        }),
        required=False,
    )
    dietary_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            'rows': 2,
            'placeholder': 'Any additional dietary requirements or allergies...',
        }),
    )
