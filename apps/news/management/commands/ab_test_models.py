"""
A/B Test: Compare Claude models for news filtering.
Usage: python manage.py ab_test_models
"""
import json
import os

import anthropic
import requests
from django.core.management.base import BaseCommand

from apps.companies.models import Company


class Command(BaseCommand):
    help = 'A/B test comparing Claude models for news filtering'

    def handle(self, *args, **options):
        self.stdout.write("=" * 80)
        self.stdout.write("NEWS FILTERING A/B TEST: Haiku 3 vs Sonnet 4 vs Opus 4")
        self.stdout.write("=" * 80)

        # Get portfolio companies
        companies = Company.objects.filter(
            status__in=['long_book', 'short_book'],
            is_deleted=False
        ).distinct('name')[:18]

        # Step 1: Gather news from Tavily
        self.stdout.write("\n[1/2] Fetching news from Tavily...")
        all_news = []
        for company in companies:
            ticker = company.tickers.first()
            ticker_symbol = ticker.symbol if ticker else 'N/A'
            self.stdout.write(f"  {company.name} ({ticker_symbol})")

            results = self.search_tavily(company.name, ticker_symbol)
            all_news.extend(results)
            self.stdout.write(f"    -> {len(results)} articles")

        self.stdout.write(f"\nTotal raw articles: {len(all_news)}")

        # Step 2: Run each model
        self.stdout.write("\n[2/2] Running models...")

        models = {
            "Haiku 3 ($0.25/M)": "claude-3-haiku-20240307",
            "Sonnet 4 ($3/M)": "claude-sonnet-4-20250514",
            "Opus 4 ($15/M)": "claude-opus-4-20250514",
        }

        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        results = {}

        for model_name, model_id in models.items():
            self.stdout.write(f"\n  Running {model_name}...")
            try:
                results[model_name] = self.run_model(client, model_id, all_news)
                self.stdout.write(self.style.SUCCESS(f"    Selected {len(results[model_name])} stories"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    Error: {e}"))
                results[model_name] = []

        # Step 3: Display results
        self.display_results(results)

    def search_tavily(self, company_name, ticker):
        """Search Tavily for company news."""
        api_key = os.environ.get('TAVILY_API_KEY')
        query = f'"{company_name}" OR "{ticker}"'

        exclude_domains = [
            'finance.yahoo.com', 'stockanalysis.com', 'tradingview.com',
            'morningstar.com', 'google.com/finance', 'zacks.com', 'tipranks.com',
        ]

        try:
            response = requests.post(
                'https://api.tavily.com/search',
                json={
                    'api_key': api_key,
                    'query': query,
                    'topic': 'news',
                    'search_depth': 'basic',
                    'max_results': 5,
                    'days': 3,
                    'exclude_domains': exclude_domains,
                },
                timeout=30
            )
            response.raise_for_status()
            data = response.json()

            return [{
                'company': company_name,
                'ticker': ticker,
                'url': item.get('url', ''),
                'title': item.get('title', ''),
                'content': item.get('content', '')[:300],
            } for item in data.get('results', [])]
        except Exception as e:
            return []

    def run_model(self, client, model_id, all_news):
        """Run a model to filter news."""
        news_text = ""
        for i, item in enumerate(all_news, 1):
            news_text += f"""
---
Item {i}:
Company: {item['company']} ({item['ticker']})
URL: {item['url']}
Title: {item['title']}
Content: {item['content']}
---
"""

        prompt = f"""You are analyzing news for a portfolio of stocks. Select the TOP 10 MOST IMPORTANT news stories.

RULES:
- Select exactly 10 stories (or fewer if there aren't 10 important ones)
- Maximum 2 stories per company
- Only include truly material news: earnings, M&A, major contracts, executive changes, regulatory actions
- Ignore stock price pages, company profiles, minor analyst mentions

For each story, provide:
1. The company name and ticker
2. The headline
3. ONE sentence explaining why this news is important for investors

Return a JSON array:
[
  {{
    "company": "Company Name",
    "ticker": "TICKER",
    "headline": "The headline",
    "url": "the url",
    "why_important": "One sentence explanation"
  }}
]

NEWS ITEMS:
{news_text}
"""

        message = client.messages.create(
            model=model_id,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text
        start_idx = response_text.find('[')
        end_idx = response_text.rfind(']') + 1

        if start_idx != -1 and end_idx > 0:
            return json.loads(response_text[start_idx:end_idx])
        return []

    def display_results(self, results):
        """Display the comparison results."""
        # First show each model's picks separately
        for model_name, stories in results.items():
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(f"{model_name} - TOP 10 PICKS")
            self.stdout.write("=" * 80)

            if not stories:
                self.stdout.write("  (No stories selected or model error)")
                continue

            for i, story in enumerate(stories, 1):
                self.stdout.write(f"\n  {i}. {story.get('company', '?')} ({story.get('ticker', '')})")
                self.stdout.write(f"     {story.get('headline', 'N/A')}")
                self.stdout.write(f"     Why: {story.get('why_important', 'N/A')}")

        # Then show consensus analysis
        all_stories = {}
        for model_name, stories in results.items():
            for story in stories:
                url = story.get('url', '')
                if url not in all_stories:
                    all_stories[url] = {'data': story, 'models': []}
                all_stories[url]['models'].append(model_name)

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("AGREEMENT ANALYSIS")
        self.stdout.write("=" * 80)

        consensus_3 = [s for s in all_stories.values() if len(s['models']) == 3]
        consensus_2 = [s for s in all_stories.values() if len(s['models']) == 2]

        if consensus_3:
            self.stdout.write(f"\nAll 3 models agreed on ({len(consensus_3)}):")
            for s in consensus_3:
                self.stdout.write(f"  - {s['data'].get('headline', 'N/A')}")

        if consensus_2:
            self.stdout.write(f"\n2 models agreed on ({len(consensus_2)}):")
            for s in consensus_2:
                self.stdout.write(f"  - {s['data'].get('headline', 'N/A')} [{' & '.join(s['models'])}]")
