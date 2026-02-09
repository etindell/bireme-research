"""
Context processors for organization data.

These make organization-related data available in all templates.
"""
from .models import OrganizationMembership


def organization(request):
    """
    Add organization and membership data to template context.

    Provides:
    - current_organization: The currently active organization
    - current_membership: User's membership in current organization
    - user_organizations: All organizations the user belongs to
    - pending_todo_count: Count of pending todos for sidebar badge
    """
    context = {
        'current_organization': getattr(request, 'organization', None),
        'current_membership': getattr(request, 'membership', None),
        'user_organizations': [],
        'pending_todo_count': 0,
        'unread_news_count': 0,
        'todays_pomodoro_count': 0,
    }

    if request.user.is_authenticated:
        context['user_organizations'] = OrganizationMembership.objects.filter(
            user=request.user,
            is_deleted=False,
            organization__is_deleted=False
        ).select_related('organization').order_by('-is_default', 'organization__name')

        # Add pending todo count for sidebar badge
        if hasattr(request, 'organization') and request.organization:
            from apps.todos.models import Todo
            context['pending_todo_count'] = Todo.objects.filter(
                organization=request.organization,
                is_completed=False
            ).count()

            # Add unread news count for sidebar badge
            from apps.news.models import CompanyNews
            context['unread_news_count'] = CompanyNews.objects.filter(
                organization=request.organization,
                is_read=False
            ).count()

            # Add today's pomodoro count for sidebar badge
            from apps.pomodoros.models import Pomodoro
            context['todays_pomodoro_count'] = Pomodoro.objects.filter(
                organization=request.organization,
                user=request.user,
                is_completed=True,
            ).today().count()

    return context
