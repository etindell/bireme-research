"""
Google Tasks API client for syncing tasks to Bireme Research.

Uses allauth's SocialToken to authenticate. Requires:
- Google OAuth with 'tasks.readonly' scope
- access_type='offline' for refresh tokens
"""
import logging
from datetime import datetime

import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from allauth.socialaccount.models import SocialToken

logger = logging.getLogger(__name__)

KEYWORD_PREFIX = 'br:'


def get_google_credentials(user):
    """
    Build google.oauth2.credentials.Credentials from allauth's stored tokens.
    Returns None if no valid token exists.
    """
    try:
        social_token = SocialToken.objects.select_related('app').get(
            account__user=user,
            account__provider='google',
        )
    except SocialToken.DoesNotExist:
        logger.warning(f"No Google social token for user {user.email}")
        return None

    app = social_token.app

    creds = Credentials(
        token=social_token.token,
        refresh_token=social_token.token_secret,
        token_uri='https://oauth2.googleapis.com/token',
        client_id=app.client_id,
        client_secret=app.secret,
    )

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(google.auth.transport.requests.Request())
            social_token.token = creds.token
            social_token.save(update_fields=['token'])
        except Exception as e:
            logger.error(f"Failed to refresh Google token for {user.email}: {e}")
            return None

    return creds


def fetch_tasks_from_google(creds, updated_min=None):
    """
    Fetch all tasks from all task lists via the Google Tasks API.

    Args:
        creds: google.oauth2.credentials.Credentials
        updated_min: Optional RFC3339 datetime string. Only return tasks
                     updated after this time.

    Returns:
        List of task dicts from the API.
    """
    service = build('tasks', 'v1', credentials=creds)

    all_tasks = []

    # Get all task lists
    tasklists_result = service.tasklists().list().execute()
    tasklists = tasklists_result.get('items', [])

    for tasklist in tasklists:
        params = {
            'tasklist': tasklist['id'],
            'showCompleted': False,
            'showHidden': False,
        }
        if updated_min:
            params['updatedMin'] = updated_min

        # Paginate through tasks
        page_token = None
        while True:
            if page_token:
                params['pageToken'] = page_token

            result = service.tasks().list(**params).execute()
            tasks = result.get('items', [])

            for task in tasks:
                task['_tasklist_id'] = tasklist['id']
                task['_tasklist_title'] = tasklist.get('title', '')

            all_tasks.extend(tasks)

            page_token = result.get('nextPageToken')
            if not page_token:
                break

    return all_tasks


def filter_bireme_tasks(tasks):
    """
    Filter tasks to only those starting with the keyword prefix (br:).
    Strips the prefix from the title for the Todo.

    Returns list of dicts with cleaned data:
        {
            'google_task_id': str,
            'title': str (prefix stripped),
            'notes': str,
            'due': datetime or None,
        }
    """
    results = []
    for task in tasks:
        title = (task.get('title') or '').strip()
        if not title.lower().startswith(KEYWORD_PREFIX):
            continue

        clean_title = title[len(KEYWORD_PREFIX):].strip()
        if not clean_title:
            continue

        # Parse due date if present (RFC3339)
        due = None
        if task.get('due'):
            try:
                due = datetime.fromisoformat(task['due'].replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                pass

        results.append({
            'google_task_id': task['id'],
            'title': clean_title,
            'notes': task.get('notes', ''),
            'due': due,
        })

    return results
