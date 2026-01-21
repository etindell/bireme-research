"""
Forms for Todo management.
"""
from django import forms
from django.forms import inlineformset_factory

from .models import Todo, TodoCategory, WatchlistQuickAdd
from apps.companies.models import Company
from apps.notes.models import Note, NoteType


class QuarterlySettingsForm(forms.Form):
    """Form for managing automated quarterly todo generation settings."""

    enabled = forms.BooleanField(
        required=False,
        label='Enable quarterly todos',
        help_text='Automatically generate todos for company updates each quarter',
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600',
        })
    )

    days_after_quarter = forms.IntegerField(
        required=True,
        label='Days after quarter end',
        help_text='Number of days after quarter ends before generating todos',
        min_value=0,
        max_value=90,
        widget=forms.NumberInput(attrs={
            'class': 'block w-20 rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
        })
    )

    portfolio_enabled = forms.BooleanField(
        required=False,
        label='Portfolio companies',
        help_text='Generate quarterly update todos for Portfolio companies',
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600',
        })
    )

    on_deck_enabled = forms.BooleanField(
        required=False,
        label='On Deck companies',
        help_text='Generate quarterly update todos for On Deck companies',
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600',
        })
    )

    investor_letter_enabled = forms.BooleanField(
        required=False,
        label='Investor letter review',
        help_text='Generate a quarterly investor letter review todo',
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600',
        })
    )

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            settings = organization.get_quarterly_settings()
            statuses = settings.get('statuses', ['portfolio', 'on_deck'])
            self.initial['enabled'] = settings.get('enabled', True)
            self.initial['days_after_quarter'] = settings.get('days_after_quarter', 21)
            self.initial['portfolio_enabled'] = 'portfolio' in statuses
            self.initial['on_deck_enabled'] = 'on_deck' in statuses
            self.initial['investor_letter_enabled'] = settings.get('investor_letter_enabled', True)


class TodoForm(forms.ModelForm):
    """Full form for creating and editing todos."""

    class Meta:
        model = Todo
        fields = ['title', 'description', 'company', 'category', 'priority', 'scope']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'What needs to be done?',
            }),
            'description': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'rows': 3,
                'placeholder': 'Additional details (optional)...',
            }),
            'company': forms.Select(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            }),
            'category': forms.Select(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            }),
            'priority': forms.Select(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            }),
            'scope': forms.RadioSelect(attrs={
                'class': 'h-4 w-4 border-gray-300 text-primary-600 focus:ring-primary-600',
            }),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['company'].queryset = Company.objects.filter(
                organization=organization,
                is_deleted=False
            )
            self.fields['company'].required = False
            self.fields['category'].queryset = TodoCategory.objects.filter(
                organization=organization
            )
            self.fields['category'].required = False
        # Set scope choices with user-friendly labels
        self.fields['scope'].choices = Todo.Scope.choices


class QuickTodoForm(forms.ModelForm):
    """Simplified form for quick todo creation on company page."""

    class Meta:
        model = Todo
        fields = ['title', 'scope']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Add a todo...',
            }),
            'scope': forms.HiddenInput(),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Default to personal scope for quick todos
        self.fields['scope'].initial = Todo.Scope.PERSONAL


class InvestorLetterTodoForm(forms.ModelForm):
    """Form for investor letter todo with embedded notes."""

    class Meta:
        model = Todo
        fields = ['investor_letter_notes', 'is_completed']
        widgets = {
            'investor_letter_notes': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6 font-mono',
                'rows': 15,
                'placeholder': '''Notes about investor letters read this quarter...

Example:
- Buffett's 2024 letter: Key insight about XYZ
- Klarman Q4: Interesting take on ABC industry
- Li Lu's talk: Comments on China investing''',
            }),
            'is_completed': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-600',
            }),
        }


class WatchlistQuickAddForm(forms.ModelForm):
    """Form for a single watchlist quick-add entry."""

    class Meta:
        model = WatchlistQuickAdd
        fields = ['ticker', 'alert_price', 'note']
        widgets = {
            'ticker': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6 uppercase',
                'placeholder': 'AAPL',
            }),
            'alert_price': forms.NumberInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': '150.00',
                'step': '0.01',
            }),
            'note': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Why is this interesting?',
            }),
        }


# Inline formset for watchlist quick-adds (max 10)
WatchlistQuickAddFormSet = inlineformset_factory(
    Todo,
    WatchlistQuickAdd,
    form=WatchlistQuickAddForm,
    extra=5,
    max_num=10,
    can_delete=True,
)


class CompleteWithNoteForm(forms.ModelForm):
    """Form for creating a note to complete a todo."""

    class Meta:
        model = Note
        fields = ['title', 'content', 'note_type', 'note_date']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'placeholder': 'Summary of what was done...',
            }),
            'content': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 placeholder:text-gray-400 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'rows': 6,
                'placeholder': 'Details, findings, notes from completing this task...',
            }),
            'note_type': forms.Select(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
            }),
            'note_date': forms.DateInput(attrs={
                'class': 'block w-full rounded-md border-0 py-1.5 text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 focus:ring-2 focus:ring-inset focus:ring-primary-600 sm:text-sm sm:leading-6',
                'type': 'date',
            }),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization:
            self.fields['note_type'].queryset = NoteType.objects.filter(
                organization=organization
            )
            self.fields['note_type'].required = False
