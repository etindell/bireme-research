"""
Services for company valuation calculations and external data fetching.
"""
import logging
import os
from datetime import timedelta
from decimal import Decimal
from typing import Optional, List

from django.utils import timezone

logger = logging.getLogger(__name__)


SUMMARY_PROMPT_TEMPLATE = """Summarize the following research notes for {company_name}.

IMPORTANT DATE HANDLING INSTRUCTIONS:
1. For TIME-SENSITIVE metrics (valuation, IRR, price targets, model assumptions, market cap, earnings estimates, sell-side ratings):
   - ONLY use information from notes dated within the last 60 days
   - Always state the date when these metrics were recorded (e.g., "As of Oct 2025...")
   - NEVER use words like "current", "today", or "now" for metrics older than 30 days

2. For HISTORICAL events (earnings releases, management changes, acquisitions, regulatory decisions):
   - You may reference older notes but always include the date (e.g., "In Jan 2025, Nigeria approved...")
   - Frame these as past events, not current state

3. For TIMELESS information (business model, investment thesis, risk factors, competitive dynamics):
   - Synthesize across all notes
   - These don't need date attribution unless the situation has changed

OUTPUT FORMAT:
Use markdown with these sections:
- **Business Overview**: 2-3 sentences on what the company does
- **Valuation & Estimates**: Only from recent notes, with dates
- **Investment Thesis**: Key reasons to own the stock
- **Key Events Timeline**: Important developments with dates
- **Risks**: Main risk factors
- **Recent Developments**: From most recent 1-2 notes

Keep the summary concise (400-600 words).

TODAY'S DATE: {today_date}

NOTES (most recent first):
{notes_content}
"""


def generate_company_summary(company) -> Optional[str]:
    """
    Generate an AI summary of research notes for a company using Claude 3 Haiku.

    Args:
        company: Company model instance

    Returns:
        Generated summary string or None if generation fails.
    """
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed. Run: pip install anthropic")
        return None

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return None

    # Fetch notes for this company, ordered by date (most recent first)
    from apps.notes.models import Note
    from django.db.models.functions import Coalesce

    notes = Note.objects.filter(
        company=company,
        is_deleted=False
    ).annotate(
        effective_date=Coalesce('written_at', 'created_at')
    ).order_by('-effective_date')

    if not notes.exists():
        logger.info(f"No notes found for {company.name}")
        return None

    # Build notes content with dates
    notes_content = []
    for note in notes:
        note_date = note.written_at or note.created_at
        date_str = note_date.strftime('%Y-%m-%d') if note_date else 'Unknown date'

        note_text = f"---\n[{date_str}] {note.title}\n"
        if note.content:
            note_text += f"{note.content}\n"
        note_text += "---\n"
        notes_content.append(note_text)

    # Build prompt
    today_date = timezone.now().strftime('%Y-%m-%d')
    prompt = SUMMARY_PROMPT_TEMPLATE.format(
        company_name=company.name,
        today_date=today_date,
        notes_content="\n".join(notes_content)
    )

    # Call Claude 3 Haiku
    try:
        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        summary = message.content[0].text

        # Update company with summary
        company.ai_summary = summary
        company.summary_updated_at = timezone.now()
        company.save(update_fields=['ai_summary', 'summary_updated_at'])

        logger.info(f"Generated summary for {company.name}")
        return summary

    except Exception as e:
        logger.error(f"Failed to generate summary for {company.name}: {e}")
        return None


def summary_is_stale(company, days: int = 7) -> bool:
    """
    Check if a company's summary needs regeneration.

    Returns True if:
    - No summary exists
    - Summary is older than `days` days
    - Notes have been added/updated since summary was generated
    """
    if not company.ai_summary or not company.summary_updated_at:
        return True

    # Check if summary is older than threshold
    threshold = timezone.now() - timedelta(days=days)
    if company.summary_updated_at < threshold:
        return True

    # Check if any notes are newer than the summary
    from apps.notes.models import Note
    from django.db.models.functions import Coalesce

    latest_note = Note.objects.filter(
        company=company,
        is_deleted=False
    ).annotate(
        effective_date=Coalesce('written_at', 'created_at')
    ).order_by('-effective_date', '-updated_at').first()

    if latest_note:
        note_date = max(
            latest_note.written_at or latest_note.created_at,
            latest_note.updated_at
        )
        if note_date > company.summary_updated_at:
            return True

    return False


def calculate_irr(cash_flows: List[float]) -> Optional[Decimal]:
    """
    Calculate Internal Rate of Return for a series of cash flows.

    Args:
        cash_flows: List of cash flows where index 0 is initial investment (negative)
                   and subsequent values are returns for years 1-5.

    Returns:
        IRR as a Decimal (e.g., 0.15 for 15%) or None if calculation fails.
    """
    try:
        import numpy_financial as npf
        import numpy as np

        irr = npf.irr(cash_flows)
        if irr is not None and not np.isnan(irr) and not np.isinf(irr):
            # Convert to percentage and round to 2 decimal places
            return Decimal(str(round(irr * 100, 2)))
    except Exception as e:
        logger.warning(f"IRR calculation failed: {e}")
    return None


def fetch_stock_price(symbol: str) -> Optional[dict]:
    """
    Fetch current stock price and valuation metrics from Yahoo Finance.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL')

    Returns:
        Dict with price, metrics, and company info or None if fetch fails.
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Get current price - try multiple fields
        price = info.get('currentPrice') or info.get('regularMarketPrice')

        # Get EV/EBITDA ratio
        ev_ebitda = info.get('enterpriseToEbitda')

        # Get market cap
        market_cap = info.get('marketCap')

        # Get business summary (truncate to 1000 chars if too long)
        business_summary = info.get('longBusinessSummary', '')
        if business_summary and len(business_summary) > 1000:
            business_summary = business_summary[:997] + '...'

        if price:
            return {
                'price': Decimal(str(price)),
                'currency': info.get('currency', 'USD'),
                'timestamp': timezone.now(),
                'market_cap': Decimal(str(market_cap)) if market_cap else None,
                'shares_outstanding': info.get('sharesOutstanding'),
                'ev_ebitda': Decimal(str(ev_ebitda)) if ev_ebitda else None,
                'business_summary': business_summary,
                'sector': info.get('sector', ''),
                'industry': info.get('industry', ''),
            }
    except Exception as e:
        logger.error(f"Failed to fetch price for {symbol}: {e}")

    return None


def update_valuation_prices(valuation_ids: List[int] = None, organization=None) -> int:
    """
    Batch update stock prices for valuations.

    Args:
        valuation_ids: Specific valuations to update, or None for all active
        organization: Filter by organization

    Returns:
        Number of valuations updated
    """
    from apps.companies.models import CompanyValuation

    queryset = CompanyValuation.objects.filter(
        is_active=True,
        is_deleted=False
    ).select_related('company')

    if valuation_ids:
        queryset = queryset.filter(pk__in=valuation_ids)
    if organization:
        queryset = queryset.filter(company__organization=organization)

    updated_count = 0
    for valuation in queryset:
        ticker = valuation.company.get_primary_ticker()
        if not ticker:
            continue

        price_data = fetch_stock_price(ticker.symbol)
        if price_data and price_data['price']:
            valuation.current_price = price_data['price']
            valuation.price_last_updated = price_data['timestamp']
            valuation.save(update_fields=[
                'current_price', 'price_last_updated',
                'calculated_irr', 'irr_last_calculated'
            ])
            updated_count += 1

    return updated_count
