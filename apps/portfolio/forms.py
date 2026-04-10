from django import forms

from .models import PortfolioSnapshot

INPUT_CLASS = 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6'
FILE_CLASS = 'block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100'


class PortfolioSnapshotForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        kwargs.pop('organization', None)
        super().__init__(*args, **kwargs)

    class Meta:
        model = PortfolioSnapshot
        fields = ['name', 'as_of_date', 'source_file', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': 'e.g., Q1 2026 Long Book',
            }),
            'as_of_date': forms.DateInput(attrs={
                'class': INPUT_CLASS,
                'type': 'date',
            }),
            'source_file': forms.FileInput(attrs={
                'class': FILE_CLASS,
                'accept': '.pdf,.png,.jpg,.jpeg',
            }),
            'notes': forms.Textarea(attrs={
                'class': INPUT_CLASS,
                'rows': 3,
                'placeholder': 'Optional notes about this snapshot...',
            }),
        }
