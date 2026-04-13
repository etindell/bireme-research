from django import forms
from apps.users.models import User
from .models import (
    ComplianceSettings, ComplianceTaskTemplate, ComplianceTask,
    ComplianceEvidence, ComplianceDocument, SurveyTemplate, SurveyVersion,
    SurveyQuestion, SurveyException,
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
            'owner_role', 'suggested_evidence', 'is_active', 'survey_template',
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
            'survey_template': forms.Select(attrs={'class': SELECT_CLASS}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            from .models import SurveyTemplate
            self.fields['survey_template'].queryset = SurveyTemplate.objects.filter(
                organization=organization, is_active=True,
            )


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


class SurveySendForm(forms.Form):
    YEAR_CHOICES = [(y, str(y)) for y in range(2024, 2030)]
    QUARTER_CHOICES = [('', '—'), (1, 'Q1'), (2, 'Q2'), (3, 'Q3'), (4, 'Q4')]

    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'space-y-2'}),
        required=False,
        label="Select Employees",
    )
    send_to_audience = forms.BooleanField(
        required=False,
        label="Send to all in audience group instead",
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
    )
    year = forms.TypedChoiceField(
        choices=YEAR_CHOICES, coerce=int,
        widget=forms.Select(attrs={'class': SELECT_CLASS}),
        label="Year",
    )
    quarter = forms.TypedChoiceField(
        choices=QUARTER_CHOICES, coerce=lambda x: int(x) if x else None,
        required=False,
        widget=forms.Select(attrs={'class': SELECT_CLASS}),
        label="Quarter",
    )
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
        label="Due Date",
    )
    send_email = forms.BooleanField(
        required=False, initial=True,
        label="Send email notification",
        widget=forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
    )

    def __init__(self, *args, organization=None, cadence=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['users'].queryset = User.objects.filter(
                organization_memberships__organization=organization,
                organization_memberships__is_deleted=False,
            ).distinct().order_by('email')


class SurveyTemplateForm(forms.ModelForm):
    class Meta:
        model = SurveyTemplate
        fields = ['name', 'description', 'cadence', 'audience_type', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'description': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'cadence': forms.Select(attrs={'class': SELECT_CLASS}),
            'audience_type': forms.Select(attrs={'class': SELECT_CLASS}),
            'is_active': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class SurveyVersionForm(forms.ModelForm):
    class Meta:
        model = SurveyVersion
        fields = ['instructions', 'attestation_text', 'effective_date']
        widgets = {
            'instructions': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'attestation_text': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'effective_date': forms.DateInput(attrs={'class': INPUT_CLASS, 'type': 'date'}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


class SurveyQuestionForm(forms.ModelForm):
    class Meta:
        model = SurveyQuestion
        fields = ['sort_order', 'question_key', 'prompt', 'help_text', 'field_type', 'is_required']
        widgets = {
            'sort_order': forms.NumberInput(attrs={'class': INPUT_CLASS, 'min': 0}),
            'question_key': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'prompt': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 2}),
            'help_text': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'field_type': forms.Select(attrs={'class': SELECT_CLASS}),
            'is_required': forms.CheckboxInput(attrs={'class': CHECKBOX_CLASS}),
        }


class SurveyExceptionForm(forms.ModelForm):
    class Meta:
        model = SurveyException
        fields = ['status', 'severity', 'category', 'summary', 'details', 'resolution_notes']
        widgets = {
            'status': forms.Select(attrs={'class': SELECT_CLASS}),
            'severity': forms.Select(attrs={'class': SELECT_CLASS}),
            'category': forms.Select(attrs={'class': SELECT_CLASS}),
            'summary': forms.TextInput(attrs={'class': INPUT_CLASS}),
            'details': forms.Textarea(attrs={'class': TEXTAREA_CLASS, 'rows': 3}),
            'resolution_notes': forms.Textarea(attrs={
                'class': TEXTAREA_CLASS, 'rows': 4,
                'placeholder': 'Describe how this exception was resolved...',
            }),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)


SurveyQuestionFormSet = forms.inlineformset_factory(
    SurveyVersion, SurveyQuestion,
    form=SurveyQuestionForm,
    extra=1,
    can_delete=True,
)


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
