from django import forms
from .models import (
    ComplianceSettings, ComplianceTaskTemplate, ComplianceTask,
    ComplianceEvidence, ComplianceDocument
)

INPUT_CLASS = 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6'
CHECKBOX_CLASS = 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600'
SELECT_CLASS = INPUT_CLASS
TEXTAREA_CLASS = INPUT_CLASS


class ComplianceSettingsForm(forms.ModelForm):
    class Meta:
        model = ComplianceSettings
        fields = [
            'firm_name', 'fiscal_year_end_month', 'fiscal_year_end_day',
            'is_form_13f_applicable', 'is_form_crs_applicable',
            'is_privacy_notice_annual_required', 'is_form_pf_applicable',
            'has_material_brochure_changes', 'require_evidence_for_completion',
            'upload_max_mb', 'monthly_close_due_day',
        ]
        widgets = {
            'firm_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'fiscal_year_end_month': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 12}),
            'fiscal_year_end_day': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 31}),
            'is_form_13f_applicable': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'is_form_crs_applicable': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'is_privacy_notice_annual_required': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'is_form_pf_applicable': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'has_material_brochure_changes': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'require_evidence_for_completion': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'upload_max_mb': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 100}),
            'monthly_close_due_day': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 28}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class ComplianceTaskTemplateForm(forms.ModelForm):
    class Meta:
        model = ComplianceTaskTemplate
        fields = [
            'title', 'description', 'frequency', 'default_due_day',
            'default_due_month', 'quarter', 'tags', 'conditional_flag',
            'owner_role', 'suggested_evidence', 'is_active',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Task template title'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'frequency': forms.Select(attrs={'class': SELECT_CLASS}),
            'default_due_day': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 31}),
            'default_due_month': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 12}),
            'quarter': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 4}),
            'tags': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'comma-separated tags'}),
            'conditional_flag': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'owner_role': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'suggested_evidence': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class ComplianceTaskForm(forms.ModelForm):
    class Meta:
        model = ComplianceTask
        fields = ['title', 'description', 'due_date', 'status', 'notes', 'tags']
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'due_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
            'status': forms.Select(attrs={'class': SELECT_CLASS}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 4}),
            'tags': forms.TextInput(attrs={'class': INPUT_CLASS}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class ComplianceTaskStatusForm(forms.Form):
    """Lightweight form for changing task status via HTMX."""
    status = forms.ChoiceField(choices=ComplianceTask.Status.choices)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))


class EvidenceUploadForm(forms.ModelForm):
    class Meta:
        model = ComplianceEvidence
        fields = ['file', 'external_link', 'description']
        widgets = {
            'file': forms.ClearableFileInput(attrs={'class': INPUT_CLASS}),
            'external_link': forms.URLInput(attrs={'class': INPUT_CLASS, 'placeholder': 'https://...'}),
            'description': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Brief description'}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('file') and not cleaned.get('external_link'):
            raise forms.ValidationError('Provide either a file or an external link.')
        return cleaned


class ComplianceDocumentForm(forms.ModelForm):
    class Meta:
        model = ComplianceDocument
        fields = ['name', 'description', 'category', 'file']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2}),
            'category': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g. Policies, Filings'}),
            'file': forms.ClearableFileInput(attrs={'class': INPUT_CLASS}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
