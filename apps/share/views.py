"""
Public views for shared notes.
These views do not require authentication.
"""
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, CreateView

from apps.notes.models import NoteShareLink, NoteShareComment
from .forms import ShareCommentForm


def get_client_ip(request):
    """Extract client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


class SharedNoteView(DetailView):
    """
    Public view for a shared note.
    No authentication required.
    """
    model = NoteShareLink
    template_name = 'share/note.html'
    context_object_name = 'share_link'
    slug_field = 'token'
    slug_url_kwarg = 'token'

    def get_queryset(self):
        return NoteShareLink.objects.select_related(
            'note', 'note__note_type', 'note__company'
        ).prefetch_related(
            'note__referenced_companies',
            'comments'
        )

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)

        # Check if share link is valid
        if not obj.is_active:
            raise Http404("This share link is no longer active.")

        if obj.is_expired:
            raise Http404("This share link has expired.")

        # Check if note is soft-deleted
        if obj.note.is_deleted:
            raise Http404("This note is no longer available.")

        return obj

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        # Record the view
        self.object.record_view()
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['note'] = self.object.note
        context['comment_form'] = ShareCommentForm()
        context['comments'] = self.object.comments.filter(
            is_approved=True,
            is_hidden=False
        )
        return context


class SharedNoteCommentView(CreateView):
    """
    Handle comment submission on shared notes.
    No authentication required.
    """
    model = NoteShareComment
    form_class = ShareCommentForm
    http_method_names = ['post']

    def get_share_link(self):
        """Get and validate the share link."""
        share_link = get_object_or_404(
            NoteShareLink,
            token=self.kwargs['token']
        )

        if not share_link.is_valid:
            raise Http404("This share link is no longer valid.")

        if not share_link.allow_comments:
            raise Http404("Comments are not enabled for this share link.")

        return share_link

    def form_valid(self, form):
        share_link = self.get_share_link()
        form.instance.share_link = share_link
        form.instance.ip_address = get_client_ip(self.request)
        return super().form_valid(form)

    def get_success_url(self):
        return self.object.share_link.get_absolute_url() + '#comments'

    def form_invalid(self, form):
        # Redirect back to the shared note with error
        share_link = self.get_share_link()
        return redirect(share_link.get_absolute_url() + '#comments')
