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
                    # Use a radio select for yes/no instead of checkbox for better explicitness
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
                        # Assume list of strings or list of pairs
                        opts = question.response_options
                        if isinstance(opts, list):
                            for o in opts:
                                if isinstance(o, list): choices.append(tuple(o))
                                else: choices.append((o, o))
                    
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
                # Tables would need more complex JS handling, defaulting to text for now
                else:
                    self.fields[field_key] = forms.CharField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2, 'placeholder': 'Table data (CSV/List)'})
                    )


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
                    # Use a radio select for yes/no instead of checkbox for better explicitness
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
                        # Assume list of strings or list of pairs
                        opts = question.response_options
                        if isinstance(opts, list):
                            for o in opts:
                                if isinstance(o, list): choices.append(tuple(o))
                                else: choices.append((o, o))
                    
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
                # Tables would need more complex JS handling, defaulting to text for now
                else:
                    self.fields[field_key] = forms.CharField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2, 'placeholder': 'Table data (CSV/List)'})
                    )


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
                    # Use a radio select for yes/no instead of checkbox for better explicitness
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
                        # Assume list of strings or list of pairs
                        opts = question.response_options
                        if isinstance(opts, list):
                            for o in opts:
                                if isinstance(o, list): choices.append(tuple(o))
                                else: choices.append((o, o))
                    
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
                # Tables would need more complex JS handling, defaulting to text for now
                else:
                    self.fields[field_key] = forms.CharField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2, 'placeholder': 'Table data (CSV/List)'})
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
                    # Use a radio select for yes/no instead of checkbox for better explicitness
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
                        # Assume list of strings or list of pairs
                        opts = question.response_options
                        if isinstance(opts, list):
                            for o in opts:
                                if isinstance(o, list): choices.append(tuple(o))
                                else: choices.append((o, o))
                    
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
                # Tables would need more complex JS handling, defaulting to text for now
                else:
                    self.fields[field_key] = forms.CharField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2, 'placeholder': 'Table data (CSV/List)'})
                    )

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
                    # Use a radio select for yes/no instead of checkbox for better explicitness
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
                        # Assume list of strings or list of pairs
                        opts = question.response_options
                        if isinstance(opts, list):
                            for o in opts:
                                if isinstance(o, list): choices.append(tuple(o))
                                else: choices.append((o, o))
                    
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
                # Tables would need more complex JS handling, defaulting to text for now
                else:
                    self.fields[field_key] = forms.CharField(
                        label=label, required=required, help_text=help_text,
                        widget=forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2, 'placeholder': 'Table data (CSV/List)'})
                    )
