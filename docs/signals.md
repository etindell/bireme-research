# Signals App

## What is the Signals tab?

The Signals tab provides alternative-data signal tracking for portfolio companies.
It surfaces proxy indicators derived from public data sources that may correlate
with business activity, such as customer acquisition trends.

**Important:** These signals are proxies, not literal customer counts or revenue
figures. They should be treated as one input among many in the research process.

## Cybozu CT Subdomain Tracker

The first signal source tracks certificate-transparency (CT) log activity for
Cybozu/Kintone base domains. When a company provisions a new subdomain
(e.g., `newcustomer.kintone.com`), a TLS certificate is typically issued and
logged in public CT logs.

### Why it's only a proxy

- Not every subdomain is a paying customer (could be trials, internal, or test).
- Some customers may share subdomains or use custom domains not captured here.
- CT logs have variable latency; certificates may appear days or weeks after provisioning.
- The ignore-keyword filter is heuristic, not perfect.

### Base domains tracked

- `cybozu.com`
- `cybozu.cn`
- `kintone.com`

### How it works

1. Queries [crt.sh](https://crt.sh) JSON API for wildcard matches on each base domain.
2. Parses the `name_value` field (which may contain newline-separated SAN entries).
3. Normalizes FQDNs (lowercase, strip wildcards and trailing dots).
4. Classifies each subdomain by label depth and ignore-keyword matching.
5. Upserts observations, preserving `first_seen_at` and incrementing `observation_count`.
6. Logs a `SignalSyncRun` with stats for each execution.

### Candidate classification

A subdomain is classified as a **tenant candidate** if:
- It has exactly 1 label before the base domain (depth = 1)
- The label does not contain any ignore keywords (test, staging, dev, demo, etc.)

All other subdomains (deeper paths, keyword matches) are stored but classified as
non-candidates.

## Setup

### 1. Run migration

```bash
python manage.py migrate signals
```

### 2. Create signal config

```bash
python manage.py create_signal_config \
    --company-slug cybozu \
    --source cybozu_ct_subdomains
```

This creates a `SignalSourceConfig` with sensible defaults for base domains and
ignore keywords.

### 3. Run initial backfill

```bash
python manage.py backfill_cybozu_ct --company-slug cybozu
```

This fetches all available historical CT log data from crt.sh and populates
observations. It may take a few minutes depending on data volume.

### 4. Run periodic syncs

```bash
python manage.py sync_cybozu_ct
```

Or for a specific company:

```bash
python manage.py sync_cybozu_ct --company-slug cybozu
```

This is idempotent and intended for cron/scheduled execution.

## Admin

All three models are registered in Django admin with useful list displays and
filters:

- **SignalSourceConfig**: Manage configs per company/org
- **SignalSyncRun**: View sync history and stats
- **CertificateSubdomainObservation**: Browse and search observations

## UI Features

- **Signals index** (`/signals/`): Overview of all configured signal sources
- **Company detail** (`/signals/<slug>/`): Monthly trend, candidate table, excluded section
- **Exclude/include**: HTMX-powered inline toggle to exclude false positives
- **Sync now**: Button on both the signals detail page and company detail card
- **Company detail card**: Signals summary card loads via HTMX on company pages
