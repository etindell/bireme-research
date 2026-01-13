"""
Forms for Note management.
"""
from django import forms

from .models import Note, NoteType
from apps.companies.models import Company


class NoteForm(forms.ModelForm):
    """Form for creating and editing notes."""

    referenced_companies = forms.ModelMultipleChoiceField(
        queryset=Company.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
        }),
        help_text='Tag other companies mentioned in this note'
    )

    class Meta:
        model = Note
        fields = ['company', 'title', 'content', 'note_type', 'referenced_companies', 'note_date', 'written_at']
        widgets = {
            'company': forms.Select(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            }),
            'title': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Note title (the bullet point)',
            }),
            'content': forms.Textarea(attrs={
                'class': 'block w-full rounded-t-none rounded-b-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'rows': 6,
                'placeholder': 'Detailed notes...',
            }),
            'note_type': forms.Select(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            }),
            'note_date': forms.DateInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'type': 'date',
            }),
            'written_at': forms.DateTimeInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'type': 'datetime-local',
            }),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)

        if organization:
            # Filter companies and note types by organization
            self.fields['company'].queryset = Company.objects.filter(
                organization=organization,
                is_deleted=False
            )
            self.fields['referenced_companies'].queryset = Company.objects.filter(
                organization=organization,
                is_deleted=False
            )
            self.fields['note_type'].queryset = NoteType.objects.filter(
                organization=organization
            )


class QuickNoteForm(forms.ModelForm):
    """Simplified form for quick note creation."""

    class Meta:
        model = Note
        fields = ['title', 'content', 'note_type']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Note title...',
            }),
            'content': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'rows': 3,
                'placeholder': 'Details (optional)...',
            }),
            'note_type': forms.Select(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            }),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['note_type'].queryset = NoteType.objects.filter(
                organization=organization
            )


class ImportNotesForm(forms.Form):
    """Form for importing notes from a Markdown file."""

    company = forms.ModelChoiceField(
        queryset=Company.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
        }),
        help_text='Select company for single-company import, or leave blank for batch import'
    )

    file = forms.FileField(
        widget=forms.FileInput(attrs={
            'class': 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100',
            'accept': '.md,.txt',
        }),
        help_text='Upload a Markdown (.md) or text (.txt) file'
    )

    note_type = forms.ModelChoiceField(
        queryset=NoteType.objects.none(),
        required=False,
        widget=forms.Select(attrs={
            'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
        }),
        help_text='Optional: Assign a type to all imported notes'
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['company'].queryset = Company.objects.filter(
                organization=organization,
                is_deleted=False
            ).order_by('name')
            self.fields['note_type'].queryset = NoteType.objects.filter(
                organization=organization
            )


class NoteCashFlowForm(forms.Form):
    """Form for cash flow assumptions attached to a note."""

    INPUT_CLASS = 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6'

    include_cash_flows = forms.BooleanField(
        required=False,
        label='Include IRR Cash Flows',
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600',
        })
    )

    current_price = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Current Price',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    fcf_year_1 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Year 1 FCF',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    fcf_year_2 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Year 2 FCF',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    fcf_year_3 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Year 3 FCF',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    fcf_year_4 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Year 4 FCF',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    fcf_year_5 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Year 5 FCF',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    terminal_value = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Terminal Value',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    # Revenue forecasts (optional)
    revenue_year_1 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y1 Revenue',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    revenue_year_2 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y2 Revenue',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    revenue_year_3 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y3 Revenue',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    revenue_year_4 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y4 Revenue',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    revenue_year_5 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y5 Revenue',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    # EBIT/EBITDA forecasts (optional)
    ebit_ebitda_year_1 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y1',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    ebit_ebitda_year_2 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y2',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    ebit_ebitda_year_3 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y3',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    ebit_ebitda_year_4 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y4',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    ebit_ebitda_year_5 = forms.DecimalField(
        required=False,
        max_digits=12,
        decimal_places=2,
        label='Y5',
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASS,
            'step': '0.01',
            'placeholder': '0.00',
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        include = cleaned_data.get('include_cash_flows')

        if include:
            required_fields = ['current_price', 'fcf_year_1', 'fcf_year_2',
                             'fcf_year_3', 'fcf_year_4', 'fcf_year_5', 'terminal_value']
            for field in required_fields:
                if not cleaned_data.get(field):
                    self.add_error(field, 'Required when including cash flows.')

        return cleaned_data
