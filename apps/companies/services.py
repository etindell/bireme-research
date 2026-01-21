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


SUMMARY_PROMPT_TEMPLATE_PORTFOLIO = """Summarize the following research notes for {company_name} (a portfolio holding).

Be succinct and focus on actionable information.

IMPORTANT: For time-sensitive metrics (valuation, IRR, price), only use data from the last 60 days and include dates.

OUTPUT FORMAT (use markdown, keep each section brief):
- **Business Overview**: 2-3 sentences on what the company does
- **Valuation**: Current valuation metrics and estimates with dates
- **Investment Thesis**: Key reasons for the position (3-5 bullet points)
{key_questions_section}
Keep total length under 400 words.

TODAY'S DATE: {today_date}

NOTES (most recent first):
{notes_content}
"""

SUMMARY_PROMPT_TEMPLATE_RESEARCH = """Summarize the following research notes for {company_name} (a research candidate).

Be succinct and focus on key information needed to evaluate the opportunity.

IMPORTANT: For time-sensitive metrics (valuation, IRR, price), only use data from the last 60 days and include dates.

OUTPUT FORMAT (use markdown, keep each section brief):
- **Business Overview**: 2-3 sentences on what the company does
- **Valuation**: Current valuation metrics and estimates with dates
{key_questions_section}
Keep total length under 300 words.

TODAY'S DATE: {today_date}

NOTES (most recent first):
{notes_content}
"""

KEY_QUESTIONS_SECTION = """- **Key Questions**: For each question below, briefly summarize what is known from the notes:
{key_questions_formatted}
"""

FOCUS_TOPIC_ADDITION = """

ADDITIONAL FOCUS AREA: {focus_topic}
In addition to the standard sections above, please include a dedicated section:
- **{focus_topic}**: Search through all notes for any information related to this topic. Include relevant details, quotes, dates, and context. If no information is found, state "No specific information found in notes regarding this topic."
"""


def generate_company_summary(company, focus_topic: Optional[str] = None) -> Optional[str]:
    """
    Generate an AI summary of research notes for a company using Claude 3 Haiku.

    Args:
        company: Company model instance
        focus_topic: Optional topic to focus on in the summary (e.g., "capital allocation and dividends")

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

    # Build key questions section if company has key questions
    key_questions_section = ""
    if company.key_questions and company.key_questions.strip():
        questions = [q.strip() for q in company.key_questions.strip().split('\n') if q.strip()]
        if questions:
            formatted_questions = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(questions))
            key_questions_section = KEY_QUESTIONS_SECTION.format(
                key_questions_formatted=formatted_questions
            )

    # Select template based on company status
    # Portfolio companies (long_book, short_book) get investment thesis section
    # Research candidates (on_deck, watchlist, etc.) get a more concise format
    from apps.companies.models import Company
    is_portfolio = company.status in [Company.Status.LONG_BOOK, Company.Status.SHORT_BOOK]

    if is_portfolio:
        template = SUMMARY_PROMPT_TEMPLATE_PORTFOLIO
    else:
        template = SUMMARY_PROMPT_TEMPLATE_RESEARCH

    # Build prompt
    today_date = timezone.now().strftime('%Y-%m-%d')
    prompt = template.format(
        company_name=company.name,
        today_date=today_date,
        notes_content="\n".join(notes_content),
        key_questions_section=key_questions_section
    )

    # Append focus topic section if provided
    if focus_topic:
        prompt += FOCUS_TOPIC_ADDITION.format(focus_topic=focus_topic)

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
