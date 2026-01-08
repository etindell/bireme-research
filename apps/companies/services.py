"""
Services for company valuation calculations and external data fetching.
"""
import logging
from decimal import Decimal
from typing import Optional, List

from django.utils import timezone

logger = logging.getLogger(__name__)


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
        Dict with 'price', 'currency', 'timestamp', 'ev_ebitda' or None if fetch fails.
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = ticker.info

        # Get current price - try multiple fields
        price = info.get('currentPrice') or info.get('regularMarketPrice')

        # Get EV/EBITDA ratio
        ev_ebitda = info.get('enterpriseToEbitda')

        if price:
            return {
                'price': Decimal(str(price)),
                'currency': info.get('currency', 'USD'),
                'timestamp': timezone.now(),
                'market_cap': info.get('marketCap'),
                'shares_outstanding': info.get('sharesOutstanding'),
                'ev_ebitda': Decimal(str(ev_ebitda)) if ev_ebitda else None,
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
