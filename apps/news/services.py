"""
Services for fetching and processing company news.

Sources:
    1. Google News RSS (primary) — free, good financial coverage, real dates
    2. Tavily web search (supplementary) — catches items Google misses
    3. SEC EDGAR full-text search — material filings (8-K, 10-K, 10-Q, etc.)

Pipeline:
    fetch sources → pre-filter junk → AI classification → dedup & store
"""
import hashlib
import json
import logging
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse, quote_plus
from zoneinfo import ZoneInfo

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt for AI classification (step 2 — only sees pre-filtered results)
# ---------------------------------------------------------------------------

NEWS_PROCESSING_PROMPT = """You are a strict news filter for {company_name} (tickers: {tickers}).

Your job is to identify ONLY the 2-3 MOST IMPORTANT news items that investors absolutely need to know about. Be very selective.

ONLY include news that meets these criteria:
- Material events: earnings releases, M&A announcements, major contracts, executive changes, regulatory actions, significant legal developments
- Must specifically mention this company (not just the industry)
- Must be actual news articles (not stock price pages, company profiles, or generic financial data)
{blacklist_instruction}
DEDUPLICATE: If multiple articles cover the same story or event, keep ONLY the single most detailed and informative article. Do not return two items about the same underlying news.
{existing_instruction}
REJECT everything else including:
- Stock quote/price pages
- Company profile pages
- Minor analyst mentions
- Industry news that doesn't specifically impact this company
- Routine press releases with no material information
- Duplicate coverage of the same story (keep only the best article)

Return a JSON array with AT MOST 3 items (fewer is fine, zero if nothing important). Each item must be about a DIFFERENT story:
[
  {{
    "url": "the original URL",
    "relevant": true,
    "headline": "cleaned up headline",
    "summary": "1-2 sentence summary of why this matters to investors",
    "importance": "high|medium|low",
    "event_type": "earnings|management|M&A|regulatory|product|legal|analyst|filing|other",
    "source_name": "publication name",
    "published_date": "YYYY-MM-DD or null if unknown"
  }}
]

If no items are truly important, return an empty array: []

NEWS ITEMS TO ANALYZE:
{news_items}
"""


# ---------------------------------------------------------------------------
# Pre-filter: cheap, rule-based junk removal before sending to LLM
# ---------------------------------------------------------------------------

# URL path segments that indicate a stock-quote / profile page, not an article
_JUNK_PATH_PATTERNS = re.compile(
    r'/quote[s]?/'
    r'|/symbol/'
    r'|/stock/quote'
    r'|/market-activity/'
    r'|/investing/stock/'
    r'|/finance/quote'
    r'|/price-target/'
    r'|/etf/'
    r'|/mutual-fund/',
    re.IGNORECASE,
)

# Domains that are almost never real news articles
_JUNK_DOMAINS = {
    'stockanalysis.com',
    'tradingview.com',
    'morningstar.com',
    'tipranks.com',
    'simplywall.st',
    'macrotrends.net',
    'wisesheets.io',
    'dividendmax.com',
    'finviz.com',
    'chartmill.com',
}


def _extract_domain(url: str) -> str:
    """Extract bare domain from URL (strips www.)."""
    try:
        return urlparse(url).netloc.lower().replace('www.', '')
    except Exception:
        return ''


# Legal suffixes to strip (order matters — check longer ones first)
_LEGAL_SUFFIXES = [
    ', Inc.', ', Inc', ' Inc.', ' Inc',
    ', LLC', ' LLC',
    ', Ltd.', ', Ltd', ' Ltd.', ' Ltd',
    ', PLC', ' PLC', ', Plc', ' Plc',
    ' Corporation', ' Corp.', ' Corp',
    ' Company', ' Co.', ' Co',
    ' Incorporated',
    ' Limited',
    ' Group',
    ' Holdings',
    ' N.V.', ' N.V',
    ' S.A.', ' S.A',
    ' SE',
    ' AG',
    ' S.p.A.', ' S.p.A',
    ' Oyj',
    ' ASA',
    ' AB',
]

# Generic business words that would cause too many false-positive matches
_GENERIC_WORDS = {
    'the', 'and', 'for', 'from', 'with', 'group', 'holdings',
    'international', 'technologies', 'systems', 'services', 'global',
    'capital', 'financial', 'resources', 'industries', 'partners',
    'management', 'solutions', 'enterprises',
}


def _extract_common_names(company_name: str) -> set[str]:
    """
    Extract name variants from a company's legal name for relevance matching.

    "Moderna, Inc." → {"moderna, inc.", "moderna"}
    "Apple Inc." → {"apple inc.", "apple"}
    "BP" → {"bp"}
    """
    names = {company_name.lower()}

    # Strip legal suffixes
    short = company_name
    for suffix in _LEGAL_SUFFIXES:
        if short.endswith(suffix):
            short = short[:-len(suffix)].strip()
            break

    short_lower = short.lower()
    if short_lower and short_lower != company_name.lower():
        names.add(short_lower)

    # For multi-word names, also add individual significant words
    # This helps match "Semiconductor" in articles about TSMC, etc.
    # Only add words with 4+ chars to avoid false positives
    words = short_lower.split()
    if len(words) > 1:
        for word in words:
            if len(word) >= 4 and word not in _GENERIC_WORDS:
                names.add(word)

    return names


def prefilter_results(
    raw_news: list[dict],
    company_name: str,
    ticker_symbols: list[str],
    blacklisted_domains: list[str] | None = None,
) -> list[dict]:
    """
    Cheap rule-based filter applied *before* the LLM call.

    Removes:
        - URLs matching known quote/profile path patterns
        - Known junk domains
        - User-blacklisted domains
        - Items whose title doesn't mention the company or any ticker
    """
    blacklisted = set(blacklisted_domains or [])
    kept = []

    # Build a set of lowercase terms to check title relevance
    relevance_terms = _extract_common_names(company_name)
    for sym in ticker_symbols:
        relevance_terms.add(sym.lower())
        # Also add without exchange suffix (e.g. "7203" from "7203.T")
        base = sym.split('.')[0].lower()
        if base:
            relevance_terms.add(base)

    for item in raw_news:
        url = item.get('url', '')
        domain = _extract_domain(url)
        title = (item.get('title') or '').lower()
        content = (item.get('content') or '').lower()

        # Skip junk domains
        if domain in _JUNK_DOMAINS or domain in blacklisted:
            logger.debug(f"Pre-filter: skipped junk/blacklisted domain {domain}")
            continue

        # Skip quote/profile URLs
        if _JUNK_PATH_PATTERNS.search(url):
            logger.debug(f"Pre-filter: skipped quote-pattern URL {url}")
            continue

        # Relevance check: title or content snippet must mention company/ticker
        text_to_check = f"{title} {content}"
        if not any(term in text_to_check for term in relevance_terms):
            logger.debug(f"Pre-filter: no relevance match in '{title[:80]}'")
            continue

        kept.append(item)

    removed = len(raw_news) - len(kept)
    if removed:
        logger.info(
            f"Pre-filter: kept {len(kept)}/{len(raw_news)} items for {company_name}"
        )
    return kept


# ---------------------------------------------------------------------------
# Source 1: Google News RSS (primary)
# ---------------------------------------------------------------------------

def search_google_news(
    company,
    days_back: int = 3,
    max_results: int = 15,
) -> list[dict]:
    """
    Fetch recent news via Google News RSS.

    Builds two queries — one for company name, one for primary ticker —
    and deduplicates by URL. Returns items with real published dates.
    """
    primary_ticker = company.get_primary_ticker()
    queries = []

    # Query 1: company common name (strip legal suffixes like ", Inc.")
    # Google News exact-match on "Moderna, Inc." misses most articles
    common_names = _extract_common_names(company.name)
    # Pick the shortest non-trivial name variant (the "common" name)
    short_name = min(
        (n for n in common_names if len(n) > 2),
        key=len,
        default=company.name,
    )
    queries.append(quote_plus(f'"{short_name}"'))

    # Query 2: ticker symbol + "stock" to bias toward financial news
    if primary_ticker:
        queries.append(quote_plus(f'{primary_ticker.symbol} stock'))

    seen_urls = set()
    results = []

    for q in queries:
        rss_url = (
            f'https://news.google.com/rss/search'
            f'?q={q}+when:{days_back}d&hl=en-US&gl=US&ceid=US:en'
        )

        try:
            resp = requests.get(rss_url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; BiremeResearch/1.0)',
            })
            if resp.status_code != 200:
                logger.warning(
                    f"Google News returned {resp.status_code} for query '{q}'"
                )
                continue

            root = ET.fromstring(resp.content)
            channel = root.find('channel')
            if channel is None:
                continue

            for item_el in channel.findall('item'):
                link = (item_el.findtext('link') or '').strip()
                if not link or link in seen_urls:
                    continue
                seen_urls.add(link)

                title = (item_el.findtext('title') or '').strip()
                # Google News titles often end with " - Source Name"
                source_name = ''
                if ' - ' in title:
                    title, source_name = title.rsplit(' - ', 1)

                # Parse RFC-822 pubDate
                pub_date_str = item_el.findtext('pubDate')
                published_date = None
                if pub_date_str:
                    try:
                        published_date = parsedate_to_datetime(pub_date_str)
                    except Exception:
                        pass

                description = (item_el.findtext('description') or '').strip()
                # Description is often HTML; strip tags for a usable snippet
                description = re.sub(r'<[^>]+>', ' ', description).strip()

                # Extract the real publisher domain from RSS <source url="...">
                source_el = item_el.find('source')
                publisher_url = ''
                if source_el is not None:
                    publisher_url = source_el.get('url', '')
                    if not source_name:
                        source_name = (source_el.text or '').strip()

                results.append({
                    'url': link,
                    'title': title,
                    'content': description,
                    'published_date': published_date,
                    'source': 'google_news',
                    'source_name': source_name,
                    'publisher_url': publisher_url,
                })

                if len(results) >= max_results:
                    break

        except ET.ParseError:
            logger.warning(f"Failed to parse Google News RSS for query '{q}'")
        except requests.RequestException as e:
            logger.error(f"Google News request failed for query '{q}': {e}")

    logger.info(f"Google News returned {len(results)} results for {company.name}")
    return results


# ---------------------------------------------------------------------------
# Source 2: Tavily web search (supplementary)
# ---------------------------------------------------------------------------

def search_tavily(
    company,
    days_back: int = 3,
    extra_exclude_domains: list = None,
) -> list[dict]:
    """
    Search Tavily for recent company news.

    Used as a supplement to Google News — catches niche sources and
    press releases that Google may not surface quickly.
    """
    api_key = os.environ.get('TAVILY_API_KEY')
    if not api_key:
        logger.debug("TAVILY_API_KEY not set — skipping Tavily source")
        return []

    primary_ticker = company.get_primary_ticker()

    # Use common name (strip legal suffixes) for better search results
    common_names = _extract_common_names(company.name)
    short_name = min(
        (n for n in common_names if len(n) > 2),
        key=len,
        default=company.name,
    )

    if primary_ticker:
        query = f'"{short_name}" OR "{primary_ticker.symbol}" news'
    else:
        query = f'"{short_name}" news'

    exclude_domains = [
        'finance.yahoo.com',
        'stockanalysis.com',
        'tradingview.com',
        'morningstar.com',
        'tipranks.com',
        'google.com',
    ]
    if extra_exclude_domains:
        exclude_domains.extend(extra_exclude_domains)

    try:
        response = requests.post(
            'https://api.tavily.com/search',
            headers={
                'Authorization': f'Bearer {api_key}',
            },
            json={
                'query': query,
                'topic': 'news',
                'search_depth': 'basic',
                'include_answer': False,
                'include_raw_content': False,
                'max_results': 8,
                'days': days_back,
                'exclude_domains': exclude_domains,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get('results', []):
            # Parse Tavily's published_date (ISO format string or None)
            published_date = None
            raw_date = item.get('published_date')
            if raw_date:
                try:
                    published_date = datetime.fromisoformat(
                        raw_date.replace('Z', '+00:00')
                    )
                except (ValueError, TypeError):
                    pass

            results.append({
                'url': item.get('url', ''),
                'title': item.get('title', ''),
                'content': item.get('content', ''),
                'published_date': published_date,
                'source': 'tavily',
                'source_name': '',
            })

        logger.info(f"Tavily returned {len(results)} results for {company.name}")
        return results

    except requests.RequestException as e:
        logger.error(f"Tavily search failed for {company.name}: {e}")
        return []


# ---------------------------------------------------------------------------
# Source 3: SEC EDGAR full-text search (modern API)
# ---------------------------------------------------------------------------

def fetch_edgar_filings(company, days_back: int = 7) -> list[dict]:
    """
    Fetch recent SEC filings via the EDGAR full-text search API (efts).

    Only runs for US-listed companies. Searches for 8-K, 10-K, 10-Q,
    and other material filing types.
    """
    primary_ticker = company.get_primary_ticker()
    if not primary_ticker:
        return []

    us_exchanges = {'NYSE', 'NASDAQ', 'AMEX', 'OTC', 'US', ''}
    if primary_ticker.exchange and primary_ticker.exchange.upper() not in us_exchanges:
        return []

    symbol = primary_ticker.symbol.replace('.', '-')
    cutoff = (timezone.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

    try:
        # EDGAR full-text search API
        resp = requests.get(
            'https://efts.sec.gov/LATEST/search-index',
            params={
                'q': f'"{company.name}" OR "{symbol}"',
                'dateRange': 'custom',
                'startdt': cutoff,
                'enddt': timezone.now().strftime('%Y-%m-%d'),
                'forms': '8-K,10-K,10-Q,6-K,SC 13D,SC 13G',
            },
            headers={
                'User-Agent': 'Bireme Research contact@biremecapital.com',
                'Accept': 'application/json',
            },
            timeout=30,
        )

        if resp.status_code != 200:
            # Fallback: try the submissions JSON endpoint
            return _fetch_edgar_submissions(company, symbol, days_back)

        data = resp.json()
        results = []

        for hit in data.get('hits', {}).get('hits', []):
            source = hit.get('_source', {})
            file_date = source.get('file_date', '')
            form_type = source.get('form_type', '')
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{source.get('entity_id', '')}/{source.get('file_num', '')}"

            # Use the direct filing URL if available
            if source.get('file_name'):
                filing_url = f"https://www.sec.gov/Archives/{source['file_name']}"

            pub_date = None
            if file_date:
                try:
                    pub_date = datetime.strptime(file_date, '%Y-%m-%d').replace(
                        tzinfo=ZoneInfo('US/Eastern')
                    )
                except ValueError:
                    pass

            results.append({
                'url': filing_url,
                'title': f'{form_type}: {source.get("display_names", [company.name])[0] if source.get("display_names") else company.name}',
                'content': f'SEC {form_type} filing. {source.get("file_description", "")}',
                'published_date': pub_date,
                'source': 'sec_edgar',
                'source_name': 'SEC EDGAR',
            })

        logger.info(f"EDGAR search returned {len(results)} filings for {company.name}")
        return results

    except requests.RequestException as e:
        logger.error(f"EDGAR search failed for {company.name}: {e}")
        return _fetch_edgar_submissions(company, symbol, days_back)


def _fetch_edgar_submissions(company, symbol: str, days_back: int) -> list[dict]:
    """
    Fallback: fetch recent filings from EDGAR submissions JSON endpoint.
    """
    try:
        # First resolve ticker to CIK via SEC company tickers JSON
        resp = requests.get(
            'https://www.sec.gov/files/company_tickers.json',
            headers={'User-Agent': 'Bireme Research contact@biremecapital.com'},
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        cik = None
        for entry in resp.json().values():
            if entry.get('ticker', '').upper() == symbol.upper():
                cik = str(entry['cik_str']).zfill(10)
                break

        if not cik:
            return []

        # Fetch submissions
        resp = requests.get(
            f'https://data.sec.gov/submissions/CIK{cik}.json',
            headers={'User-Agent': 'Bireme Research contact@biremecapital.com'},
            timeout=15,
        )
        if resp.status_code != 200:
            return []

        data = resp.json()
        recent = data.get('filings', {}).get('recent', {})
        if not recent:
            return []

        cutoff = (timezone.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        results = []

        forms = recent.get('form', [])
        dates = recent.get('filingDate', [])
        accessions = recent.get('accessionNumber', [])
        descriptions = recent.get('primaryDocDescription', [])

        for i in range(min(len(forms), 20)):  # Check last 20 filings
            filing_date = dates[i] if i < len(dates) else ''
            if filing_date < cutoff:
                continue

            form_type = forms[i] if i < len(forms) else ''
            # Only include material filing types
            if form_type not in ('8-K', '10-K', '10-Q', '6-K', 'SC 13D', 'SC 13G', '4', '13F-HR'):
                continue

            accession = accessions[i].replace('-', '') if i < len(accessions) else ''
            desc = descriptions[i] if i < len(descriptions) else ''

            filing_url = f'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_type}&dateb=&owner=include&count=5'

            pub_date = None
            if filing_date:
                try:
                    pub_date = datetime.strptime(filing_date, '%Y-%m-%d').replace(
                        tzinfo=ZoneInfo('US/Eastern')
                    )
                except ValueError:
                    pass

            results.append({
                'url': filing_url,
                'title': f'{form_type}: {company.name}',
                'content': f'SEC {form_type} filing. {desc}',
                'published_date': pub_date,
                'source': 'sec_edgar',
                'source_name': 'SEC EDGAR',
            })

        logger.info(
            f"EDGAR submissions returned {len(results)} filings for {company.name}"
        )
        return results

    except Exception as e:
        logger.error(f"EDGAR submissions fallback failed for {company.name}: {e}")
        return []


# ---------------------------------------------------------------------------
# AI classification (runs on pre-filtered results only)
# ---------------------------------------------------------------------------

def process_news_with_ai(
    company,
    raw_news: list[dict],
    blacklisted_domains: list = None,
    existing_headlines: list[str] = None,
) -> list[dict]:
    """
    Use Gemini 3 Flash to filter, summarize, and classify news items.

    Only called on results that have already passed prefilter_results().
    Requires GEMINI_API_KEY environment variable.
    """
    if not raw_news:
        return []

    try:
        from google import genai
    except ImportError:
        logger.error("google-genai package not installed")
        return []

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable not set")
        return []

    tickers = ', '.join([t.symbol for t in company.tickers.all()[:5]]) or 'N/A'

    # Format news items for the prompt — include more content than before
    news_text = ""
    for i, item in enumerate(raw_news, 1):
        content = item.get('content', 'N/A') or 'N/A'
        # Allow up to 800 chars of content for better AI judgment
        if len(content) > 800:
            content = content[:800] + '...'

        pub_date = item.get('published_date')
        if isinstance(pub_date, datetime):
            pub_str = pub_date.strftime('%Y-%m-%d')
        elif pub_date:
            pub_str = str(pub_date)
        else:
            pub_str = 'Unknown'

        news_text += f"""
---
Item {i}:
URL: {item.get('url', 'N/A')}
Title: {item.get('title', 'N/A')}
Content: {content}
Published: {pub_str}
Source: {item.get('source_name') or item.get('source', 'Unknown')}
---
"""

    blacklist_instruction = ""
    if blacklisted_domains:
        blacklist_instruction = (
            f"- EXCLUDE all news from these blacklisted domains: "
            f"{', '.join(blacklisted_domains)}\n"
        )

    # Add existing headlines so Gemini can skip duplicate stories
    existing_instruction = ""
    if existing_headlines:
        headlines_list = '\n'.join(f'  - {h}' for h in existing_headlines[:20])
        existing_instruction = (
            f"\nThese stories have ALREADY been stored. "
            f"Do NOT return any item that covers the same story as these:\n"
            f"{headlines_list}\n"
        )

    prompt = NEWS_PROCESSING_PROMPT.format(
        company_name=company.name,
        tickers=tickers,
        news_items=news_text,
        blacklist_instruction=blacklist_instruction,
        existing_instruction=existing_instruction,
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=prompt,
        )

        response_text = response.text

        # Extract JSON array from response
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']') + 1
        if start_idx == -1 or end_idx == 0:
            logger.warning(f"No JSON array in AI response for {company.name}")
            return []

        processed = json.loads(response_text[start_idx:end_idx])

        relevant_items = []
        for item in processed:
            if item.get('relevant', False):
                relevant_items.append({
                    'url': item.get('url', ''),
                    'headline': item.get('headline', ''),
                    'summary': item.get('summary', ''),
                    'importance': item.get('importance', 'medium'),
                    'event_type': item.get('event_type', 'other'),
                    'source_name': item.get('source_name', 'Unknown'),
                    'published_date': item.get('published_date'),
                })

        logger.info(
            f"AI identified {len(relevant_items)} relevant items for {company.name}"
        )
        return relevant_items

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response for {company.name}: {e}")
        return []
    except Exception as e:
        logger.error(f"AI processing failed for {company.name}: {e}")
        return []


# ---------------------------------------------------------------------------
# Date parsing helper
# ---------------------------------------------------------------------------

def _parse_published_date(raw_news_item: dict, ai_item: dict) -> datetime:
    """
    Try to extract a real published date from multiple sources.

    Priority:
        1. Parsed datetime already on the raw news item
        2. Date string returned by the AI
        3. Fallback to now()
    """
    # 1. Check if the raw item already has a parsed datetime
    raw_date = raw_news_item.get('published_date') if raw_news_item else None
    if isinstance(raw_date, datetime):
        return raw_date

    # 2. Try the AI-returned date string
    ai_date_str = ai_item.get('published_date')
    if ai_date_str and ai_date_str != 'null':
        for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ'):
            try:
                return datetime.strptime(ai_date_str, fmt).replace(
                    tzinfo=ZoneInfo('UTC')
                )
            except (ValueError, TypeError):
                continue

    # 3. Try parsing raw_date as a string
    if isinstance(raw_date, str):
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d'):
            try:
                return datetime.strptime(
                    raw_date.replace('Z', ''), fmt
                ).replace(tzinfo=ZoneInfo('UTC'))
            except (ValueError, TypeError):
                continue
        # Try RFC-822
        try:
            return parsedate_to_datetime(raw_date)
        except Exception:
            pass

    return timezone.now()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def fetch_and_store_news(company) -> int:
    """
    Full pipeline: fetch → pre-filter → AI classify → dedup & store.

    Returns count of new items stored.
    """
    from .models import CompanyNews, BlacklistedDomain

    blacklisted_domains = list(
        BlacklistedDomain.objects.filter(
            organization=company.organization
        ).values_list('domain', flat=True)
    )

    # Collect ticker symbols for pre-filter relevance checks
    ticker_symbols = list(
        company.tickers.values_list('symbol', flat=True)[:10]
    )

    # ------------------------------------------------------------------
    # Step 1: Gather raw news from all sources (in parallel)
    # ------------------------------------------------------------------
    raw_news = []

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(search_google_news, company): 'google_news',
            pool.submit(search_tavily, company, 3, blacklisted_domains): 'tavily',
            pool.submit(fetch_edgar_filings, company): 'edgar',
        }
        for future in as_completed(futures):
            source_name = futures[future]
            try:
                raw_news.extend(future.result())
            except Exception as e:
                logger.error(f"Source {source_name} failed for {company.name}: {e}")

    if not raw_news:
        logger.info(f"No raw news found for {company.name}")
        return 0

    # Deduplicate by URL across sources
    seen_urls = set()
    deduped = []
    for item in raw_news:
        url = item.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(item)
    raw_news = deduped

    # ------------------------------------------------------------------
    # Step 2: Pre-filter junk before sending to LLM
    # ------------------------------------------------------------------
    filtered_news = prefilter_results(
        raw_news,
        company_name=company.name,
        ticker_symbols=ticker_symbols,
        blacklisted_domains=blacklisted_domains,
    )

    if not filtered_news:
        logger.info(f"No items survived pre-filter for {company.name}")
        return 0

    # Build a lookup from URL -> raw item (for date recovery later)
    raw_by_url = {item.get('url'): item for item in filtered_news}

    # Fetch recent existing headlines for cross-run dedup
    existing_headlines = list(
        CompanyNews.objects.filter(
            company=company,
            published_at__gte=timezone.now() - timedelta(days=7),
        ).values_list('headline', flat=True)[:20]
    )

    # ------------------------------------------------------------------
    # Step 3: AI classification
    # ------------------------------------------------------------------
    processed = process_news_with_ai(
        company, filtered_news,
        blacklisted_domains=blacklisted_domains,
        existing_headlines=existing_headlines,
    )

    if not processed:
        logger.info(f"No relevant news after AI processing for {company.name}")
        return 0

    # ------------------------------------------------------------------
    # Step 4: Store with proper dates
    # ------------------------------------------------------------------
    stored_count = 0
    for item in processed:
        url = item.get('url', '')
        if not url:
            continue

        url_hash = hashlib.sha256(url.encode()).hexdigest()

        source_type = CompanyNews.SourceType.WEB
        if 'sec.gov' in url.lower():
            source_type = CompanyNews.SourceType.SEC_EDGAR

        # Recover the real published date
        raw_item = raw_by_url.get(url, {})
        published_at = _parse_published_date(raw_item, item)

        # Extract publisher domain from publisher_url (Google News) or source_url
        publisher_domain = ''
        publisher_url = raw_item.get('publisher_url', '')
        if publisher_url:
            publisher_domain = _extract_domain(publisher_url)

        try:
            _, created = CompanyNews.objects.get_or_create(
                company=company,
                url_hash=url_hash,
                defaults={
                    'organization': company.organization,
                    'headline': item.get('headline', '')[:500],
                    'summary': item.get('summary', ''),
                    'source_url': url[:2000],
                    'source_name': (
                        item.get('source_name')
                        or raw_item.get('source_name')
                        or 'Unknown'
                    )[:100],
                    'source_type': source_type,
                    'publisher_domain': publisher_domain,
                    'importance': item.get('importance', 'medium'),
                    'event_type': item.get('event_type', '')[:50],
                    'published_at': published_at,
                },
            )
            if created:
                stored_count += 1
        except Exception as e:
            logger.error(f"Failed to store news item for {company.name}: {e}")

    logger.info(f"Stored {stored_count} new news items for {company.name}")
    return stored_count


def fetch_news_for_companies(companies, max_workers=4) -> tuple[int, list[str]]:
    """
    Fetch news for multiple companies concurrently.

    Returns (total_new_items, list_of_error_strings).

    max_workers controls how many companies are processed in parallel.
    Keep this moderate (4-5) to avoid hammering external API rate limits.
    """
    total = 0
    errors = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_company = {
            pool.submit(fetch_and_store_news, company): company
            for company in companies
        }
        for future in as_completed(future_to_company):
            company = future_to_company[future]
            try:
                count = future.result()
                total += count
            except Exception as e:
                logger.error(f"News fetch failed for {company.name}: {e}")
                errors.append(f"{company.name}: {e}")

    return total, errors
