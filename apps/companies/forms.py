"""
Forms for Company management.
"""
from django import forms
from django.forms import inlineformset_factory

from .models import Company, CompanyTicker, CompanyValuation


class CompanyForm(forms.ModelForm):
    """Form for creating and editing companies."""

    # Optional file upload for importing notes when creating a company
    notes_file = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100',
            'accept': '.md,.txt',
        }),
        help_text='Optional: Import notes from a Markdown file. Company name will be taken from the file.'
    )

    def __init__(self, *args, **kwargs):
        # Remove organization kwarg passed by OrganizationViewMixin
        kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)
        # Make name optional - can come from uploaded file
        self.fields['name'].required = False

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        notes_file = cleaned_data.get('notes_file')
        status = cleaned_data.get('status')
        alert_price = cleaned_data.get('alert_price')
        alert_price_reason = cleaned_data.get('alert_price_reason')

        # Require either a name or a notes file (which contains the name)
        if not name and not notes_file:
            self.add_error('name', 'Company name is required (or upload a notes file).')

        # Require alert price and reason for watchlist companies
        if status == Company.Status.WATCHLIST:
            if not alert_price:
                self.add_error('alert_price', 'Alert price is required for Watchlist companies.')
            if not alert_price_reason:
                self.add_error('alert_price_reason', 'Please explain why you chose this alert price.')

        return cleaned_data

    class Meta:
        model = Company
        fields = [
            'name', 'description', 'website', 'status', 'sector', 'country', 'thesis',
            'alert_price', 'alert_price_reason'
        ]
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
            'alert_price': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Price to trigger deeper research',
                'step': '0.01',
            }),
            'alert_price_reason': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'e.g., 10x FCF, below book value, etc.',
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


class CompanyValuationForm(forms.ModelForm):
    """Form for creating and editing company valuations."""

    def __init__(self, *args, **kwargs):
        kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = CompanyValuation
        fields = [
            'shares_outstanding',
            'fcf_year_1', 'fcf_year_2', 'fcf_year_3', 'fcf_year_4', 'fcf_year_5',
            'terminal_value',
            'price_override',
            'as_of_date',
            'notes',
            'is_active',
        ]
        widgets = {
            'shares_outstanding': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'e.g., 1500 (in millions)',
                'step': '0.01',
            }),
            'fcf_year_1': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'step': '0.01',
            }),
            'fcf_year_2': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'step': '0.01',
            }),
            'fcf_year_3': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'step': '0.01',
            }),
            'fcf_year_4': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'step': '0.01',
            }),
            'fcf_year_5': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'step': '0.01',
            }),
            'terminal_value': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'step': '0.01',
            }),
            'price_override': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Leave blank to use Yahoo Finance price',
                'step': '0.01',
            }),
            'as_of_date': forms.DateInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'type': 'date',
            }),
            'notes': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'rows': 3,
                'placeholder': 'Valuation assumptions and notes...',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600',
            }),
        }
