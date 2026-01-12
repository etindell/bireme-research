"""
Forms for Organization management.
"""
from django import forms

from .models import Organization, OrganizationMembership


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


class AddMemberForm(forms.Form):
    """Form for adding an existing user to an organization by email."""

    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            'placeholder': 'user@example.com',
        }),
        help_text='Enter the email address of an existing user'
    )

    role = forms.ChoiceField(
        choices=[
            (OrganizationMembership.Role.MEMBER, 'Member - Can view and edit'),
            (OrganizationMembership.Role.ADMIN, 'Admin - Full access + manage members'),
            (OrganizationMembership.Role.VIEWER, 'Viewer - Read-only access'),
        ],
        initial=OrganizationMembership.Role.MEMBER,
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
        })
    )
