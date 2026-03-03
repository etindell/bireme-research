"""
Prompt builder for Claude Code deep research tasks.

Generates a structured, step-by-step prompt that Claude Code can execute
using the browser (via Claude in Chrome extension) to gather company
research materials and load them into NotebookLM.
"""
from datetime import datetime


def build_research_prompt(company, profile, options=None):
    """
    Build the full Claude Code prompt for a deep research run.

    Args:
        company: Company model instance
        profile: ResearchProfile model instance
        options: dict with optional overrides:
            - years: how many years of filings (default 5)
            - skip_youtube: bool
            - skip_podcasts: bool
            - skip_notebooklm: bool
            - max_youtube_videos: int (default 20)

    Returns:
        str: The complete prompt text
    """
    options = options or {}
    years = options.get('years', 5)
    skip_youtube = options.get('skip_youtube', False)
    skip_podcasts = options.get('skip_podcasts', False)
    skip_notebooklm = options.get('skip_notebooklm', False)
    max_videos = options.get('max_youtube_videos', 20)

    ticker = company.get_primary_ticker()
    ticker_symbol = ticker.symbol if ticker else '[UNKNOWN TICKER]'

    executive_names = profile.get_executive_names()
    extra_terms = profile.get_extra_search_terms()

    sections = []

    # --- Header ---
    sections.append(_build_header(company, ticker_symbol, profile))

    # --- Step 1: Investor Relations ---
    sections.append(_build_ir_section(company, profile, ticker_symbol, years))

    # --- Step 2: SEC EDGAR ---
    sections.append(_build_sec_section(company, ticker_symbol, years))

    # --- Step 3: Earnings Transcripts ---
    sections.append(_build_transcripts_section(company, ticker_symbol, years))

    # --- Step 4: YouTube ---
    if not skip_youtube:
        sections.append(_build_youtube_section(
            company, ticker_symbol, executive_names, extra_terms, max_videos
        ))

    # --- Step 5: Podcasts ---
    if not skip_podcasts:
        sections.append(_build_podcast_section(company, executive_names, extra_terms))

    # --- Step 6: NotebookLM ---
    if not skip_notebooklm:
        sections.append(_build_notebooklm_section(company))

    # --- Final summary ---
    sections.append(_build_summary_section(company))

    return '\n\n'.join(sections)


def _build_header(company, ticker_symbol, profile):
    exec_names = profile.get_executive_names()
    exec_line = ', '.join(exec_names) if exec_names else 'Unknown — please look up'

    return f"""# DEEP RESEARCH TASK: {company.name} ({ticker_symbol})

**Date**: {datetime.now().strftime('%Y-%m-%d')}
**Company**: {company.name}
**Ticker**: {ticker_symbol}
**Sector**: {company.get_sector_display() if company.sector else 'N/A'}
**Website**: {company.website or 'N/A'}
**IR Page**: {profile.ir_url or 'Not known — find it in Step 1'}
**Key Executives**: {exec_line}

## OBJECTIVE

You are a research assistant for an investment fund. Your job is to gather
every important public document about {company.name} and organize them for
deep analysis. Work through each step below methodically. Download files to
the local folder structure, and at the end upload everything to NotebookLM.

## DOWNLOAD FOLDER STRUCTURE

Create this folder structure before starting:

```
{company.slug}/
├── filings/          # SEC filings (10-K, 10-Q, 8-K, proxy)
├── transcripts/      # Earnings call transcripts
├── presentations/    # Investor day, conference presentations
├── annual-reports/   # Annual reports / shareholder letters
├── other-ir/         # Other IR documents (factsheets, etc.)
├── youtube/          # YouTube video URLs and metadata
└── podcasts/         # Podcast episode URLs and metadata
```"""


def _build_ir_section(company, profile, ticker_symbol, years):
    ir_url = profile.ir_url

    if ir_url:
        find_ir = f'Go to the Investor Relations page: {ir_url}'
    else:
        find_ir = f"""First, find the Investor Relations page:
1. Search for "{company.name} investor relations"
2. Look for the official IR page (usually ir.{company.website or "companyname.com"} or a subdomain)
3. The IR page typically has sections like "SEC Filings", "Press Releases", "Events & Presentations"
4. If you find it, note the URL for future reference"""

    return f"""---

## STEP 1: INVESTOR RELATIONS WEBSITE

{find_ir}

Once on the IR site, systematically download the following from the last {years} years:

### A. Quarterly & Annual Financial Reports
- **Annual Reports** (10-K or glossy annual report PDFs) → save to `annual-reports/`
- **Quarterly Reports** (10-Q filings or quarterly result PDFs) → save to `filings/`
- **Shareholder Letters** (if separate from annual report) → save to `annual-reports/`
- Look for sections labeled: "SEC Filings", "Financial Reports", "Annual Reports", "Quarterly Results"

### B. Earnings Call Transcripts
- Download any earnings call transcripts available on the IR site → save to `transcripts/`
- These are often under "Events & Presentations" or "Quarterly Results"
- If transcripts are not on the IR site, we'll get them in Step 3

### C. Investor Presentations & Events
- **Investor Day presentations** (these are gold — download every one you find)
- **Conference presentations** (Goldman Sachs, JP Morgan, etc.)
- **Capital Markets Day decks**
- **Analyst Day materials**
- Save all to `presentations/`

### D. Other Useful IR Documents
- **Fact sheets** or **company overviews**
- **ESG/sustainability reports** (if relevant to the investment thesis)
- **Proxy statements** (DEF 14A — shows executive compensation)
- Save to `other-ir/`

### TIPS FOR IR SITE NAVIGATION
- Many IR sites use tabs or dropdowns — check all sections
- Look for an "Archive" or "Past Events" section for older materials
- Some sites require you to select a year/quarter filter
- PDFs are preferred; if only HTML is available, save/print as PDF
- If a document requires email registration, skip it"""


def _build_sec_section(company, ticker_symbol, years):
    return f"""---

## STEP 2: SEC EDGAR FILINGS

Go to SEC EDGAR and search for {company.name} (ticker: {ticker_symbol}).

**URL**: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker_symbol}&type=&dateb=&owner=include&count=40&search_text=&action=getcompany

Or search at: https://efts.sec.gov/LATEST/search-index?q=%22{ticker_symbol}%22&dateRange=custom&startdt={datetime.now().year - years}-01-01

Download these filing types from the last {years} years → save to `filings/`:

| Filing Type | What It Is | Priority |
|-------------|-----------|----------|
| **10-K** | Annual report (full financials + MD&A) | MUST HAVE |
| **10-Q** | Quarterly report | MUST HAVE |
| **8-K** | Material events (acquisitions, leadership changes) | HIGH — skim titles, download important ones |
| **DEF 14A** | Proxy statement (exec comp, governance) | NICE TO HAVE — get the most recent one |
| **S-1** | IPO prospectus (if company IPO'd in last {years} years) | HIGH if available |

### HOW TO DOWNLOAD FROM EDGAR
1. Find the filing in the index
2. Click into the filing detail page
3. Look for the main document (usually the first .htm or .pdf link)
4. Download the full document, not just the index page
5. Name files descriptively: `10-K_2024.pdf`, `10-Q_2024-Q3.pdf`, `8-K_2024-03-15_acquisition.pdf`

### SKIP
- XBRL viewer pages (these are just formatted versions of the same data)
- Exhibits unless they look particularly interesting (e.g., material contracts)
- Amendments (10-K/A) unless the original is not available"""


def _build_transcripts_section(company, ticker_symbol, years):
    return f"""---

## STEP 3: EARNINGS CALL TRANSCRIPTS

If you didn't find transcripts on the IR site in Step 1, search for them now.

### Sources to Try (in order of preference)
1. **The company's IR site** (already checked in Step 1)
2. **Seeking Alpha**: Search for "{company.name} earnings call transcript"
   - URL pattern: seekingalpha.com/symbol/{ticker_symbol}/earnings/transcripts
   - Note: may require login for full text — grab what you can
3. **The Motley Fool**: Search for "{company.name} earnings transcript"
4. **Google search**: "{company.name} Q[1-4] {datetime.now().year} earnings call transcript"

### What to Get
- All quarterly earnings call transcripts from the last {years} years
- Any special calls (guidance updates, pre-announcements, strategic reviews)
- Save to `transcripts/` with names like: `{ticker_symbol}_Q3_2024_earnings_transcript.pdf`

### TIPS
- If full transcripts aren't freely available, at minimum get the **prepared remarks**
  (the scripted portion at the beginning of the call)
- Management commentary > Q&A section if you have to choose
- If you can only get summaries rather than full transcripts, those are still valuable"""


def _build_youtube_section(company, ticker_symbol, exec_names, extra_terms, max_videos):
    search_queries = [
        f'"{company.name}" CEO interview',
        f'"{company.name}" investor day',
        f'"{company.name}" earnings call',
        f'"{company.name}" conference presentation',
    ]

    for name in exec_names:
        search_queries.append(f'"{name}" interview')
        search_queries.append(f'"{name}" {company.name}')

    for term in extra_terms:
        search_queries.append(f'"{company.name}" {term}')

    seen = set()
    unique_queries = []
    for q in search_queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            unique_queries.append(q)

    queries_formatted = '\n'.join(f'   - `{q}`' for q in unique_queries)

    return f"""---

## STEP 4: YOUTUBE VIDEOS

Search YouTube for interviews, presentations, and discussions about {company.name}.

### Search Queries (run each one)
{queries_formatted}

### For Each Search
1. Sort by **relevance** first, then check **upload date** to prioritize recent
2. Look for videos from reputable channels:
   - Financial media: CNBC, Bloomberg, Yahoo Finance, WSJ
   - Investment conferences: Goldman Sachs, Morgan Stanley, Bernstein
   - Industry conferences: CES, SXSW, sector-specific events
   - The company's own YouTube channel
   - Quality independent analysts (channels with 10K+ subscribers)
3. Skip: random stock tip videos, AI-generated content, clickbait

### What to Save
For each relevant video, create a line in `youtube/video_list.txt`:
```
Title: [Video Title]
URL: [YouTube URL]
Channel: [Channel Name]
Date: [Upload Date]
Duration: [Length]
Why relevant: [1-sentence description]
```

**IMPORTANT**: NotebookLM can ingest YouTube URLs directly as sources.
So just collecting the URLs is sufficient — no need to download the actual videos.

### Target
Aim for {max_videos} high-quality videos maximum. Quality over quantity —
an hour-long CEO interview at a Goldman conference is worth 10 short news clips."""


def _build_podcast_section(company, exec_names, extra_terms):
    search_terms = [company.name]
    search_terms.extend(exec_names)
    search_terms.extend(extra_terms)
    terms_formatted = ', '.join(f'"{t}"' for t in search_terms if t)

    return f"""---

## STEP 5: PODCASTS & AUDIO INTERVIEWS

Search for podcast episodes featuring {company.name} or its executives.

### Search Terms
{terms_formatted}

### Where to Search
1. **Google**: `"{company.name}" podcast episode` or `"{company.name}" interview podcast`
2. **Spotify** (via web): Open spotify.com, search for the company name in podcasts
3. **Apple Podcasts** (via web): Search at podcasts.apple.com
4. **Google Podcasts / YouTube**: Many podcasts are also on YouTube (covered in Step 4)

### Quality Signals (prioritize these)
- Invest Like the Best, Acquired, The Investors Podcast
- Bloomberg Odd Lots, FT Alphachat, Goldman Sachs Exchanges
- Industry-specific podcasts relevant to {company.name}'s sector
- Any podcast where the CEO/CFO is a guest

### What to Save
Create `podcasts/podcast_list.txt` with entries:
```
Title: [Episode Title]
Show: [Podcast Name]
URL: [Episode URL]
Date: [Publish Date]
Duration: [Length]
Why relevant: [1-sentence description]
```

### NOTE
NotebookLM can ingest audio files and YouTube URLs.
If a podcast episode is on YouTube, the YouTube URL is the best format.
Otherwise, note the URL for manual addition later."""


def _build_notebooklm_section(company):
    return f"""---

## STEP 6: UPLOAD TO GOOGLE NOTEBOOKLM

Now that all materials are gathered, create a NotebookLM notebook and load everything in.

### Steps
1. Open **https://notebooklm.google.com** in the browser
2. Click **"New Notebook"** (or "+ New" button)
3. Name the notebook: **"{company.name} Deep Research"**

### Add Sources (in this order)

**A. Upload PDF Documents**
- Click "Add source" → "Upload" (or the "+" icon on the sources panel)
- Upload all PDFs from the download folders:
  - `filings/` — 10-Ks, 10-Qs, 8-Ks
  - `transcripts/` — earnings call transcripts
  - `presentations/` — investor day decks, conference presentations
  - `annual-reports/` — annual reports, shareholder letters
  - `other-ir/` — proxy statements, fact sheets
- NotebookLM has a limit of ~50 sources per notebook and ~500K words per source
- **Prioritize**: 10-Ks > transcripts > presentations > 10-Qs > 8-Ks

**B. Add YouTube URLs**
- Click "Add source" → "YouTube"
- Paste each YouTube URL from `youtube/video_list.txt`
- NotebookLM will automatically transcribe the audio
- Prioritize long-form interviews and investor day presentations

**C. Add Website URLs** (optional bonus)
- Click "Add source" → "Website"
- Add the company's IR page URL
- Add any particularly good analysis or overview pages you found

### IMPORTANT NOTES
- If you hit the 50-source limit, prioritize:
  1. Most recent 10-K (annual report)
  2. Last 4 quarterly transcripts
  3. Investor day presentation(s)
  4. CEO interviews (YouTube)
  5. Remaining 10-Ks (older years)
  6. Remaining transcripts
  7. 8-Ks and other documents
- Wait for each upload to finish processing before adding the next
- Some large PDFs may take 30-60 seconds to process

### When Complete
- Note the NotebookLM notebook URL
- Report it back along with a count of what was uploaded"""


def _build_summary_section(company):
    return f"""---

## FINAL REPORT

When you're done, provide a summary in this format:

```
## Deep Research Complete: {company.name}

### Documents Downloaded
- Annual Reports: [count]
- 10-K Filings: [count]
- 10-Q Filings: [count]
- 8-K Filings: [count]
- Earnings Transcripts: [count]
- Presentations: [count]
- Other IR Documents: [count]

### Media Found
- YouTube Videos: [count]
- Podcast Episodes: [count]

### NotebookLM
- Notebook URL: [URL]
- Sources Uploaded: [count]
- Any sources that couldn't be uploaded: [list]

### Notes
- [Anything notable — missing years, paywalled content, unusual findings]
- [IR site observations — how well-organized, any broken links]
- [Key documents that seem particularly important for the thesis]
```

### TIPS FOR THE ENTIRE TASK
- Work methodically through each step — don't skip ahead
- If a particular source is paywalled or unavailable, note it and move on
- Prefer PDFs over HTML when both are available
- Name files descriptively so they're easy to identify later
- If you encounter CAPTCHAs or bot detection, note it and try an alternative approach
- The goal is comprehensiveness — it's better to download too much than too little"""


def build_config_snapshot(profile):
    """Create a JSON-serializable snapshot of the research profile."""
    return {
        'ir_url': profile.ir_url,
        'ceo_name': profile.ceo_name,
        'cfo_name': profile.cfo_name,
        'other_executives': profile.other_executives,
        'extra_search_terms': profile.extra_search_terms,
        'exclude_domains': profile.exclude_domains,
    }
