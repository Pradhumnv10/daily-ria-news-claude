"""
summarize_news.py — GPT-4o-mini article filter, categorizer, and summarizer.

Sends a single batched API call per 20 articles. Returns articles grouped into
four categories: acquisitions_ma, breakaway_advisors, funding_investment, ai_wealthtech.
"""

import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"acquisitions_ma", "breakaway_advisors", "funding_investment", "ai_wealthtech"}
BATCH_SIZE = 20

SYSTEM_PROMPT = """You are the editorial assistant for FastTrackr AI, a platform serving independent RIA firms and breakaway advisors.

Your job is to review news articles and:
1. FILTER: Keep only articles relevant to the US wealth management / RIA industry. Discard anything unrelated (e.g., general stock holdings announcements, unrelated M&A, international stories with no US wealth management angle).
2. CATEGORIZE: Assign each kept article to exactly one of these categories:
   - acquisitions_ma: RIA firm acquisitions, mergers, consolidations, or firm sales. Also includes PE-backed aggregator deals.
   - breakaway_advisors: Any advisor or team movement story — advisors leaving wirehouses/broker-dealers to go independent, wirehouse-to-wirehouse team moves, team recruiting announcements, and wirehouse retention/recruiting loan programs (these reveal the competitive dynamics independent advisors face).
   - funding_investment: VC/PE funding rounds, growth capital raises, or strategic investment in wealth management or wealthtech firms.
   - ai_wealthtech: ANY AI or technology news with a US wealth management angle — AI tools or platforms for financial advisors, new product launches by wealthtech companies (e.g. Orion, Envestnet, Riskalyze, Emotomy, YieldX, Salesforce Financial Services, etc.), AI regulation or SEC guidance on AI in advice, research on AI adoption in the advisory industry. Broad AI news (e.g. GPT updates, model releases) only if the article specifically discusses implications for US wealth management or financial advisors.
3. SUMMARIZE: Write a 2-3 sentence summary in active voice. End with why it matters for independent advisors or how it shifts the competitive landscape.

Return a JSON object with this exact structure:
{
  "articles": [
    {
      "title": "original article title",
      "url": "original article url",
      "source": "original source name",
      "published": "original published date",
      "category": "acquisitions_ma|breakaway_advisors|funding_investment|ai_wealthtech",
      "summary": "2-3 sentence summary ending with why it matters for independent advisors."
    }
  ]
}

Only include articles that are relevant. If none are relevant, return {"articles": []}.
Do not invent, hallucinate, or modify titles, URLs, sources, or dates."""


def _build_user_prompt(articles: list[dict]) -> str:
    lines = ["Review the following articles and process them per your instructions:\n"]
    for i, a in enumerate(articles, 1):
        lines.append(f"{i}. TITLE: {a['title']}")
        lines.append(f"   SOURCE: {a['source']}")
        lines.append(f"   DATE: {a['published']}")
        lines.append(f"   URL: {a['url']}")
        if a.get("description"):
            lines.append(f"   DESCRIPTION: {a['description'][:300]}")
        lines.append("")
    return "\n".join(lines)


def _parse_gpt_response(raw_json: str, original_articles: list[dict]) -> list[dict]:
    """
    Parse GPT JSON response. Validates category names.
    Returns list of valid article dicts.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        logger.error(f"GPT returned invalid JSON: {e}\nRaw response: {raw_json[:500]}")
        return []

    results = []
    for item in data.get("articles", []):
        # Validate required fields
        if not item.get("title") or not item.get("url"):
            continue

        # Filter out hallucinated categories
        category = item.get("category", "")
        if category not in VALID_CATEGORIES:
            logger.warning(f"Filtered out article with invalid category '{category}': {item.get('title', '')[:60]}")
            continue

        results.append({
            "title": item["title"],
            "url": item["url"],
            "source": item.get("source", ""),
            "published": item.get("published", ""),
            "category": category,
            "summary": item.get("summary", ""),
        })

    return results


def _call_gpt(client: OpenAI, articles: list[dict]) -> list[dict]:
    """Send one batch of articles to GPT-4o-mini."""
    user_prompt = _build_user_prompt(articles)

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=4000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content
        return _parse_gpt_response(raw, articles)

    except Exception as e:
        logger.error(f"GPT API call failed: {e}")
        return []


def summarize_and_categorize(articles: list[dict], openai_api_key: str) -> dict[str, list[dict]]:
    """
    Filter, categorize, and summarize articles using GPT-4o-mini.

    Args:
        articles: List of normalized article dicts from fetch_news.py
        openai_api_key: OpenAI API key

    Returns:
        Dict with keys: acquisitions_ma, breakaway_advisors, funding_investment
        Each value is a list of processed article dicts.
    """
    result = {cat: [] for cat in VALID_CATEGORIES}

    if not articles:
        logger.info("No articles to summarize — skipping GPT call.")
        return result

    client = OpenAI(api_key=openai_api_key)

    # Batch into groups of BATCH_SIZE
    all_processed = []
    for i in range(0, len(articles), BATCH_SIZE):
        batch = articles[i: i + BATCH_SIZE]
        logger.info(f"Sending GPT batch {i // BATCH_SIZE + 1}: {len(batch)} articles")
        processed = _call_gpt(client, batch)
        all_processed.extend(processed)

    # Group by category
    for article in all_processed:
        cat = article["category"]
        if cat in result:
            result[cat].append(article)

    total = sum(len(v) for v in result.values())
    logger.info(
        f"GPT output: {total} relevant articles — "
        f"{len(result['acquisitions_ma'])} M&A, "
        f"{len(result['breakaway_advisors'])} breakaway, "
        f"{len(result['funding_investment'])} funding, "
        f"{len(result['ai_wealthtech'])} AI/wealthtech"
    )

    return result


if __name__ == "__main__":
    import os
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from dotenv import load_dotenv
    load_dotenv()

    # Quick smoke test with dummy data
    dummy = [
        {
            "title": "Mercer Advisors Acquires $500M RIA in Denver",
            "url": "https://example.com/mercer-acquires",
            "source": "InvestmentNews",
            "published": "2026-02-23T10:00:00+00:00",
            "description": "Mercer Advisors announced the acquisition of a $500M AUM RIA firm based in Denver.",
            "content": "",
        },
        {
            "title": "Top Morgan Stanley Team Goes Independent with $1.2B",
            "url": "https://example.com/ms-breakaway",
            "source": "ThinkAdvisor",
            "published": "2026-02-23T08:00:00+00:00",
            "description": "A $1.2B AUM team departed Morgan Stanley to launch an independent RIA.",
            "content": "",
        },
    ]

    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        print("OPENAI_API_KEY not set — skipping live test")
    else:
        cats = summarize_and_categorize(dummy, key)
        for cat, arts in cats.items():
            print(f"\n{cat}: {len(arts)} articles")
            for a in arts:
                print(f"  - {a['title'][:70]}")
