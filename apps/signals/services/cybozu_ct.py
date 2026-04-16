"""
Certificate Transparency log ingestion for Cybozu/Kintone subdomain tracking.

Fetches CT log data from crt.sh and parses subdomain observations as a proxy
signal for customer acquisition activity. This is NOT a literal customer count.
"""
import logging
import time
from datetime import datetime, timezone as dt_timezone

import requests
from django.utils import timezone

from apps.signals.models import (
    CertificateSubdomainObservation,
    SignalSourceConfig,
    SignalSyncRun,
)

logger = logging.getLogger(__name__)

CRT_SH_URL = 'https://crt.sh/'
USER_AGENT = 'BiremResearch/1.0 (CT subdomain tracker; research use)'
REQUEST_TIMEOUT = 60
MAX_RETRIES = 2
RETRY_DELAY = 5


def normalize_fqdn(name):
    """
    Normalize a domain name from CT log data.
    - lowercase
    - strip whitespace
    - strip trailing dots
    - strip leading *.
    """
    name = name.strip().lower()
    name = name.rstrip('.')
    if name.startswith('*.'):
        name = name[2:]
    return name


def parse_name_values(name_value_str):
    """
    Parse the name_value field from crt.sh JSON.
    This field may contain newline-separated SAN values.
    Returns a list of normalized domain strings.
    """
    if not name_value_str:
        return []
    names = []
    for line in name_value_str.split('\n'):
        line = line.strip()
        if line:
            names.append(normalize_fqdn(line))
    return names


def classify_fqdn(fqdn, base_domain, ignore_keywords):
    """
    Classify an FQDN relative to a base domain.

    Returns:
        dict with keys: tenant_label, label_depth, tenant_candidate,
                       is_excluded, exclude_reason
    """
    if not fqdn.endswith(base_domain):
        return None

    # Exact match = the base domain itself, not a subdomain
    if fqdn == base_domain:
        return None

    prefix = fqdn[:-(len(base_domain) + 1)]  # strip ".base_domain"
    if not prefix:
        return {
            'tenant_label': '',
            'label_depth': 0,
            'tenant_candidate': False,
            'is_excluded': False,
            'exclude_reason': '',
        }

    labels = prefix.split('.')
    label_depth = len(labels)
    tenant_label = labels[0] if labels else ''

    is_excluded = False
    exclude_reason = ''
    tenant_candidate = False

    if label_depth == 1:
        # Check against ignore keywords
        label_lower = tenant_label.lower()
        for keyword in ignore_keywords:
            if keyword.lower() in label_lower:
                is_excluded = True
                exclude_reason = f'matches ignore keyword: {keyword}'
                break
        if not is_excluded:
            tenant_candidate = True

    return {
        'tenant_label': tenant_label,
        'label_depth': label_depth,
        'tenant_candidate': tenant_candidate,
        'is_excluded': is_excluded,
        'exclude_reason': exclude_reason,
    }


def fetch_crtsh_json(base_domain, session=None):
    """
    Fetch CT log entries from crt.sh for a wildcard query on base_domain.

    Returns list of raw JSON entries, or empty list on failure.
    """
    if session is None:
        session = requests.Session()

    url = CRT_SH_URL
    params = {
        'q': f'%.{base_domain}',
        'output': 'json',
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(
                url,
                params=params,
                timeout=REQUEST_TIMEOUT,
                headers={'User-Agent': USER_AGENT},
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.warning(
                'crt.sh request failed for %s (attempt %d/%d): %s',
                base_domain, attempt + 1, MAX_RETRIES + 1, e,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (attempt + 1))
        except ValueError as e:
            logger.error('Failed to parse crt.sh JSON for %s: %s', base_domain, e)
            return []

    return []


def _parse_crtsh_datetime(dt_str):
    """Parse a crt.sh datetime string to a timezone-aware datetime."""
    if not dt_str:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%d'):
        try:
            dt = datetime.strptime(dt_str, fmt)
            return dt.replace(tzinfo=dt_timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def process_crtsh_entries(entries, base_domain, config):
    """
    Process raw crt.sh JSON entries into parsed observation dicts.

    Returns a dict keyed by normalized fqdn with observation metadata.
    """
    ignore_keywords = config.ignore_keywords or []
    observations = {}

    for entry in entries:
        name_value = entry.get('name_value', '') or ''
        names = parse_name_values(name_value)

        entry_logged_at = _parse_crtsh_datetime(
            entry.get('entry_timestamp')
        )
        not_before = _parse_crtsh_datetime(entry.get('not_before'))
        not_after = _parse_crtsh_datetime(entry.get('not_after'))
        issuer = entry.get('issuer_name', '') or ''
        cert_id = entry.get('id')

        for name in names:
            if not name.endswith(base_domain):
                continue
            if name == base_domain:
                continue

            classification = classify_fqdn(name, base_domain, ignore_keywords)
            if classification is None:
                continue

            # Determine earliest timestamp for this entry
            entry_time = entry_logged_at or not_before or timezone.now()

            if name in observations:
                obs = observations[name]
                obs['observation_count'] += 1
                if entry_time < obs['first_seen_at']:
                    obs['first_seen_at'] = entry_time
                if entry_time > obs['last_seen_at']:
                    obs['last_seen_at'] = entry_time
                    obs['last_cert_logged_at'] = entry_logged_at
                    obs['cert_not_before'] = not_before
                    obs['cert_not_after'] = not_after
                    obs['issuer_name'] = issuer
                    if cert_id:
                        obs['source_url'] = f'{CRT_SH_URL}?id={cert_id}'
            else:
                source_url = f'{CRT_SH_URL}?id={cert_id}' if cert_id else ''
                observations[name] = {
                    'fqdn': name,
                    'base_domain': base_domain,
                    'first_seen_at': entry_time,
                    'last_seen_at': entry_time,
                    'last_cert_logged_at': entry_logged_at,
                    'cert_not_before': not_before,
                    'cert_not_after': not_after,
                    'issuer_name': issuer,
                    'observation_count': 1,
                    'source_url': source_url,
                    'raw_payload': entry,
                    **classification,
                }

    return observations


def upsert_observations(observations, config):
    """
    Upsert parsed observations into the database.

    Preserves first_seen_at, updates last_seen_at, increments observation_count.

    Returns (created_count, updated_count, excluded_count).
    """
    created_count = 0
    updated_count = 0
    excluded_count = 0

    for fqdn, obs_data in observations.items():
        existing = CertificateSubdomainObservation.objects.filter(
            config=config,
            fqdn=fqdn,
        ).first()

        if existing:
            changed = False
            if obs_data['first_seen_at'] < existing.first_seen_at:
                existing.first_seen_at = obs_data['first_seen_at']
                changed = True
            if obs_data['last_seen_at'] > existing.last_seen_at:
                existing.last_seen_at = obs_data['last_seen_at']
                existing.last_cert_logged_at = obs_data.get('last_cert_logged_at')
                existing.cert_not_before = obs_data.get('cert_not_before')
                existing.cert_not_after = obs_data.get('cert_not_after')
                existing.issuer_name = obs_data.get('issuer_name', '')
                existing.source_url = obs_data.get('source_url', '')
                changed = True
            existing.observation_count += obs_data['observation_count']
            changed = True
            if changed:
                existing.save()
            updated_count += 1
        else:
            CertificateSubdomainObservation.objects.create(
                config=config,
                company=config.company,
                base_domain=obs_data['base_domain'],
                fqdn=fqdn,
                tenant_label=obs_data['tenant_label'],
                label_depth=obs_data['label_depth'],
                tenant_candidate=obs_data['tenant_candidate'],
                is_excluded=obs_data['is_excluded'],
                exclude_reason=obs_data['exclude_reason'],
                first_seen_at=obs_data['first_seen_at'],
                last_seen_at=obs_data['last_seen_at'],
                last_cert_logged_at=obs_data.get('last_cert_logged_at'),
                cert_not_before=obs_data.get('cert_not_before'),
                cert_not_after=obs_data.get('cert_not_after'),
                issuer_name=obs_data.get('issuer_name', ''),
                observation_count=obs_data['observation_count'],
                source_url=obs_data.get('source_url', ''),
                raw_payload=obs_data.get('raw_payload', {}),
            )
            created_count += 1

        if obs_data.get('is_excluded'):
            excluded_count += 1

    return created_count, updated_count, excluded_count


def run_sync(config):
    """
    Run a full sync for a SignalSourceConfig.

    Fetches data from crt.sh for each base domain, processes entries,
    and upserts observations. Logs a SignalSyncRun.

    Returns the SignalSyncRun instance.
    """
    sync_run = SignalSyncRun.objects.create(
        config=config,
        status=SignalSyncRun.Status.RUNNING,
    )

    settings_json = config.settings_json or {}
    base_domains = settings_json.get('base_domains', [])

    if not base_domains:
        sync_run.status = SignalSyncRun.Status.FAILED
        sync_run.error_text = 'No base_domains configured in settings_json'
        sync_run.finished_at = timezone.now()
        sync_run.save()
        return sync_run

    total_raw = 0
    total_unique = 0
    total_created = 0
    total_updated = 0
    total_excluded = 0
    errors = []

    session = requests.Session()

    for base_domain in base_domains:
        try:
            logger.info('Fetching CT data for %s ...', base_domain)
            entries = fetch_crtsh_json(base_domain, session=session)
            total_raw += len(entries)

            observations = process_crtsh_entries(entries, base_domain, config)
            total_unique += len(observations)

            created, updated, excluded = upsert_observations(observations, config)
            total_created += created
            total_updated += updated
            total_excluded += excluded

            logger.info(
                '%s: %d entries -> %d unique, %d created, %d updated, %d excluded',
                base_domain, len(entries), len(observations),
                created, updated, excluded,
            )

            # Be polite to crt.sh between domains
            if base_domain != base_domains[-1]:
                time.sleep(3)

        except Exception as e:
            msg = f'{base_domain}: {e}'
            logger.error('Error processing %s: %s', base_domain, e)
            errors.append(msg)

    # Finalize sync run
    sync_run.raw_items_seen = total_raw
    sync_run.unique_domains_parsed = total_unique
    sync_run.created_count = total_created
    sync_run.updated_count = total_updated
    sync_run.excluded_count = total_excluded
    sync_run.finished_at = timezone.now()

    if errors:
        sync_run.error_text = '\n'.join(errors)
        if total_created == 0 and total_updated == 0:
            sync_run.status = SignalSyncRun.Status.FAILED
        else:
            sync_run.status = SignalSyncRun.Status.SUCCESS
    else:
        sync_run.status = SignalSyncRun.Status.SUCCESS

    sync_run.metadata_json = {
        'base_domains': base_domains,
    }
    sync_run.save()

    # Update config last_synced_at
    config.last_synced_at = timezone.now()
    config.save(update_fields=['last_synced_at'])

    return sync_run
