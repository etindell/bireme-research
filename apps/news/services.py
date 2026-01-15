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


NEWS_PROCESSING_PROMPT = """You are analyzing news for {company_name} (tickers: {tickers}).

Review these news items and for each one:
1. Determine if it's relevant to this specific company (not just the industry in general)
2. If relevant, provide:
   - A concise 1-2 sentence summary of the key information
   - Importance rating:
     * high: Material events (earnings, M&A, major contracts, executive changes, regulatory actions)
     * medium: Notable but not material (analyst ratings, product updates, partnerships)
     * low: Minor mentions or tangential references
   - Event type: earnings, management, M&A, regulatory, product, legal, analyst, filing, or other

IMPORTANT: Only mark items as relevant if they specifically mention or directly concern this company.

Return a JSON array with your analysis:
[
  {{
    "url": "the original URL",
    "relevant": true or false,
    "headline": "cleaned up headline",
    "summary": "1-2 sentence summary",
    "importance": "high", "medium", or "low",
    "event_type": "category",
    "source_name": "publication name"
  }}
]

If no items are relevant, return an empty array: []

NEWS ITEMS TO ANALYZE:
{news_items}
"""


def search_tavily(company, days_back: int = 2) -> list[dict]:
    """
    Search Tavily for recent company news.

    Args:
        company: Company model instance
        days_back: Number of days to search back

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
        query = f'"{company.name}" OR "{primary_ticker.symbol}" stock news'
    else:
        query = f'"{company.name}" company news'

    try:
        response = requests.post(
            'https://api.tavily.com/search',
            json={
                'api_key': api_key,
                'query': query,
                'search_depth': 'basic',
                'include_answer': False,
                'include_raw_content': False,
                'max_results': 10,
                'days': days_back,
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


def process_news_with_ai(company, raw_news: list[dict]) -> list[dict]:
    """
    Use Claude Haiku to filter, summarize, and classify news items.

    Args:
        company: Company model instance
        raw_news: List of raw news items from search

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

    prompt = NEWS_PROCESSING_PROMPT.format(
        company_name=company.name,
        tickers=tickers,
        news_items=news_text
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-3-haiku-20240307",
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
    from .models import CompanyNews

    # Gather raw news from all sources
    raw_news = []

    # Tavily web search
    tavily_results = search_tavily(company)
    raw_news.extend(tavily_results)

    # SEC EDGAR filings
    edgar_results = fetch_edgar_filings(company)
    raw_news.extend(edgar_results)

    if not raw_news:
        logger.info(f"No raw news found for {company.name}")
        return 0

    # Process with AI
    processed = process_news_with_ai(company, raw_news)

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
