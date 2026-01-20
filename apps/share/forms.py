"""
Forms for the share app.
"""
from django import forms

from apps.notes.models import NoteShareComment


class ShareCommentForm(forms.ModelForm):
    """Form for visitors to leave comments on shared notes."""

    class Meta:
        model = NoteShareComment
        fields = ['author_name', 'author_email', 'content']
        widgets = {
            'author_name': forms.TextInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'Your name (optional)',
            }),
            'author_email': forms.EmailInput(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'Your email (optional)',
            }),
            'content': forms.Textarea(attrs={
                'class': 'block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm',
                'placeholder': 'Leave a comment...',
                'rows': 3,
            }),
        }

    def clean_content(self):
        content = self.cleaned_data.get('content', '').strip()
        if not content:
            raise forms.ValidationError('Comment content is required.')
        if len(content) > 2000:
            raise forms.ValidationError('Comment must be 2000 characters or less.')
        return content
