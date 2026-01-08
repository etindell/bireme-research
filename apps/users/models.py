"""
Custom User model for Bireme Research platform.

Uses email as the unique identifier instead of username.
"""
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model using email for authentication.

    This model replaces Django's default User model and uses email
    as the primary identifier instead of username.
    """
    email = models.EmailField(
        'email address',
        unique=True,
        error_messages={
            'unique': 'A user with that email already exists.',
        },
    )
    first_name = models.CharField('first name', max_length=150, blank=True)
    last_name = models.CharField('last name', max_length=150, blank=True)

    is_staff = models.BooleanField(
        'staff status',
        default=False,
        help_text='Designates whether the user can log into the admin site.',
    )
    is_active = models.BooleanField(
        'active',
        default=True,
        help_text='Designates whether this user should be treated as active.',
    )
    date_joined = models.DateTimeField('date joined', default=timezone.now)

    # Profile fields
    avatar_url = models.URLField('avatar URL', blank=True)
    job_title = models.CharField('job title', max_length=100, blank=True)

    objects = UserManager()

    EMAIL_FIELD = 'email'
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # Email is already required by USERNAME_FIELD

    class Meta:
        db_table = 'users'
        verbose_name = 'user'
        verbose_name_plural = 'users'
        ordering = ['email']

    def __str__(self):
        return self.email

    def get_full_name(self):
        """
        Return the first_name plus the last_name, with a space in between.
        """
        full_name = f'{self.first_name} {self.last_name}'.strip()
        return full_name or self.email

    def get_short_name(self):
        """
        Return the short name for the user.
        """
        return self.first_name or self.email.split('@')[0]

    def get_organizations(self):
        """
        Return all organizations the user is a member of.
        """
        from apps.organizations.models import Organization
        return Organization.objects.filter(
            memberships__user=self,
            memberships__is_deleted=False
        )

    def get_default_organization(self):
        """
        Return the user's default organization.
        """
        membership = self.organization_memberships.filter(
            is_default=True,
            is_deleted=False
        ).select_related('organization').first()

        if membership:
            return membership.organization

        # Fallback to first organization
        membership = self.organization_memberships.filter(
            is_deleted=False
        ).select_related('organization').first()

        return membership.organization if membership else None
