"""
Forms for Company management.
"""
from django import forms
from django.forms import inlineformset_factory

from .models import Company, CompanyTicker


class CompanyForm(forms.ModelForm):
    """Form for creating and editing companies."""

    class Meta:
        model = Company
        fields = ['name', 'description', 'website', 'status', 'sector', 'country', 'thesis']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Company name',
            }),
            'description': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'rows': 3,
                'placeholder': 'Brief description',
            }),
            'website': forms.URLInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'https://example.com',
            }),
            'status': forms.Select(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            }),
            'sector': forms.Select(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            }),
            'country': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Country',
            }),
            'thesis': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'rows': 5,
                'placeholder': 'Investment thesis...',
            }),
        }


class CompanyTickerForm(forms.ModelForm):
    """Form for company ticker."""

    class Meta:
        model = CompanyTicker
        fields = ['symbol', 'exchange', 'is_primary']
        widgets = {
            'symbol': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'AAPL',
            }),
            'exchange': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'NASDAQ',
            }),
            'is_primary': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600',
            }),
        }


# Inline formset for tickers
CompanyTickerFormSet = inlineformset_factory(
    Company,
    CompanyTicker,
    form=CompanyTickerForm,
    extra=1,
    can_delete=True,
)


class CompanyStatusForm(forms.ModelForm):
    """Simple form for updating company status via HTMX."""

    class Meta:
        model = Company
        fields = ['status']
