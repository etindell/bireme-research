"""
Services for fetching and processing company news.
Uses Tavily for web search and Claude Haiku for AI processing.
"""
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


NEWS_PROCESSING_PROMPT = """You are a strict news filter for {company_name} (tickers: {tickers}).

Your job is to identify ONLY the 2-3 MOST IMPORTANT news items that investors absolutely need to know about. Be very selective.

ONLY include news that meets these criteria:
- Material events: earnings releases, M&A announcements, major contracts, executive changes, regulatory actions, significant legal developments
- Must specifically mention this company (not just the industry)
- Must be actual news articles (not stock price pages, company profiles, or generic financial data)
{blacklist_instruction}
REJECT everything else including:
- Stock quote/price pages
- Company profile pages
- Minor analyst mentions
- Industry news that doesn't specifically impact this company
- Routine press releases with no material information

Return a JSON array with AT MOST 3 items (fewer is fine, zero if nothing important):
[
  {{
    "url": "the original URL",
    "relevant": true,
    "headline": "cleaned up headline",
    "summary": "1-2 sentence summary of why this matters to investors",
    "importance": "high",
    "event_type": "earnings|management|M&A|regulatory|product|legal|analyst|filing|other",
    "source_name": "publication name"
  }}
]

If no items are truly important, return an empty array: []

NEWS ITEMS TO ANALYZE:
{news_items}
"""


def search_tavily(company, days_back: int = 2, extra_exclude_domains: list = None) -> list[dict]:
    """
    Search Tavily for recent company news.

    Args:
        company: Company model instance
        days_back: Number of days to search back
        extra_exclude_domains: Additional domains to exclude (user blacklist)

    Returns:
        List of raw news items from Tavily
    """
    api_key = os.environ.get('TAVILY_API_KEY')
    if not api_key:
        logger.error("TAVILY_API_KEY environment variable not set")
        return []

    # Build search query using company name and primary ticker
    primary_ticker = company.get_primary_ticker()
    if primary_ticker:
        query = f'"{company.name}" OR "{primary_ticker.symbol}"'
    else:
        query = f'"{company.name}"'

    # Exclude common stock quote/price sites that don't have actual news
    exclude_domains = [
        'finance.yahoo.com',
        'stockanalysis.com',
        'tradingview.com',
        'marketwatch.com/investing',
        'morningstar.com',
        'seekingalpha.com/symbol',
        'nasdaq.com/market-activity',
        'google.com/finance',
        'zacks.com/stock/quote',
        'tipranks.com',
    ]

    # Add user-blacklisted domains
    if extra_exclude_domains:
        exclude_domains.extend(extra_exclude_domains)

    try:
        response = requests.post(
            'https://api.tavily.com/search',
            json={
                'api_key': api_key,
                'query': query,
                'topic': 'news',  # Filter for news articles specifically
                'search_depth': 'basic',
                'include_answer': False,
                'include_raw_content': False,
                'max_results': 10,
                'days': days_back,
                'exclude_domains': exclude_domains,
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get('results', []):
            results.append({
                'url': item.get('url', ''),
                'title': item.get('title', ''),
                'content': item.get('content', ''),
                'published_date': item.get('published_date'),
                'source': 'tavily',
            })

        logger.info(f"Tavily returned {len(results)} results for {company.name}")
        return results

    except requests.RequestException as e:
        logger.error(f"Tavily search failed for {company.name}: {e}")
        return []


def fetch_edgar_filings(company, days_back: int = 7) -> list[dict]:
    """
    Fetch recent SEC filings from EDGAR RSS feed.

    Args:
        company: Company model instance
        days_back: Number of days to search back

    Returns:
        List of recent SEC filings
    """
    # Get CIK from ticker if available (US companies only)
    primary_ticker = company.get_primary_ticker()
    if not primary_ticker:
        return []

    # Skip non-US exchanges
    us_exchanges = ['NYSE', 'NASDAQ', 'AMEX', 'OTC', 'US']
    if primary_ticker.exchange and primary_ticker.exchange.upper() not in us_exchanges:
        return []

    try:
        # Use SEC EDGAR company search to find filings
        # Note: This is a simplified approach - a production system might use SEC's full API
        symbol = primary_ticker.symbol.replace('.', '-')  # Handle symbols like BRK.A

        # SEC EDGAR RSS feed for company filings
        rss_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={symbol}&type=8-K&dateb=&owner=include&count=10&output=atom"

        response = requests.get(
            rss_url,
            headers={'User-Agent': 'Bireme Research research@bireme.io'},
            timeout=30
        )

        if response.status_code != 200:
            return []

        # Parse the Atom feed (simplified parsing)
        results = []
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}

            cutoff_date = timezone.now() - timedelta(days=days_back)

            for entry in root.findall('atom:entry', ns):
                title = entry.find('atom:title', ns)
                link = entry.find('atom:link', ns)
                updated = entry.find('atom:updated', ns)

                if title is not None and link is not None:
                    # Parse date
                    pub_date = None
                    if updated is not None and updated.text:
                        try:
                            pub_date = datetime.fromisoformat(updated.text.replace('Z', '+00:00'))
                            if pub_date < cutoff_date:
                                continue
                        except ValueError:
                            pass

                    results.append({
                        'url': link.get('href', ''),
                        'title': title.text or 'SEC Filing',
                        'content': f"SEC EDGAR filing: {title.text}",
                        'published_date': pub_date.isoformat() if pub_date else None,
                        'source': 'sec_edgar',
                    })

            logger.info(f"EDGAR returned {len(results)} filings for {company.name}")

        except ET.ParseError:
            logger.warning(f"Failed to parse EDGAR RSS for {company.name}")

        return results

    except requests.RequestException as e:
        logger.error(f"EDGAR fetch failed for {company.name}: {e}")
        return []


def process_news_with_ai(company, raw_news: list[dict], blacklisted_domains: list = None) -> list[dict]:
    """
    Use Claude Haiku to filter, summarize, and classify news items.

    Args:
        company: Company model instance
        raw_news: List of raw news items from search
        blacklisted_domains: Domains to deprioritize/exclude

    Returns:
        List of processed news items ready for storage
    """
    if not raw_news:
        return []

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed")
        return []

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return []

    # Get ticker symbols
    tickers = ', '.join([t.symbol for t in company.tickers.all()[:5]])
    if not tickers:
        tickers = 'N/A'

    # Format news items for the prompt
    news_text = ""
    for i, item in enumerate(raw_news, 1):
        news_text += f"""
---
Item {i}:
URL: {item.get('url', 'N/A')}
Title: {item.get('title', 'N/A')}
Content: {item.get('content', 'N/A')[:500]}
Published: {item.get('published_date', 'Unknown')}
---
"""

    # Build blacklist instruction if there are blacklisted domains
    blacklist_instruction = ""
    if blacklisted_domains:
        blacklist_instruction = f"- EXCLUDE all news from these blacklisted domains: {', '.join(blacklisted_domains)}\n"

    prompt = NEWS_PROCESSING_PROMPT.format(
        company_name=company.name,
        tickers=tickers,
        news_items=news_text,
        blacklist_instruction=blacklist_instruction
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.content[0].text

        # Parse JSON response
        # Find JSON array in response (handle potential text around it)
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']') + 1

        if start_idx == -1 or end_idx == 0:
            logger.warning(f"No JSON array found in AI response for {company.name}")
            return []

        json_str = response_text[start_idx:end_idx]
        processed = json.loads(json_str)

        # Filter to only relevant items and add metadata
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
                })

        logger.info(f"AI identified {len(relevant_items)} relevant items for {company.name}")
        return relevant_items

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response for {company.name}: {e}")
        return []
    except Exception as e:
        logger.error(f"AI processing failed for {company.name}: {e}")
        return []


def fetch_and_store_news(company) -> int:
    """
    Full pipeline: fetch, process, and store news for a company.

    Args:
        company: Company model instance

    Returns:
        Count of new items stored
    """
    from .models import CompanyNews, BlacklistedDomain

    # Get user-blacklisted domains for this organization
    blacklisted_domains = list(
        BlacklistedDomain.objects.filter(
            organization=company.organization
        ).values_list('domain', flat=True)
    )

    # Gather raw news from all sources
    raw_news = []

    # Tavily web search (pass blacklisted domains)
    tavily_results = search_tavily(company, extra_exclude_domains=blacklisted_domains)
    raw_news.extend(tavily_results)

    # SEC EDGAR filings
    edgar_results = fetch_edgar_filings(company)
    raw_news.extend(edgar_results)

    if not raw_news:
        logger.info(f"No raw news found for {company.name}")
        return 0

    # Process with AI (pass blacklisted domains for additional filtering)
    processed = process_news_with_ai(company, raw_news, blacklisted_domains=blacklisted_domains)

    if not processed:
        logger.info(f"No relevant news after AI processing for {company.name}")
        return 0

    # Store in database
    stored_count = 0
    for item in processed:
        url = item.get('url', '')
        if not url:
            continue

        url_hash = hashlib.sha256(url.encode()).hexdigest()

        # Determine source type
        source_type = CompanyNews.SourceType.WEB
        if 'sec.gov' in url.lower():
            source_type = CompanyNews.SourceType.SEC_EDGAR

        # Parse published date or use now
        published_at = timezone.now()

        try:
            _, created = CompanyNews.objects.get_or_create(
                company=company,
                url_hash=url_hash,
                defaults={
                    'organization': company.organization,
                    'headline': item.get('headline', '')[:500],
                    'summary': item.get('summary', ''),
                    'source_url': url[:2000],
                    'source_name': item.get('source_name', 'Unknown')[:100],
                    'source_type': source_type,
                    'importance': item.get('importance', 'medium'),
                    'event_type': item.get('event_type', '')[:50],
                    'published_at': published_at,
                }
            )
            if created:
                stored_count += 1
        except Exception as e:
            logger.error(f"Failed to store news item for {company.name}: {e}")

    logger.info(f"Stored {stored_count} new news items for {company.name}")
    return stored_count
