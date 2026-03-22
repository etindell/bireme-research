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

    Returns a list of dicts, one per filing found. Each filing contains
    per-state detail: notice date, first sale date, investors, amount sold, expiry.
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
            filing_result = {'efd_id': efd_id, 'accession': accession, 'states': [], 'state_details': {}}

            try:
                # Fetch the notices page — has per-state detail
                notices_url = f'https://nasaaefd.org/FormD/ViewFilingNotices?EFDID={efd_id}&Accession={accession}'
                notices_resp = requests.get(notices_url, headers=headers, timeout=15)
                notices_resp.raise_for_status()
                notices_html = notices_resp.text

                # Parse the notices table
                # Columns: State | File Number | Notice Date | Accession | Offering Amount | Date of 1st Sale | Total # Investors | Amount Sold | Expires
                import re as _re
                tbody_match = _re.search(r'<tbody>(.*?)</tbody>', notices_html, _re.DOTALL)
                if tbody_match:
                    rows = _re.findall(r'<tr[^>]*>(.*?)</tr>', tbody_match.group(1), _re.DOTALL)
                    for row in rows:
                        cells = _re.findall(r'<td[^>]*>(.*?)</td>', row, _re.DOTALL)
                        clean = [_re.sub(r'<[^>]+>', '', c).strip() for c in cells]
                        if len(clean) >= 9 and clean[0] and len(clean[0]) == 2:
                            state_code = clean[0]
                            filing_result['states'].append(state_code)
                            filing_result['state_details'][state_code] = {
                                'file_number': clean[1],
                                'notice_date': clean[2],       # MM/DD/YYYY
                                'accession': clean[3],
                                'offering_amount': clean[4],
                                'first_sale_date': clean[5],    # M/D/YYYY or empty
                                'investors': clean[6],
                                'amount_sold': clean[7],
                                'expires': clean[8],
                            }

                # Fallback: parse from filing page if notices page had no table
                if not filing_result['states']:
                    detail_url = f'https://nasaaefd.org/FORMD/ViewFiling?EFDID={efd_id}&Accession={accession}'
                    time.sleep(SEC_REQUEST_DELAY)
                    detail_resp = requests.get(detail_url, headers=headers, timeout=15)
                    filed_match = re.search(r"Filed:</td><td>([A-Z, ]+)</td>", detail_resp.text)
                    if filed_match:
                        filing_result['states'] = [s.strip() for s in filed_match.group(1).split(',') if s.strip()]

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


def _parse_date(date_str):
    """Parse M/D/YYYY or MM/DD/YYYY to a date object, or None."""
    if not date_str or not date_str.strip():
        return None
    from datetime import datetime
    for fmt in ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d'):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


def import_jurisdictions_from_sec(fund):
    """
    Import investor jurisdictions for a fund from NASAA EFD state notice filings.

    Pulls per-state detail: notice date, first sale date, investors, amount sold.
    """
    result = fetch_fund_states(fund.name, cik=fund.edgar_cik or None)

    if result.get('error'):
        return {'created': [], 'existing': [], 'updated': [], 'error': result['error']}

    states = result.get('states', [])
    if not states:
        return {'created': [], 'existing': [], 'updated': [], 'error': 'No state notices found in NASAA EFD filings'}

    # Collect per-state details from the most recent filing
    state_details = {}
    for f in result.get('filings', []):
        for state_code, detail in f.get('state_details', {}).items():
            if state_code not in state_details:
                state_details[state_code] = detail

    created = []
    existing = []
    updated = []

    for state_code in states:
        iso_code = f'US-{state_code}'
        state_name = US_STATE_NAMES.get(state_code, state_code)
        detail = state_details.get(state_code, {})

        first_sale = _parse_date(detail.get('first_sale_date', ''))
        notice_date = _parse_date(detail.get('notice_date', ''))

        notes_parts = [f'Auto-imported from NASAA EFD (CIK: {result["cik"]})']
        if detail.get('investors'):
            notes_parts.append(f'Investors: {detail["investors"]}')
        if detail.get('amount_sold'):
            notes_parts.append(f'Amount sold: {detail["amount_sold"]}')
        if detail.get('expires') and detail['expires'] != 'Never':
            notes_parts.append(f'Expires: {detail["expires"]}')

        jur, was_created = InvestorJurisdiction.objects.get_or_create(
            fund=fund,
            jurisdiction_code=iso_code,
            defaults={
                'organization': fund.organization,
                'jurisdiction_name': state_name,
                'country': 'US',
                'first_sale_date': first_sale,
                'blue_sky_filed': True,
                'blue_sky_filing_date': notice_date,
                'notes': ' | '.join(notes_parts),
            }
        )

        if was_created:
            created.append(iso_code)
            from .blue_sky import generate_blue_sky_task
            generate_blue_sky_task(jur)
        else:
            # Update existing with new data if we have it
            changed = False
            if first_sale and not jur.first_sale_date:
                jur.first_sale_date = first_sale
                changed = True
            if notice_date and not jur.blue_sky_filing_date:
                jur.blue_sky_filing_date = notice_date
                jur.blue_sky_filed = True
                changed = True
            if changed:
                jur.save(update_fields=['first_sale_date', 'blue_sky_filing_date', 'blue_sky_filed', 'updated_at'])
                updated.append(iso_code)
            else:
                existing.append(iso_code)

    # Update the fund's CIK if we found it and it wasn't set
    if result.get('cik') and not fund.edgar_cik:
        fund.edgar_cik = result['cik']
        fund.save(update_fields=['edgar_cik', 'updated_at'])

    return {'created': created, 'existing': existing, 'updated': updated, 'error': None}
