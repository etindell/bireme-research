"""
Data migration to set up Google OAuth SocialApplication from environment variables.
"""
import os
from django.db import migrations


def setup_google_oauth(apps, schema_editor):
    """
    Create or update the Google SocialApplication using environment variables.
    """
    SocialApp = apps.get_model('socialaccount', 'SocialApp')
    Site = apps.get_model('sites', 'Site')

    client_id = os.environ.get('GOOGLE_CLIENT_ID', '')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET', '')

    if not client_id or not client_secret:
        print("GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not set - skipping Google OAuth setup")
        return

    # Get or create the Google social app
    social_app, created = SocialApp.objects.get_or_create(
        provider='google',
        defaults={
            'name': 'Google',
            'client_id': client_id,
            'secret': client_secret,
        }
    )

    if not created:
        # Update existing app with new credentials
        social_app.client_id = client_id
        social_app.secret = client_secret
        social_app.save()
        print("Updated existing Google OAuth application")
    else:
        print("Created new Google OAuth application")

    # Get site domain from environment or use default
    site_domain = os.environ.get('SITE_DOMAIN', 'localhost')

    # Associate with the default site
    site, site_created = Site.objects.get_or_create(
        id=1,
        defaults={'domain': site_domain, 'name': 'Bireme Research'}
    )

    # Update site domain if it changed
    if site.domain != site_domain:
        site.domain = site_domain
        site.save()
        print(f"Updated site domain to: {site_domain}")

    # Add site to social app if not already added
    if not social_app.sites.filter(id=site.id).exists():
        social_app.sites.add(site)
        print(f"Associated Google OAuth with site: {site.domain}")


def reverse_google_oauth(apps, schema_editor):
    """
    Remove the Google SocialApplication.
    """
    SocialApp = apps.get_model('socialaccount', 'SocialApp')
    SocialApp.objects.filter(provider='google').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),
        ('socialaccount', '0001_initial'),
        ('sites', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(setup_google_oauth, reverse_google_oauth),
    ]
