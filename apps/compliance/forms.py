from django import forms
from .models import (
    ComplianceSettings, ComplianceObligation, ComplianceTask,
    ComplianceEvidence, ComplianceDocument,
    Fund, FundPrincipal, InvestorJurisdiction,
)

INPUT_CLASS = 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6'
CHECKBOX_CLASS = 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600'
SELECT_CLASS = INPUT_CLASS
TEXTAREA_CLASS = INPUT_CLASS


class ComplianceSettingsForm(forms.ModelForm):
    class Meta:
        model = ComplianceSettings
        fields = [
            'firm_name', 'registration_type', 'domicile_state',
            'entity_jurisdiction', 'firm_crd_number',
            'fiscal_year_end_month', 'fiscal_year_end_day',
            'primary_compliance_counsel', 'fund_admin_compliance_contact',
            'fund_admin_compliance_rate', 'aml_cft_target_date',
            'upload_max_mb', 'monthly_close_due_day',
        ]
        widgets = {
            'firm_name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'registration_type': forms.Select(attrs={'class': SELECT_CLASS}),
            'domicile_state': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., US-CA'}),
            'entity_jurisdiction': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., US-DE'}),
            'firm_crd_number': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., 319106'}),
            'fiscal_year_end_month': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 12}),
            'fiscal_year_end_day': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 31}),
            'primary_compliance_counsel': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., Cole Frieman'}),
            'fund_admin_compliance_contact': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'fund_admin_compliance_rate': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01', 'placeholder': '500.00'}),
            'aml_cft_target_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
            'upload_max_mb': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 100}),
            'monthly_close_due_day': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 28}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class ComplianceObligationForm(forms.ModelForm):
    class Meta:
        model = ComplianceObligation
        fields = [
            'title', 'description', 'category', 'frequency',
            'jurisdiction', 'default_due_day', 'default_due_month',
            'quarter', 'advance_notice_days', 'due_date_reference',
            'regulatory_reference', 'filing_url',
            'tags', 'owner_role', 'suggested_evidence',
            'is_active', 'is_placeholder',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Obligation title'}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'category': forms.Select(attrs={'class': SELECT_CLASS}),
            'frequency': forms.Select(attrs={'class': SELECT_CLASS}),
            'jurisdiction': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., US-NY, SEC'}),
            'default_due_day': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 31}),
            'default_due_month': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 12}),
            'quarter': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 1, 'max': 4}),
            'advance_notice_days': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
            'due_date_reference': forms.Select(attrs={'class': SELECT_CLASS}),
            'regulatory_reference': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2}),
            'filing_url': forms.URLInput(attrs={'class': INPUT_CLASS, 'placeholder': 'https://...'}),
            'tags': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'comma-separated tags'}),
            'owner_role': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'suggested_evidence': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'is_placeholder': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


# Backwards compatibility alias
ComplianceTaskTemplateForm = ComplianceObligationForm


class ComplianceTaskForm(forms.ModelForm):
    class Meta:
        model = ComplianceTask
        fields = [
            'title', 'description', 'due_date', 'status', 'notes', 'tags',
            'fund', 'delegated_to', 'delegated_to_name',
            'estimated_cost', 'actual_cost',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'due_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
            'status': forms.Select(attrs={'class': SELECT_CLASS}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 4}),
            'tags': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'fund': forms.Select(attrs={'class': SELECT_CLASS}),
            'delegated_to': forms.Select(attrs={'class': SELECT_CLASS}),
            'delegated_to_name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., Cole Frieman'}),
            'estimated_cost': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01'}),
            'actual_cost': forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01'}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['fund'].queryset = Fund.objects.filter(
                organization=organization, is_active=True
            )


class ComplianceTaskStatusForm(forms.Form):
    """Lightweight form for changing task status via HTMX."""
    status = forms.ChoiceField(choices=ComplianceTask.Status.choices)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 2}))


class EvidenceUploadForm(forms.ModelForm):
    class Meta:
        model = ComplianceEvidence
        fields = ['file', 'external_link', 'text_content', 'description']
        widgets = {
            'file': forms.ClearableFileInput(attrs={'class': INPUT_CLASS}),
            'external_link': forms.URLInput(attrs={'class': INPUT_CLASS, 'placeholder': 'https://...'}),
            'text_content': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2, 'placeholder': 'Simple text evidence...'}),
            'description': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Brief description'}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('file') and not cleaned.get('external_link') and not cleaned.get('text_content'):
            raise forms.ValidationError('Provide either a file, an external link, or text evidence.')
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


class FundForm(forms.ModelForm):
    class Meta:
        model = Fund
        fields = [
            'name', 'entity_type', 'entity_jurisdiction',
            'sec_file_number', 'edgar_cik', 'inception_date', 'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., Top Mark Capital Partners LP'}),
            'entity_type': forms.Select(attrs={'class': SELECT_CLASS}),
            'entity_jurisdiction': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., US-DE'}),
            'sec_file_number': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'edgar_cik': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'inception_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class FundPrincipalForm(forms.ModelForm):
    class Meta:
        model = FundPrincipal
        fields = [
            'name', 'crd_number', 'title', 'residency_jurisdiction',
            'is_us_resident', 'requires_adv_nr',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'crd_number': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., 7510496'}),
            'title': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., Managing Partner'}),
            'residency_jurisdiction': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., US-CA or CA-AB'}),
            'is_us_resident': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'requires_adv_nr': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class InvestorJurisdictionForm(forms.ModelForm):
    class Meta:
        model = InvestorJurisdiction
        fields = [
            'jurisdiction_code', 'jurisdiction_name', 'first_sale_date',
            'blue_sky_filed', 'blue_sky_filing_date', 'notes',
        ]
        widgets = {
            'jurisdiction_code': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., US-NY'}),
            'jurisdiction_name': forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'e.g., New York'}),
            'first_sale_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
            'blue_sky_filed': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
            'blue_sky_filing_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class SurveyCompleteForm(forms.Form):
    """Dynamic form for survey completion based on version questions."""

    attested_name = forms.CharField(
        label="Digital Signature (Type Full Name)",
        widget=forms.TextInput(attrs={'class': INPUT_CLASS, 'placeholder': 'Full Name'})
    )
    attestation_consent = forms.BooleanField(
        label="I certify that the information provided is true and correct.",
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS})
    )

    def __init__(self, *args, **kwargs):
        self.version = kwargs.pop('version', None)
        super().__init__(*args, **kwargs)

        if self.version:
            for question in self.version.questions.all():
                field_key = f'q_{question.pk}'
                field_type = question.field_type
                label = question.prompt
                required = question.is_required
                help_text = question.help_text

                if field_type == 'YES_NO':
                    self.fields[field_key] = forms.TypedChoiceField(
                        label=label,
                        choices=[(True, 'Yes'), (False, 'No')],
                        coerce=lambda x: str(x).lower() == 'true',
                        widget=forms.RadioSelect(attrs={'class': 'flex gap-4'}),
                        required=required,
                        help_text=help_text
                    )
                elif field_type == 'TEXT':
                    self.fields[field_key] = forms.CharField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.TextInput(attrs={'class': INPUT_CLASS})
                    )
                elif field_type == 'LONG_TEXT':
                    self.fields[field_key] = forms.CharField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3})
                    )
                elif field_type == 'DATE':
                    self.fields[field_key] = forms.DateField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'})
                    )
                elif field_type == 'DECIMAL':
                    self.fields[field_key] = forms.DecimalField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.NumberInput(attrs={'class': INPUT_CLASS, 'step': '0.01'})
                    )
                elif field_type == 'FILE':
                    self.fields[field_key] = forms.FileField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.ClearableFileInput(attrs={'class': INPUT_CLASS})
                    )
                elif field_type in ['SINGLE_SELECT', 'MULTI_SELECT']:
                    choices = []
                    if question.response_options:
                        opts = question.response_options
                        if isinstance(opts, list):
                            for o in opts:
                                if isinstance(o, list):
                                    choices.append(tuple(o))
                                else:
                                    choices.append((o, o))

                    if field_type == 'SINGLE_SELECT':
                        self.fields[field_key] = forms.ChoiceField(
                            label=label, choices=choices, required=required, help_text=help_text,
                            widget=forms.Select(attrs={'class': SELECT_CLASS})
                        )
                    else:
                        self.fields[field_key] = forms.MultipleChoiceField(
                            label=label, choices=choices, required=required, help_text=help_text,
                            widget=forms.CheckboxSelectMultiple(attrs={'class': 'space-y-1'})
                        )
                else:
                    self.fields[field_key] = forms.CharField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2, 'placeholder': 'Table data (CSV/List)'})
                    )
