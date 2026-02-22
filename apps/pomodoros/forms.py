"""
Forms for pomodoro timer.
"""
from django import forms
from apps.companies.models import Company


class PomodoroStartForm(forms.Form):
    """Form to start a new pomodoro session."""

    company = forms.ModelChoiceField(
        queryset=Company.objects.none(),
        required=False,
        empty_label='All Other (General Work)',
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border-0 bg-white py-2 pl-3 pr-10 text-gray-900 ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-primary-600 sm:text-sm sm:leading-6',
        })
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['company'].queryset = Company.objects.filter(
                organization=organization,
                is_deleted=False
            ).order_by('name')
