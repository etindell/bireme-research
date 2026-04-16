"""
Tests for the Cybozu CT ingestion service.
"""
from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.companies.models import Company
from apps.organizations.models import Organization
from apps.signals.models import (
    CertificateSubdomainObservation,
    SignalSourceConfig,
    SignalSyncRun,
)
from apps.signals.services.cybozu_ct import (
    classify_fqdn,
    normalize_fqdn,
    parse_name_values,
    process_crtsh_entries,
    upsert_observations,
    run_sync,
)


def _disconnect_search_signal():
    """Disconnect Company post_save search vector signal for SQLite compat."""
    from django.db.models.signals import post_save
    from apps.companies.signals import update_search_vector
    post_save.disconnect(update_search_vector, sender=Company)


def _reconnect_search_signal():
    from django.db.models.signals import post_save
    from apps.companies.signals import update_search_vector
    post_save.connect(update_search_vector, sender=Company)


class NormalizeFQDNTests(TestCase):
    def test_basic_normalization(self):
        self.assertEqual(normalize_fqdn('Example.COM'), 'example.com')

    def test_strip_trailing_dot(self):
        self.assertEqual(normalize_fqdn('example.com.'), 'example.com')

    def test_strip_wildcard(self):
        self.assertEqual(normalize_fqdn('*.example.com'), 'example.com')

    def test_strip_whitespace(self):
        self.assertEqual(normalize_fqdn('  example.com  '), 'example.com')

    def test_combined(self):
        self.assertEqual(normalize_fqdn('  *.Example.COM.  '), 'example.com')


class ParseNameValuesTests(TestCase):
    def test_single_value(self):
        result = parse_name_values('foo.kintone.com')
        self.assertEqual(result, ['foo.kintone.com'])

    def test_newline_separated(self):
        result = parse_name_values('foo.kintone.com\nbar.kintone.com\nbaz.cybozu.com')
        self.assertEqual(result, [
            'foo.kintone.com',
            'bar.kintone.com',
            'baz.cybozu.com',
        ])

    def test_with_wildcards_and_whitespace(self):
        result = parse_name_values('*.foo.kintone.com\n  bar.kintone.com  ')
        self.assertEqual(result, [
            'foo.kintone.com',
            'bar.kintone.com',
        ])

    def test_empty_string(self):
        self.assertEqual(parse_name_values(''), [])

    def test_none(self):
        self.assertEqual(parse_name_values(None), [])

    def test_blank_lines(self):
        result = parse_name_values('foo.kintone.com\n\nbar.kintone.com\n')
        self.assertEqual(result, ['foo.kintone.com', 'bar.kintone.com'])


class ClassifyFQDNTests(TestCase):
    def setUp(self):
        self.ignore = ['test', 'staging', 'dev', 'demo', 'sandbox']

    def test_depth_1_candidate(self):
        result = classify_fqdn('acme.kintone.com', 'kintone.com', self.ignore)
        self.assertEqual(result['tenant_label'], 'acme')
        self.assertEqual(result['label_depth'], 1)
        self.assertTrue(result['tenant_candidate'])
        self.assertFalse(result['is_excluded'])

    def test_depth_1_ignored(self):
        result = classify_fqdn('test.kintone.com', 'kintone.com', self.ignore)
        self.assertEqual(result['label_depth'], 1)
        self.assertFalse(result['tenant_candidate'])
        self.assertTrue(result['is_excluded'])
        self.assertIn('test', result['exclude_reason'])

    def test_depth_1_partial_keyword_match(self):
        result = classify_fqdn('testcompany.kintone.com', 'kintone.com', self.ignore)
        self.assertTrue(result['is_excluded'])
        self.assertFalse(result['tenant_candidate'])

    def test_depth_2_not_candidate(self):
        result = classify_fqdn('sub.acme.kintone.com', 'kintone.com', self.ignore)
        self.assertEqual(result['label_depth'], 2)
        self.assertFalse(result['tenant_candidate'])
        self.assertFalse(result['is_excluded'])

    def test_base_domain_only(self):
        result = classify_fqdn('kintone.com', 'kintone.com', self.ignore)
        self.assertIsNone(result)

    def test_wrong_base_domain(self):
        result = classify_fqdn('foo.example.com', 'kintone.com', self.ignore)
        self.assertIsNone(result)

    def test_depth_0(self):
        """FQDN equals the base domain after removing prefix should give depth 0."""
        result = classify_fqdn('kintone.com', 'kintone.com', self.ignore)
        self.assertIsNone(result)

    def test_staging_keyword(self):
        result = classify_fqdn('staging.kintone.com', 'kintone.com', self.ignore)
        self.assertTrue(result['is_excluded'])

    def test_demo_keyword(self):
        result = classify_fqdn('demo.kintone.com', 'kintone.com', self.ignore)
        self.assertTrue(result['is_excluded'])


class ProcessCrtshEntriesTests(TestCase):
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

    def test_basic_entry_processing(self):
        entries = [
            {
                'id': 123,
                'name_value': 'acme.kintone.com\nfoo.kintone.com',
                'entry_timestamp': '2024-01-15T10:00:00',
                'not_before': '2024-01-15T00:00:00',
                'not_after': '2025-01-15T00:00:00',
                'issuer_name': 'R3',
            }
        ]
        obs = process_crtsh_entries(entries, 'kintone.com', self.config)
        self.assertIn('acme.kintone.com', obs)
        self.assertIn('foo.kintone.com', obs)
        self.assertTrue(obs['acme.kintone.com']['tenant_candidate'])
        self.assertEqual(obs['acme.kintone.com']['observation_count'], 1)

    def test_newline_san_values(self):
        entries = [
            {
                'id': 456,
                'name_value': 'a.kintone.com\nb.kintone.com\nc.kintone.com',
                'entry_timestamp': '2024-06-01T00:00:00',
            }
        ]
        obs = process_crtsh_entries(entries, 'kintone.com', self.config)
        self.assertEqual(len(obs), 3)

    def test_deduplication_within_entries(self):
        entries = [
            {
                'id': 1,
                'name_value': 'acme.kintone.com',
                'entry_timestamp': '2024-01-01T00:00:00',
            },
            {
                'id': 2,
                'name_value': 'acme.kintone.com',
                'entry_timestamp': '2024-06-01T00:00:00',
            },
        ]
        obs = process_crtsh_entries(entries, 'kintone.com', self.config)
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs['acme.kintone.com']['observation_count'], 2)

    def test_filters_non_matching_domain(self):
        entries = [
            {
                'id': 1,
                'name_value': 'acme.example.com',
                'entry_timestamp': '2024-01-01T00:00:00',
            }
        ]
        obs = process_crtsh_entries(entries, 'kintone.com', self.config)
        self.assertEqual(len(obs), 0)


class UpsertObservationsTests(TestCase):
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

    def test_create_new_observation(self):
        observations = {
            'acme.kintone.com': {
                'fqdn': 'acme.kintone.com',
                'base_domain': 'kintone.com',
                'tenant_label': 'acme',
                'label_depth': 1,
                'tenant_candidate': True,
                'is_excluded': False,
                'exclude_reason': '',
                'first_seen_at': datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
                'last_seen_at': datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
                'last_cert_logged_at': None,
                'cert_not_before': None,
                'cert_not_after': None,
                'issuer_name': 'R3',
                'observation_count': 1,
                'source_url': '',
                'raw_payload': {},
            }
        }
        created, updated, excluded = upsert_observations(observations, self.config)
        self.assertEqual(created, 1)
        self.assertEqual(updated, 0)

        obs = CertificateSubdomainObservation.objects.get(
            config=self.config, fqdn='acme.kintone.com'
        )
        self.assertEqual(obs.tenant_label, 'acme')
        self.assertTrue(obs.tenant_candidate)

    def test_update_existing_preserves_first_seen(self):
        CertificateSubdomainObservation.objects.create(
            config=self.config,
            company=self.company,
            base_domain='kintone.com',
            fqdn='acme.kintone.com',
            tenant_label='acme',
            label_depth=1,
            tenant_candidate=True,
            first_seen_at=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
            last_seen_at=datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
            observation_count=1,
        )

        observations = {
            'acme.kintone.com': {
                'fqdn': 'acme.kintone.com',
                'base_domain': 'kintone.com',
                'tenant_label': 'acme',
                'label_depth': 1,
                'tenant_candidate': True,
                'is_excluded': False,
                'exclude_reason': '',
                'first_seen_at': datetime(2024, 6, 1, tzinfo=dt_timezone.utc),
                'last_seen_at': datetime(2024, 6, 1, tzinfo=dt_timezone.utc),
                'last_cert_logged_at': None,
                'cert_not_before': None,
                'cert_not_after': None,
                'issuer_name': 'R3',
                'observation_count': 3,
                'source_url': '',
                'raw_payload': {},
            }
        }
        created, updated, excluded = upsert_observations(observations, self.config)
        self.assertEqual(created, 0)
        self.assertEqual(updated, 1)

        obs = CertificateSubdomainObservation.objects.get(
            config=self.config, fqdn='acme.kintone.com'
        )
        # first_seen_at should NOT be overwritten with the later date
        self.assertEqual(
            obs.first_seen_at,
            datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
        )
        # last_seen_at SHOULD be updated
        self.assertEqual(
            obs.last_seen_at,
            datetime(2024, 6, 1, tzinfo=dt_timezone.utc),
        )
        # observation_count should be incremented
        self.assertEqual(obs.observation_count, 4)  # 1 + 3

    def test_update_with_earlier_first_seen(self):
        CertificateSubdomainObservation.objects.create(
            config=self.config,
            company=self.company,
            base_domain='kintone.com',
            fqdn='acme.kintone.com',
            tenant_label='acme',
            label_depth=1,
            tenant_candidate=True,
            first_seen_at=datetime(2024, 6, 1, tzinfo=dt_timezone.utc),
            last_seen_at=datetime(2024, 6, 1, tzinfo=dt_timezone.utc),
            observation_count=1,
        )

        observations = {
            'acme.kintone.com': {
                'fqdn': 'acme.kintone.com',
                'base_domain': 'kintone.com',
                'tenant_label': 'acme',
                'label_depth': 1,
                'tenant_candidate': True,
                'is_excluded': False,
                'exclude_reason': '',
                'first_seen_at': datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
                'last_seen_at': datetime(2024, 3, 1, tzinfo=dt_timezone.utc),
                'last_cert_logged_at': None,
                'cert_not_before': None,
                'cert_not_after': None,
                'issuer_name': '',
                'observation_count': 2,
                'source_url': '',
                'raw_payload': {},
            }
        }
        created, updated, excluded = upsert_observations(observations, self.config)

        obs = CertificateSubdomainObservation.objects.get(
            config=self.config, fqdn='acme.kintone.com'
        )
        # first_seen_at should be pushed back to the earlier date
        self.assertEqual(
            obs.first_seen_at,
            datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
        )


class RunSyncTests(TestCase):
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

    @patch('apps.signals.services.cybozu_ct.fetch_crtsh_json')
    def test_run_sync_creates_observations(self, mock_fetch):
        mock_fetch.return_value = [
            {
                'id': 100,
                'name_value': 'customer1.kintone.com',
                'entry_timestamp': '2024-01-15T10:00:00',
                'not_before': '2024-01-15T00:00:00',
                'not_after': '2025-01-15T00:00:00',
                'issuer_name': 'R3',
            },
        ]

        sync_run = run_sync(self.config)

        self.assertEqual(sync_run.status, 'success')
        self.assertEqual(sync_run.created_count, 1)
        self.assertTrue(
            CertificateSubdomainObservation.objects.filter(
                fqdn='customer1.kintone.com'
            ).exists()
        )

    @patch('apps.signals.services.cybozu_ct.fetch_crtsh_json')
    def test_run_sync_handles_empty_response(self, mock_fetch):
        mock_fetch.return_value = []
        sync_run = run_sync(self.config)
        self.assertEqual(sync_run.status, 'success')
        self.assertEqual(sync_run.created_count, 0)

    def test_run_sync_fails_with_no_base_domains(self):
        self.config.settings_json = {}
        self.config.save()
        sync_run = run_sync(self.config)
        self.assertEqual(sync_run.status, 'failed')
        self.assertIn('No base_domains', sync_run.error_text)
