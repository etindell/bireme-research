"""
Service for importing Form D filing data from SEC EDGAR.

Fetches states of solicitation from Form D filings and auto-creates
InvestorJurisdiction records for a fund.
"""

import time
import xml.etree.ElementTree as ET

import requests

from apps.compliance.models import InvestorJurisdiction

SEC_USER_AGENT = "Keelhaul Compliance/1.0 (admin@keelhaul.io)"
SEC_REQUEST_DELAY = 0.2  # seconds between requests (10 req/s rate limit)

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


def _sec_get(url, headers=None):
    """Make a GET request to SEC EDGAR with proper headers and rate limiting."""
    hdrs = {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    if headers:
        hdrs.update(headers)
    time.sleep(SEC_REQUEST_DELAY)
    resp = requests.get(url, headers=hdrs, timeout=30)
    resp.raise_for_status()
    return resp


def _find_form_d_filing_via_search(entity_name):
    """Search EDGAR full-text search for Form D filings by entity name."""
    url = "https://efts.sec.gov/LATEST/search-index"
    params = {
        "q": f'"{entity_name}"',
        "forms": "D",
        "dateRange": "custom",
        "startdt": "2015-01-01",
        "enddt": "2030-12-31",
    }
    print(f"[SEC Import] Searching EDGAR for Form D filings: {entity_name}")
    resp = _sec_get(url + "?" + "&".join(f"{k}={v}" for k, v in params.items()))
    data = resp.json()

    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        return None, None

    # Return the most recent hit — hits are typically sorted by date descending
    hit = hits[0]
    source = hit.get("_source", {})
    cik = source.get("entity_id") or source.get("ciks", [None])[0]
    # Extract accession number from the filing URL or _id
    file_id = hit.get("_id", "")
    return cik, source


def _find_form_d_filings_via_submissions(cik):
    """Use the EDGAR submissions API to find Form D filings for a known CIK."""
    padded_cik = str(cik).zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
    print(f"[SEC Import] Fetching submissions for CIK {padded_cik}")
    resp = _sec_get(url)
    data = resp.json()

    entity_name = data.get("name", "")
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    filing_dates = recent.get("filingDate", [])

    # Find the most recent Form D or D/A filing
    for i, form in enumerate(forms):
        if form in ("D", "D/A"):
            return {
                "cik": str(cik),
                "entity_name": entity_name,
                "accession_number": accession_numbers[i],
                "primary_document": primary_docs[i],
                "filing_date": filing_dates[i],
            }

    return None


def _fetch_form_d_xml(cik, accession_number, primary_document):
    """Fetch and parse the Form D XML filing."""
    # Accession number with dashes removed for the URL path
    accession_path = accession_number.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_path}/{primary_document}"
    print(f"[SEC Import] Fetching Form D XML: {url}")
    resp = _sec_get(url)
    return resp.text


def _parse_form_d_xml(xml_text):
    """Parse Form D XML and extract states, first sale date, and offering amount."""
    states = []
    first_sale_date = None
    total_offering_amount = None

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"[SEC Import] XML parse error: {e}")
        return states, first_sale_date, total_offering_amount

    # The XML may have namespaces; strip them for easier parsing
    # Common namespace: http://www.sec.gov/edgar/document/formd
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    # Find states of solicitation
    for elem in root.iter(f"{ns}stateOrCountryDescription"):
        code = elem.text
        if code and len(code) == 2 and code.upper() in US_STATE_NAMES:
            states.append(code.upper())

    # Also check the more common tag structure
    for elem in root.iter(f"{ns}value"):
        parent = None
        # Walk the tree to find value elements under statesOfSolOfferingType
        code = elem.text
        if code and len(code) == 2 and code.upper() in US_STATE_NAMES:
            if code.upper() not in states:
                states.append(code.upper())

    # Broader search: find any element containing state codes under solicitation sections
    for tag_name in ("statesOfSolOfferingType", "stateOrCountry"):
        for parent_elem in root.iter(f"{ns}{tag_name}"):
            for child in parent_elem:
                code = child.text
                if code and len(code) == 2 and code.upper() in US_STATE_NAMES:
                    if code.upper() not in states:
                        states.append(code.upper())

    # Extract first sale date
    for elem in root.iter(f"{ns}dateOfFirstSale"):
        for child in elem:
            if child.text and child.text.strip():
                first_sale_date = child.text.strip()
                break
        if not first_sale_date and elem.text and elem.text.strip():
            first_sale_date = elem.text.strip()

    # Extract total offering amount
    for elem in root.iter(f"{ns}totalOfferingAmount"):
        if elem.text and elem.text.strip():
            total_offering_amount = elem.text.strip()
            break

    return states, first_sale_date, total_offering_amount


def fetch_form_d_states(entity_name, cik=None):
    """
    Fetch Form D filing data from SEC EDGAR and extract states of solicitation.

    Args:
        entity_name: Name of the entity to search for.
        cik: Optional CIK number. If provided, uses the submissions API directly.

    Returns:
        Dict with keys: states, first_sale_date, entity_name, cik, offering_amount.
        On failure, returns dict with 'error' key and empty states list.
    """
    try:
        filing_info = None

        if cik:
            filing_info = _find_form_d_filings_via_submissions(cik)
            if not filing_info:
                return {
                    "error": f"No Form D filing found for CIK {cik}",
                    "states": [],
                }
        else:
            search_cik, source = _find_form_d_filing_via_search(entity_name)
            if not search_cik:
                return {
                    "error": f"No Form D filing found for '{entity_name}'",
                    "states": [],
                }
            # Now use the CIK from search to get filing details via submissions API
            filing_info = _find_form_d_filings_via_submissions(search_cik)
            if not filing_info:
                return {
                    "error": f"No Form D filing found in submissions for CIK {search_cik}",
                    "states": [],
                }

        # Fetch and parse the XML
        xml_text = _fetch_form_d_xml(
            filing_info["cik"],
            filing_info["accession_number"],
            filing_info["primary_document"],
        )
        states, first_sale_date, offering_amount = _parse_form_d_xml(xml_text)

        print(f"[SEC Import] Found {len(states)} states of solicitation: {states}")

        return {
            "states": sorted(states),
            "first_sale_date": first_sale_date,
            "entity_name": filing_info.get("entity_name", entity_name),
            "cik": filing_info.get("cik", str(cik) if cik else ""),
            "offering_amount": offering_amount,
        }

    except requests.RequestException as e:
        print(f"[SEC Import] Network error: {e}")
        return {"error": f"Network error fetching SEC data: {e}", "states": []}
    except Exception as e:
        print(f"[SEC Import] Unexpected error: {e}")
        return {"error": f"Unexpected error: {e}", "states": []}


def import_jurisdictions_from_sec(fund):
    """
    Import investor jurisdictions from SEC EDGAR Form D filings for a fund.

    Takes a Fund instance, fetches Form D data, and creates InvestorJurisdiction
    records for each state of solicitation listed in the filing.

    Args:
        fund: A Fund model instance.

    Returns:
        Dict with keys: created (list), existing (list), error (str or None).
    """
    from apps.compliance.services.blue_sky import generate_blue_sky_task

    result = {"created": [], "existing": [], "error": None}

    # Use edgar_cik if available, otherwise search by fund name
    cik = fund.edgar_cik if fund.edgar_cik else None
    sec_data = fetch_form_d_states(entity_name=fund.name, cik=cik)

    if sec_data.get("error"):
        result["error"] = sec_data["error"]
        return result

    states = sec_data.get("states", [])
    first_sale_date = sec_data.get("first_sale_date")

    # Parse first_sale_date if it's a string
    parsed_sale_date = None
    if first_sale_date:
        try:
            from datetime import date as date_type

            # Handle various date formats from SEC
            for fmt in ("%Y-%m-%d", "%m-%d-%Y", "%m/%d/%Y"):
                try:
                    parsed_sale_date = date_type(
                        *map(int, first_sale_date.replace("/", "-").split("-")[:3])
                    )
                    break
                except (ValueError, TypeError):
                    continue
            if not parsed_sale_date:
                from datetime import datetime
                parsed_sale_date = datetime.strptime(first_sale_date, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            print(f"[SEC Import] Could not parse first_sale_date: {first_sale_date}")

    for state_code in states:
        jurisdiction_code = f"US-{state_code}"
        jurisdiction_name = US_STATE_NAMES.get(state_code, state_code)

        ij, created = InvestorJurisdiction.objects.get_or_create(
            fund=fund,
            jurisdiction_code=jurisdiction_code,
            organization=fund.organization,
            defaults={
                "jurisdiction_name": jurisdiction_name,
                "country": "US",
                "first_sale_date": parsed_sale_date,
                "notes": "Auto-imported from SEC EDGAR Form D filing",
            },
        )

        if created:
            print(f"[SEC Import] Created jurisdiction: {jurisdiction_name} ({jurisdiction_code})")
            result["created"].append(jurisdiction_code)
            generate_blue_sky_task(ij)
        else:
            print(f"[SEC Import] Jurisdiction already exists: {jurisdiction_name} ({jurisdiction_code})")
            result["existing"].append(jurisdiction_code)

    print(
        f"[SEC Import] Done. Created {len(result['created'])}, "
        f"existing {len(result['existing'])}."
    )
    return result
