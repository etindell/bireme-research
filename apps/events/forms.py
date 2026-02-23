"""
Forms for events app.
"""
from django import forms

from .models import Event, EventDate, Guest

INPUT_CLASS = 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6'
RADIO_CLASS = 'h-4 w-4 border-gray-300 text-primary-600 focus:ring-primary-600'


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['event_type', 'name', 'date', 'location', 'description', 'email_subject', 'email_body_template']
        widgets = {
            'event_type': forms.RadioSelect(attrs={
                'class': RADIO_CLASS,
            }),
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'Annual Dinner 2026',
            }),
            'date': forms.DateTimeInput(attrs={
                'class': INPUT_CLASS,
                'type': 'datetime-local',
            }),
            'location': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'Restaurant Name, City',
            }),
            'description': forms.Textarea(attrs={
                'class': INPUT_CLASS,
                'rows': 3,
                'placeholder': 'Brief description of the event...',
            }),
            'email_subject': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': "You're Invited!",
            }),
            'email_body_template': forms.Textarea(attrs={
                'class': INPUT_CLASS,
                'rows': 4,
                'placeholder': 'Optional custom template. Leave blank to auto-generate with AI.',
            }),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['date'].required = False

    def clean(self):
        cleaned_data = super().clean()
        event_type = cleaned_data.get('event_type')
        date = cleaned_data.get('date')
        if event_type == 'rsvp' and not date:
            self.add_error('date', 'Date is required for RSVP events.')
        return cleaned_data


class EventDateForm(forms.ModelForm):
    class Meta:
        model = EventDate
        fields = ['date', 'label']
        widgets = {
            'date': forms.DateTimeInput(attrs={
                'class': INPUT_CLASS,
                'type': 'datetime-local',
            }),
            'label': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'e.g. Tuesday evening',
            }),
        }


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
                'class': INPUT_CLASS,
                'placeholder': 'Full name',
            }),
            'email': forms.EmailInput(attrs={
                'class': INPUT_CLASS,
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
            'class': RADIO_CLASS,
        }),
    )
    food_preference = forms.ChoiceField(
        choices=Guest.FOOD_PREFERENCE_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': RADIO_CLASS,
        }),
        required=False,
    )
    dietary_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': INPUT_CLASS,
            'rows': 2,
            'placeholder': 'Any additional dietary requirements or allergies...',
        }),
    )


class AvailabilityForm(forms.Form):
    """Public availability form for poll-type events."""

    food_preference = forms.ChoiceField(
        choices=Guest.FOOD_PREFERENCE_CHOICES,
        widget=forms.RadioSelect(attrs={
            'class': RADIO_CLASS,
        }),
        required=False,
    )
    dietary_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': INPUT_CLASS,
            'rows': 2,
            'placeholder': 'Any additional dietary requirements or allergies...',
        }),
    )

    def __init__(self, *args, event_dates=None, **kwargs):
        super().__init__(*args, **kwargs)
        if event_dates:
            for ed in event_dates:
                self.fields[f'date_{ed.pk}'] = forms.BooleanField(
                    required=False,
                    label=str(ed),
                    widget=forms.CheckboxInput(attrs={
                        'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600',
                    }),
                )
