"""
Tests for Signals app views.
"""
from datetime import datetime, timezone as dt_timezone

from django.test import TestCase, Client
from django.urls import reverse

from apps.companies.models import Company
from apps.organizations.models import Organization, OrganizationMembership
from apps.signals.models import (
    CertificateSubdomainObservation,
    SignalSourceConfig,
)
from apps.users.models import User


def _disconnect_search_signal():
    from django.db.models.signals import post_save
    from apps.companies.signals import update_search_vector
    post_save.disconnect(update_search_vector, sender=Company)


def _reconnect_search_signal():
    from django.db.models.signals import post_save
    from apps.companies.signals import update_search_vector
    post_save.connect(update_search_vector, sender=Company)


class SignalViewTestBase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _disconnect_search_signal()

    @classmethod
    def tearDownClass(cls):
        _reconnect_search_signal()
        super().tearDownClass()

    def setUp(self):
        self.org = Organization.objects.create(name='Test Org', slug='test-org')
        self.user = User.objects.create_user(email='test@test.com', password='testpass123')
        OrganizationMembership.objects.create(
            user=self.user, organization=self.org, role='admin',
        )
        self.company = Company.objects.create(
            name='Cybozu', slug='cybozu', organization=self.org,
        )
        defaults = SignalSourceConfig.get_cybozu_defaults()
        self.config = SignalSourceConfig.objects.create(
            organization=self.org,
            company=self.company,
            source=SignalSourceConfig.Source.CYBOZU_CT_SUBDOMAINS,
            name='Cybozu CT',
            **defaults,
        )
        self.client = Client()
        self.client.login(email='test@test.com', password='testpass123')
        # Set session org
        session = self.client.session
        session['organization_id'] = self.org.pk
        session.save()


class SignalIndexViewTests(SignalViewTestBase):
    def test_index_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse('signals:index'))
        self.assertEqual(resp.status_code, 302)

    def test_index_renders(self):
        resp = self.client.get(reverse('signals:index'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Signals')
        self.assertContains(resp, 'Cybozu')


class CompanySignalDetailViewTests(SignalViewTestBase):
    def test_detail_renders(self):
        resp = self.client.get(
            reverse('signals:company_detail', kwargs={'company_slug': 'cybozu'})
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'CT Subdomain Activity')
        self.assertContains(resp, 'proxy signal')

    def test_detail_requires_login(self):
        self.client.logout()
        resp = self.client.get(
            reverse('signals:company_detail', kwargs={'company_slug': 'cybozu'})
        )
        self.assertEqual(resp.status_code, 302)


class OrgScopingTests(SignalViewTestBase):
    def test_cannot_see_other_org_config(self):
        other_org = Organization.objects.create(name='Other Org', slug='other-org')
        other_company = Company.objects.create(
            name='Other Co', slug='other-co', organization=other_org,
        )
        SignalSourceConfig.objects.create(
            organization=other_org,
            company=other_company,
            source=SignalSourceConfig.Source.CYBOZU_CT_SUBDOMAINS,
            name='Other CT',
        )

        resp = self.client.get(
            reverse('signals:company_detail', kwargs={'company_slug': 'other-co'})
        )
        self.assertEqual(resp.status_code, 404)


class ExcludeIncludeTests(SignalViewTestBase):
    def setUp(self):
        super().setUp()
        self.obs = CertificateSubdomainObservation.objects.create(
            config=self.config,
            company=self.company,
            base_domain='kintone.com',
            fqdn='acme.kintone.com',
            tenant_label='acme',
            label_depth=1,
            tenant_candidate=True,
            is_excluded=False,
            first_seen_at=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
            last_seen_at=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
        )

    def test_exclude_observation(self):
        resp = self.client.post(
            reverse('signals:exclude', kwargs={'pk': self.obs.pk})
        )
        self.assertEqual(resp.status_code, 302)
        self.obs.refresh_from_db()
        self.assertTrue(self.obs.is_excluded)

    def test_include_observation(self):
        self.obs.is_excluded = True
        self.obs.exclude_reason = 'test'
        self.obs.save()

        resp = self.client.post(
            reverse('signals:include', kwargs={'pk': self.obs.pk})
        )
        self.assertEqual(resp.status_code, 302)
        self.obs.refresh_from_db()
        self.assertFalse(self.obs.is_excluded)
        self.assertEqual(self.obs.exclude_reason, '')

    def test_cannot_exclude_other_org_observation(self):
        other_org = Organization.objects.create(name='Other', slug='other')
        other_company = Company.objects.create(
            name='Other', slug='other', organization=other_org,
        )
        other_config = SignalSourceConfig.objects.create(
            organization=other_org,
            company=other_company,
            source=SignalSourceConfig.Source.CYBOZU_CT_SUBDOMAINS,
            name='Other CT',
        )
        other_obs = CertificateSubdomainObservation.objects.create(
            config=other_config,
            company=other_company,
            base_domain='kintone.com',
            fqdn='secret.kintone.com',
            tenant_label='secret',
            label_depth=1,
            tenant_candidate=True,
            first_seen_at=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
            last_seen_at=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
        )

        resp = self.client.post(
            reverse('signals:exclude', kwargs={'pk': other_obs.pk})
        )
        self.assertEqual(resp.status_code, 404)
