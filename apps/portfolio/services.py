"""
Services for portfolio extraction, matching, and analytics.
"""
import json
import logging
import os
from decimal import Decimal

import numpy as np

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are analyzing a portfolio report document. Extract ALL long equity positions.

For each position, return:
- ticker: the stock ticker symbol (e.g., "AAPL", "MSFT")
- name: the company name as shown
- weight: the portfolio weight as a decimal (e.g., 8.5% -> 0.085)

Rules:
- ONLY include long equity positions (skip cash, hedges, short positions, options, fixed income)
- Weights should be decimals that sum to approximately 1.0 (or less if cash is excluded)
- If you can't determine the ticker, use your best guess based on the company name
- If weights are shown as percentages, convert to decimals

Respond with ONLY a JSON array, no other text:
[{"ticker": "AAPL", "name": "Apple Inc.", "weight": 0.085}, ...]
"""


def extract_portfolio_from_file(file_path: str) -> list[dict]:
    """
    Send uploaded PDF/image to Gemini with vision capabilities.
    Returns list of dicts: [{"ticker": "AAPL", "name": "Apple Inc.", "weight": 0.085}, ...]
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.error("google-genai package not installed")
        return []

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        logger.error("GEMINI_API_KEY environment variable not set")
        return []

    with open(file_path, 'rb') as f:
        file_bytes = f.read()

    if file_path.lower().endswith('.pdf'):
        mime_type = 'application/pdf'
    elif file_path.lower().endswith('.png'):
        mime_type = 'image/png'
    elif file_path.lower().endswith(('.jpg', '.jpeg')):
        mime_type = 'image/jpeg'
    else:
        mime_type = 'application/octet-stream'

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-preview",
            contents=[
                types.Content(parts=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    types.Part.from_text(text=EXTRACTION_PROMPT),
                ])
            ],
        )

        response_text = response.text
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']') + 1
        if start_idx == -1 or end_idx == 0:
            logger.error("No JSON array found in Gemini response")
            return []

        positions = json.loads(response_text[start_idx:end_idx])
        logger.info(f"Extracted {len(positions)} positions from portfolio file")
        return positions

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Gemini response: {e}")
        return []
    except Exception as e:
        logger.error(f"Gemini extraction error: {e}")
        return []


def match_positions_to_companies(positions: list[dict], organization) -> list[dict]:
    """
    For each extracted position, try to match to an existing Company.
    Match by ticker symbol first, then fuzzy name match.
    Populate IRR from active CompanyValuation.
    """
    from apps.companies.models import Company, CompanyTicker

    org_tickers = CompanyTicker.objects.filter(
        company__organization=organization,
        company__is_deleted=False,
    ).select_related('company')

    ticker_map = {}
    for ct in org_tickers:
        ticker_map[ct.symbol.upper()] = ct.company

    for pos in positions:
        ticker = pos.get('ticker', '').upper()
        company = ticker_map.get(ticker)

        if not company:
            # Try fuzzy name match
            name = pos.get('name', '').lower()
            if name:
                try:
                    company = Company.objects.filter(
                        organization=organization,
                        name__icontains=name.split()[0] if name.split() else name,
                    ).first()
                except Exception:
                    pass

        pos['company'] = company
        pos['irr'] = None
        pos['irr_source'] = 'valuation'

        if company:
            active_val = company.valuations.filter(is_active=True, is_deleted=False).first()
            if active_val and active_val.calculated_irr is not None:
                pos['irr'] = float(active_val.calculated_irr)

    return positions


def calculate_portfolio_irr(positions) -> float | None:
    """
    Weighted average IRR across positions that have IRR values.
    positions: queryset or list of PortfolioPosition objects.
    """
    total_weight = Decimal('0')
    weighted_irr = Decimal('0')

    for pos in positions:
        if pos.irr is not None:
            weight = pos.proposed_weight if pos.proposed_weight is not None else pos.current_weight
            weighted_irr += weight * pos.irr
            total_weight += weight

    if total_weight == 0:
        return None

    return float(weighted_irr / total_weight)


def calculate_portfolio_irr_from_weights(positions, use_proposed=False) -> float | None:
    """
    Calculate portfolio IRR using either current or proposed weights.
    """
    total_weight = Decimal('0')
    weighted_irr = Decimal('0')

    for pos in positions:
        if pos.irr is not None:
            weight = pos.proposed_weight if (use_proposed and pos.proposed_weight is not None) else pos.current_weight
            weighted_irr += weight * pos.irr
            total_weight += weight

    if total_weight == 0:
        return None

    return float(weighted_irr / total_weight)


def estimate_portfolio_volatility(positions, lookback_days=252) -> dict:
    """
    Use yfinance to fetch historical daily returns for each ticker.
    Returns portfolio volatility, individual vols, correlation matrix, etc.
    """
    import yfinance as yf

    tickers = []
    weights = []
    ticker_to_idx = {}

    for pos in positions:
        t = pos.ticker.upper()
        w = float(pos.proposed_weight if pos.proposed_weight is not None else pos.current_weight)
        if w > 0:
            tickers.append(t)
            weights.append(w)
            ticker_to_idx[t] = len(tickers) - 1

    if not tickers:
        return {
            'portfolio_volatility': None,
            'individual_volatilities': {},
            'correlation_matrix': [],
            'diversification_ratio': None,
            'tickers_missing_data': [],
            'tickers': [],
        }

    # Normalize weights
    w_arr = np.array(weights)
    w_arr = w_arr / w_arr.sum()

    # Fetch price data
    try:
        data = yf.download(tickers, period="1y", progress=False, auto_adjust=True)
        if data.empty:
            return {
                'portfolio_volatility': None,
                'individual_volatilities': {},
                'correlation_matrix': [],
                'diversification_ratio': None,
                'tickers_missing_data': tickers,
                'tickers': tickers,
            }
    except Exception as e:
        logger.error(f"yfinance download error: {e}")
        return {
            'portfolio_volatility': None,
            'individual_volatilities': {},
            'correlation_matrix': [],
            'diversification_ratio': None,
            'tickers_missing_data': tickers,
            'tickers': tickers,
        }

    # Get close prices
    if len(tickers) == 1:
        import pandas as pd
        close = pd.DataFrame(data['Close'])
        close.columns = tickers
    else:
        close = data['Close']

    # Drop tickers with no data
    missing = []
    available_tickers = []
    available_weights = []
    for i, t in enumerate(tickers):
        if t in close.columns and close[t].dropna().shape[0] > 20:
            available_tickers.append(t)
            available_weights.append(weights[i])
        else:
            missing.append(t)

    if not available_tickers:
        return {
            'portfolio_volatility': None,
            'individual_volatilities': {},
            'correlation_matrix': [],
            'diversification_ratio': None,
            'tickers_missing_data': missing,
            'tickers': tickers,
        }

    close = close[available_tickers].dropna()
    aw = np.array(available_weights)
    aw = aw / aw.sum()

    # Daily log returns
    returns = np.log(close / close.shift(1)).dropna()

    # Covariance matrix (annualized)
    cov_matrix = returns.cov().values * 252

    # Individual volatilities (annualized)
    individual_vols = {}
    for i, t in enumerate(available_tickers):
        individual_vols[t] = float(np.sqrt(cov_matrix[i][i]))

    # Portfolio variance and volatility
    port_variance = float(aw @ cov_matrix @ aw)
    port_vol = float(np.sqrt(port_variance))

    # Correlation matrix
    corr_matrix = returns.corr().values.tolist()

    # Diversification ratio
    weighted_avg_vol = float(sum(aw[i] * individual_vols[t] for i, t in enumerate(available_tickers)))
    div_ratio = weighted_avg_vol / port_vol if port_vol > 0 else None

    return {
        'portfolio_volatility': port_vol,
        'individual_volatilities': individual_vols,
        'correlation_matrix': corr_matrix,
        'diversification_ratio': div_ratio,
        'tickers_missing_data': missing,
        'tickers': available_tickers,
    }
