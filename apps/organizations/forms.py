"""
Forms for Organization management.
"""
from django import forms

from .models import Organization


class OrganizationForm(forms.ModelForm):
    """Form for creating and editing organizations."""

    class Meta:
        model = Organization
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'placeholder': 'Organization name',
            }),
            'description': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm',
                'rows': 3,
                'placeholder': 'Brief description (optional)',
            }),
        }
