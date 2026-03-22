"""
Service for importing blue sky filing data from NASAA EFD and SEC EDGAR.

NASAA EFD (Electronic Filing Depository) tracks actual state notice filings
per fund entity. This is the authoritative source for which states a fund
has filed blue sky notices in.

SEC EDGAR is used to find the CIK and accession numbers needed to look up
filings on NASAA EFD.
"""

import re
import time

import requests

from apps.compliance.models import InvestorJurisdiction

SEC_USER_AGENT = "Keelhaul Compliance/1.0 (admin@keelhaul.io)"
SEC_REQUEST_DELAY = 0.2

US_STATE_NAMES = {
    'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
    'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
    'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
    'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
    'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
    'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
    'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
    'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
    'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
    'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
    'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
    'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
    'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia',
}


def find_cik_from_edgar(entity_name):
    """Search EDGAR for a fund's CIK by name."""
    headers = {'User-Agent': SEC_USER_AGENT}
    try:
        url = 'https://efts.sec.gov/LATEST/search-index'
        params = {
            'q': f'"{entity_name}"',
            'forms': 'D',
            'dateRange': 'custom',
            'startdt': '2015-01-01',
            'enddt': '2030-12-31',
        }
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        hits = data.get('hits', {}).get('hits', [])
        if hits:
            source = hits[0].get('_source', {})
            cik = source.get('entity_id', '')
            return cik
    except Exception as e:
        print(f'[SEC Import] EDGAR search error: {e}')
    return None


def fetch_nasaa_efd_filings(cik):
    """
    Search NASAA EFD for a fund's state notice filings by CIK.

    Returns a list of dicts, one per filing found:
    [{'efd_id': '507159', 'accession': '0001554856-25-000002', 'states': ['CA', 'CT', 'NY', 'TX']}, ...]
    """
    headers = {'User-Agent': SEC_USER_AGENT}
    results = []

    try:
        # Search NASAA EFD by CIK
        search_url = f'https://nasaaefd.org/Search?search={cik}'
        resp = requests.get(search_url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Extract filing links: /FORMD/ViewFiling?EFDID=507159&Accession=0001554856-25-000002
        filing_pattern = r"FORMD/ViewFiling\?EFDID=(\d+)&(?:amp;)?Accession=([\d-]+)"
        filings = re.findall(filing_pattern, html)

        for efd_id, accession in filings:
            time.sleep(SEC_REQUEST_DELAY)
            filing_result = {'efd_id': efd_id, 'accession': accession, 'states': []}

            try:
                # Fetch the filing detail page to get state notices
                detail_url = f'https://nasaaefd.org/FORMD/ViewFiling?EFDID={efd_id}&Accession={accession}'
                detail_resp = requests.get(detail_url, headers=headers, timeout=15)
                detail_resp.raise_for_status()
                detail_html = detail_resp.text

                # Parse "Filed: CA, CT, NY, TX" pattern
                filed_match = re.search(r"Filed:</td><td>([A-Z, ]+)</td>", detail_html)
                if filed_match:
                    states_str = filed_match.group(1)
                    states = [s.strip() for s in states_str.split(',') if s.strip()]
                    filing_result['states'] = states

                # Try to extract entity name
                name_match = re.search(r'lblEntityName["\']?>([^<]+)<', detail_html)
                if name_match:
                    filing_result['entity_name'] = name_match.group(1).strip()

            except Exception as e:
                print(f'[NASAA EFD] Error fetching filing {efd_id}: {e}')

            results.append(filing_result)

    except Exception as e:
        print(f'[NASAA EFD] Search error: {e}')

    return results


def fetch_fund_states(fund_name, cik=None):
    """
    Get the states where a fund has blue sky notice filings from NASAA EFD.

    Returns:
    {
        'states': ['CA', 'CT', 'NY', 'TX'],
        'cik': '0001554856',
        'source': 'NASAA EFD',
        'filings': [...],
        'error': None,
    }
    """
    # Find CIK if not provided
    if not cik:
        cik = find_cik_from_edgar(fund_name)
        if not cik:
            return {'states': [], 'cik': None, 'source': None, 'filings': [], 'error': f'Could not find CIK for "{fund_name}" on EDGAR'}

    # Pad CIK for NASAA EFD search
    cik_padded = cik.zfill(10) if not cik.startswith('0') else cik

    print(f'[SEC Import] Searching NASAA EFD for CIK {cik_padded}')
    filings = fetch_nasaa_efd_filings(cik_padded)

    if not filings:
        return {'states': [], 'cik': cik_padded, 'source': 'NASAA EFD', 'filings': [], 'error': 'No filings found on NASAA EFD'}

    # Use the most recent filing's states (first in list)
    # Also collect all unique states across all filings
    all_states = set()
    for f in filings:
        all_states.update(f.get('states', []))

    return {
        'states': sorted(all_states),
        'cik': cik_padded,
        'source': 'NASAA EFD',
        'filings': filings,
        'error': None,
    }


def import_jurisdictions_from_sec(fund):
    """
    Import investor jurisdictions for a fund from NASAA EFD state notice filings.

    Takes a Fund instance, fetches its blue sky filing data, and creates
    InvestorJurisdiction records for each state found.
    """
    result = fetch_fund_states(fund.name, cik=fund.edgar_cik or None)

    if result.get('error'):
        return {'created': [], 'existing': [], 'error': result['error']}

    states = result.get('states', [])
    if not states:
        return {'created': [], 'existing': [], 'error': 'No state notices found in NASAA EFD filings'}

    created = []
    existing = []

    for state_code in states:
        iso_code = f'US-{state_code}'
        state_name = US_STATE_NAMES.get(state_code, state_code)

        jur, was_created = InvestorJurisdiction.objects.get_or_create(
            fund=fund,
            jurisdiction_code=iso_code,
            defaults={
                'organization': fund.organization,
                'jurisdiction_name': state_name,
                'country': 'US',
                'blue_sky_filed': True,  # We know it's filed because NASAA EFD shows it
                'notes': f'Auto-imported from NASAA EFD (CIK: {result["cik"]})',
            }
        )

        if was_created:
            created.append(iso_code)
            # Generate blue sky task for ongoing tracking
            from .blue_sky import generate_blue_sky_task
            generate_blue_sky_task(jur)
        else:
            existing.append(iso_code)

    # Update the fund's CIK if we found it and it wasn't set
    if result.get('cik') and not fund.edgar_cik:
        fund.edgar_cik = result['cik']
        fund.save(update_fields=['edgar_cik', 'updated_at'])

    return {'created': created, 'existing': existing, 'error': None}
