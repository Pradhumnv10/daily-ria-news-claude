"""
main.py — Orchestrator for the Daily RIA News Digest.

Execution sequence:
  1. Load and validate environment variables
  2. Fetch articles (NewsData.io + RSS)
  3. Summarize and categorize with GPT-4o-mini
  4. Render HTML email
  5. Send via Gmail SMTP

Exit codes:
  0 — Success (even if "no news today")
  1 — Fatal error (missing env vars, SMTP failure, unhandled exception)
"""

import os
import sys
import logging

# Ensure tools/ is on the path regardless of where this script is invoked from
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Env config
# ---------------------------------------------------------------------------

REQUIRED_VARS = [
    "OPENAI_API_KEY",
    "GMAIL_USER",
    "GMAIL_APP_PASSWORD",
    "EMAIL_RECIPIENTS",
]

OPTIONAL_VARS = [
    "NEWSDATA_API_KEY",  # Optional — graceful RSS-only fallback if missing
]


def load_env_config() -> dict:
    """
    Load .env and validate required variables.

    Returns:
        Dict of all config values.

    Raises:
        SystemExit(1) if any required variable is missing.
    """
    load_dotenv()

    config = {}
    missing = []

    for var in REQUIRED_VARS:
        val = os.getenv(var, "").strip()
        if not val:
            missing.append(var)
        config[var] = val

    if missing:
        logger.error(f"Missing required environment variables: {', '.join(missing)}")
        logger.error("Copy .env.example to .env and fill in all values.")
        sys.exit(1)

    # Optional vars (no error if missing)
    for var in OPTIONAL_VARS:
        config[var] = os.getenv(var, "").strip()

    if not config.get("NEWSDATA_API_KEY"):
        logger.warning("NEWSDATA_API_KEY not set — will run in RSS-only mode.")

    # Parse recipients
    config["RECIPIENTS_LIST"] = [
        r.strip() for r in config["EMAIL_RECIPIENTS"].split(",") if r.strip()
    ]
    if not config["RECIPIENTS_LIST"]:
        logger.error("EMAIL_RECIPIENTS is set but contains no valid email addresses.")
        sys.exit(1)

    logger.info(f"Config loaded. Recipients: {config['RECIPIENTS_LIST']}")
    return config


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run():
    logger.info("=" * 60)
    logger.info("Daily RIA News Digest — starting")
    logger.info("=" * 60)

    # Step 1: Load config
    config = load_env_config()

    # Step 2: Fetch news
    try:
        from fetch_news import fetch_all_news
        logger.info("Fetching news from all sources...")
        articles = fetch_all_news(config["NEWSDATA_API_KEY"])
        logger.info(f"Fetched {len(articles)} unique articles total")
    except ValueError as e:
        # Auth errors (e.g. bad NewsData key) — fail fast
        logger.error(f"News fetch failed with auth error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"News fetch failed unexpectedly: {e}", exc_info=True)
        # Don't exit — continue with empty list (send "no news" email)
        articles = []

    # Step 3: Summarize and categorize
    try:
        from summarize_news import summarize_and_categorize
        logger.info("Summarizing and categorizing with GPT-4o-mini...")
        categorized = summarize_and_categorize(articles, config["OPENAI_API_KEY"])
    except Exception as e:
        logger.error(f"GPT summarization failed: {e}", exc_info=True)
        categorized = {"acquisitions_ma": [], "breakaway_advisors": [], "funding_investment": []}

    total_relevant = sum(len(v) for v in categorized.values())
    logger.info(f"Relevant articles after GPT filter: {total_relevant}")

    # Step 4: Render email HTML
    try:
        from send_email import render_email_html, send_digest_email
        html = render_email_html(categorized)
    except Exception as e:
        logger.error(f"Email rendering failed: {e}", exc_info=True)
        sys.exit(1)

    # Step 5: Send email
    has_news = total_relevant > 0
    try:
        success = send_digest_email(
            html=html,
            gmail_user=config["GMAIL_USER"],
            gmail_app_password=config["GMAIL_APP_PASSWORD"],
            recipients=config["RECIPIENTS_LIST"],
            has_news=has_news,
        )
    except Exception as e:
        logger.error(f"Email send failed: {e}", exc_info=True)
        sys.exit(1)

    if not success:
        logger.error("Email send returned False — check logs above.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Daily RIA News Digest — completed successfully")
    logger.info("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    run()
