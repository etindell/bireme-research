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


class ExtractionError:
    """Structured error from portfolio extraction."""
    # Error codes
    MISSING_PACKAGE = 'missing_package'
    MISSING_API_KEY = 'missing_api_key'
    FILE_READ_ERROR = 'file_read_error'
    UNSUPPORTED_FORMAT = 'unsupported_format'
    API_ERROR = 'api_error'
    BLOCKED_RESPONSE = 'blocked_response'
    EMPTY_RESPONSE = 'empty_response'
    NO_JSON = 'no_json'
    INVALID_JSON = 'invalid_json'
    NO_POSITIONS = 'no_positions'

    MESSAGES = {
        MISSING_PACKAGE: 'The google-genai package is not installed. Run: pip install google-genai',
        MISSING_API_KEY: 'GEMINI_API_KEY environment variable is not set. Add it to your .env file.',
        FILE_READ_ERROR: 'Could not read the uploaded file.',
        UNSUPPORTED_FORMAT: 'Unsupported file format. Upload a PDF, PNG, or JPG.',
        API_ERROR: 'Gemini API call failed.',
        BLOCKED_RESPONSE: 'Gemini blocked the response (safety filter). Try a different file or crop sensitive info.',
        EMPTY_RESPONSE: 'Gemini returned an empty response. The file may not contain readable portfolio data.',
        NO_JSON: 'Gemini did not return extractable position data. The file may not look like a portfolio report.',
        INVALID_JSON: 'Gemini returned malformed data that could not be parsed.',
        NO_POSITIONS: 'Gemini processed the file but found zero positions. Check that the file shows long equity weightings.',
    }

    def __init__(self, code, detail=''):
        self.code = code
        self.message = self.MESSAGES.get(code, 'Unknown extraction error.')
        self.detail = detail

    def __str__(self):
        if self.detail:
            return f'{self.message} ({self.detail})'
        return self.message


def extract_portfolio_from_file(file_path: str) -> tuple[list[dict], ExtractionError | None]:
    """
    Send uploaded PDF/image to Gemini with vision capabilities.
    Returns (positions, error). On success error is None; on failure positions is [].
    """
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return [], ExtractionError(ExtractionError.MISSING_PACKAGE)

    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return [], ExtractionError(ExtractionError.MISSING_API_KEY)

    # Determine MIME type
    lower_path = file_path.lower()
    MIME_MAP = {
        '.pdf': 'application/pdf',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
    }
    mime_type = None
    for ext, mt in MIME_MAP.items():
        if lower_path.endswith(ext):
            mime_type = mt
            break
    if not mime_type:
        return [], ExtractionError(ExtractionError.UNSUPPORTED_FORMAT, f'File: {os.path.basename(file_path)}')

    # Read file
    try:
        with open(file_path, 'rb') as f:
            file_bytes = f.read()
        if not file_bytes:
            return [], ExtractionError(ExtractionError.FILE_READ_ERROR, 'File is empty')
    except OSError as e:
        return [], ExtractionError(ExtractionError.FILE_READ_ERROR, str(e))

    logger.info(f"Sending {len(file_bytes)} bytes ({mime_type}) to Gemini for extraction")

    # Call Gemini
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                EXTRACTION_PROMPT,
            ],
        )
    except Exception as e:
        error_str = str(e)
        logger.error(f"Gemini API error: {error_str}")
        return [], ExtractionError(ExtractionError.API_ERROR, error_str)

    # Check for blocked / empty response
    try:
        response_text = response.text
    except (ValueError, AttributeError) as e:
        logger.error(f"Gemini response has no text: {e}")
        # Check if blocked by safety
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'finish_reason') and 'SAFETY' in str(candidate.finish_reason).upper():
                return [], ExtractionError(ExtractionError.BLOCKED_RESPONSE)
        return [], ExtractionError(ExtractionError.EMPTY_RESPONSE, str(e))

    if not response_text or not response_text.strip():
        logger.error("Gemini returned empty text")
        return [], ExtractionError(ExtractionError.EMPTY_RESPONSE)

    logger.info(f"Gemini response ({len(response_text)} chars): {response_text[:200]}...")

    # Parse JSON
    start_idx = response_text.find('[')
    end_idx = response_text.rfind(']') + 1
    if start_idx == -1 or end_idx == 0:
        logger.error(f"No JSON array in response: {response_text[:500]}")
        return [], ExtractionError(ExtractionError.NO_JSON, f'Response preview: {response_text[:200]}')

    try:
        positions = json.loads(response_text[start_idx:end_idx])
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error: {e}. Raw: {response_text[start_idx:end_idx][:500]}")
        return [], ExtractionError(ExtractionError.INVALID_JSON, str(e))

    if not positions:
        return [], ExtractionError(ExtractionError.NO_POSITIONS)

    logger.info(f"Extracted {len(positions)} positions from portfolio file")
    return positions, None


def match_positions_to_companies(positions: list[dict], organization) -> list[dict]:
    """
    For each extracted position, try to match to an existing Company.
    Matching strategy (in order):
      1. Exact ticker match
      2. Base ticker match — strip exchange suffixes (.L, .TO, .DE, etc.)
         from both sides and compare
      3. Fuzzy name match — search company names using extracted name
    Populate IRR from active CompanyValuation.

    Note: calculated_irr is already stored as a percentage (e.g. 15.0 = 15%),
    NOT as a decimal. We store it as-is in PortfolioPosition.irr.
    """
    from apps.companies.models import Company, CompanyTicker

    org_tickers = CompanyTicker.objects.filter(
        company__organization=organization,
        company__is_deleted=False,
    ).select_related('company')

    # Build lookup maps
    exact_map = {}       # "AAF.L" -> company
    base_map = {}        # "AAF" -> company (stripped of exchange suffix)
    for ct in org_tickers:
        sym = ct.symbol.upper()
        exact_map[sym] = ct.company
        base = _strip_exchange_suffix(sym)
        # Don't overwrite if a more specific ticker already claimed this base
        if base not in base_map:
            base_map[base] = ct.company

    for pos in positions:
        ticker = pos.get('ticker', '').upper()
        extracted_base = _strip_exchange_suffix(ticker)

        # 1. Exact match
        company = exact_map.get(ticker)

        # 2. Base ticker match (handles non-USD tickers)
        if not company:
            company = base_map.get(extracted_base)

        # 3. Fuzzy name match
        if not company:
            name = pos.get('name', '').strip()
            if name:
                company = _fuzzy_name_match(name, organization)

        pos['company'] = company
        pos['irr'] = None
        pos['irr_source'] = 'valuation'

        if company:
            active_val = company.valuations.filter(is_active=True, is_deleted=False).first()
            if active_val and active_val.calculated_irr is not None:
                # calculated_irr is already a percentage (15.0 = 15%)
                pos['irr'] = float(active_val.calculated_irr)

    return positions


def _strip_exchange_suffix(ticker: str) -> str:
    """Strip exchange suffix from ticker: 'AAF.L' -> 'AAF', 'RIO.AX' -> 'RIO'."""
    return ticker.split('.')[0] if '.' in ticker else ticker


def _fuzzy_name_match(name: str, organization):
    """Try to match an extracted company name to a Company in the database."""
    from apps.companies.models import Company

    # Try full name first
    match = Company.objects.filter(
        organization=organization, is_deleted=False,
        name__iexact=name,
    ).first()
    if match:
        return match

    # Try contains with full name
    match = Company.objects.filter(
        organization=organization, is_deleted=False,
        name__icontains=name,
    ).first()
    if match:
        return match

    # Try significant words (skip common suffixes like Inc, Ltd, Corp, PLC, etc.)
    skip = {'inc', 'ltd', 'llc', 'corp', 'plc', 'co', 'group', 'holdings',
            'limited', 'corporation', 'the', 'and', '&', 'sa', 'se', 'nv', 'ag'}
    words = [w for w in name.split() if w.lower().rstrip('.,') not in skip]
    if words:
        query = ' '.join(words[:3])
        match = Company.objects.filter(
            organization=organization, is_deleted=False,
            name__icontains=query,
        ).first()
        if match:
            return match

        # Try just the first significant word
        match = Company.objects.filter(
            organization=organization, is_deleted=False,
            name__icontains=words[0],
        ).first()
        if match:
            return match

    return None


def calculate_portfolio_irr_from_weights(positions, use_proposed=False) -> float | None:
    """
    Portfolio IRR relative to 100% NAV.
    portfolio_irr = sum(weight_i * irr_i) for positions with IRR.
    Unallocated weight (cash) implicitly contributes 0% IRR.
    """
    has_any = False
    weighted_irr = Decimal('0')

    for pos in positions:
        if pos.irr is not None:
            weight = pos.proposed_weight if (use_proposed and pos.proposed_weight is not None) else pos.current_weight
            weighted_irr += weight * pos.irr
            has_any = True

    if not has_any:
        return None

    return float(weighted_irr)


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
