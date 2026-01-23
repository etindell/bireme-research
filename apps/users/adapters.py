"""
Custom adapters for django-allauth social authentication.
"""
from django.conf import settings
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.shortcuts import redirect
from django.contrib import messages


class BiremeSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to restrict social login to @biremecapital.com emails.
    """

    ALLOWED_DOMAINS = ['biremecapital.com']

    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a
        social provider, but before the login is actually processed.

        We use this to check the email domain.
        """
        # Get the email from the social account
        email = sociallogin.account.extra_data.get('email', '')

        if email:
            domain = email.split('@')[-1].lower()
            if domain not in self.ALLOWED_DOMAINS:
                messages.error(
                    request,
                    f'Only @biremecapital.com email addresses are allowed. '
                    f'You signed in with {email}.'
                )
                raise ImmediateHttpResponse(redirect('account_login'))

        return super().pre_social_login(request, sociallogin)

    def populate_user(self, request, sociallogin, data):
        """
        Hook that can be used to customize user creation from social account data.
        """
        user = super().populate_user(request, sociallogin, data)

        # Set first and last name from Google profile
        if sociallogin.account.provider == 'google':
            extra_data = sociallogin.account.extra_data
            user.first_name = extra_data.get('given_name', '')
            user.last_name = extra_data.get('family_name', '')

        return user
