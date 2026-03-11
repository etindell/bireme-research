import hashlib
import re
from datetime import datetime

import feedparser

SEC_FEEDS = {
    'sec_press': {
        'url': 'https://www.sec.gov/news/pressreleases.rss',
        'name': 'SEC Press Releases',
    },
    'sec_speeches': {
        'url': 'https://www.sec.gov/news/speeches.rss',
        'name': 'SEC Speeches',
    },
}

RIA_HEDGE_FUND_KEYWORDS = [
    'investment adviser', 'investment advisor', 'registered investment',
    'adviser act', 'advisers act', 'form adv', 'form pf', 'hedge fund',
    'private fund', 'private equity', 'fiduciary', 'custody rule',
    'code of ethics', 'compliance program', 'chief compliance', 'form 13f',
    'investment management', 'fund manager', 'asset manager',
    'portfolio manager', 'marketing rule', 'advertising rule',
    'assets under management', 'form crs', 'mutual fund',
]

_KEYWORD_PATTERNS = [re.compile(kw, re.IGNORECASE) for kw in RIA_HEDGE_FUND_KEYWORDS]


def is_ria_relevant(title, description):
    text = f'{title} {description}'
    return any(p.search(text) for p in _KEYWORD_PATTERNS)


def parse_date(date_str):
    if not date_str:
        return datetime.utcnow()
    formats = [
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S %Z',
        '%Y-%m-%dT%H:%M:%S%z',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return datetime.utcnow()


def generate_guid(entry, source):
    if entry.get('id'):
        return entry['id']
    if entry.get('link'):
        return entry['link']
    content = f"{source}:{entry.get('title', '')}:{entry.get('published', '')}"
    return hashlib.md5(content.encode()).hexdigest()


def fetch_all_feeds(filter_relevant=True):
    """Fetch all SEC feeds, return list of dicts sorted by published_at desc."""
    all_items = []
    for feed_key, feed_info in SEC_FEEDS.items():
        try:
            feed = feedparser.parse(feed_info['url'])
            if hasattr(feed, 'status') and feed.status >= 400:
                continue
            for entry in feed.entries:
                title = entry.get('title', 'No title')
                description = entry.get('summary', entry.get('description', ''))
                relevant = is_ria_relevant(title, description)
                if filter_relevant and not relevant:
                    continue
                all_items.append({
                    'guid': generate_guid(entry, feed_key),
                    'title': title,
                    'link': entry.get('link', ''),
                    'description': description,
                    'published_at': parse_date(entry.get('published', '')),
                    'source': feed_info['name'],
                    'is_relevant': relevant,
                })
        except Exception:
            continue
    all_items.sort(key=lambda x: x['published_at'], reverse=True)
    return all_items
