# Daily RIA News Digest — WAT Workflow SOP

## Objective
Deliver a branded HTML email each morning at 9am IST summarizing the prior 24 hours of US wealth management news — specifically RIA acquisitions, breakaway advisor moves, and funding events — to the FastTrackr AI team.

## Trigger
- **Scheduled**: GitHub Actions cron `30 3 * * *` (3:30am UTC = 9:00am IST), every day
- **Manual**: `workflow_dispatch` button in the GitHub Actions UI (for testing or re-runs)

## Required Environment Variables

| Variable | Description | Where to Get It |
|---|---|---|
| `NEWSDATA_API_KEY` | NewsData.io API key (optional — falls back to RSS-only if missing) | newsdata.io → Free account → Dashboard |
| `OPENAI_API_KEY` | OpenAI API key for GPT-4o-mini | platform.openai.com → API keys |
| `GMAIL_USER` | Sender Gmail address (e.g. digest@yourcompany.com) | Your Gmail account |
| `GMAIL_APP_PASSWORD` | 16-char Gmail App Password — NOT your regular password | Google Account → Security → 2-Step Verification → App Passwords |
| `EMAIL_RECIPIENTS` | Comma-separated recipient email list | Team distribution list |

GitHub repo: Settings → Secrets and variables → Actions → New repository secret.

## Tool Execution Sequence

```
tools/main.py
  │
  ├── 1. load_env_config()          Validate all required env vars (fail fast if missing)
  │
  ├── 2. fetch_news.fetch_all_news()
  │       ├── fetch_newsdata()      2 API calls to NewsData.io (query: M&A + breakaway/funding)
  │       ├── fetch_rss_feeds()     4 RSS feeds, filtered to last 24h
  │       └── deduplicate()         URL-based dedup (UTM params stripped)
  │
  ├── 3. summarize_news.summarize_and_categorize()
  │       └── _call_gpt()           Batched GPT-4o-mini call (20 articles/batch)
  │                                 Returns: acquisitions_ma | breakaway_advisors | funding_investment
  │
  ├── 4. send_email.render_email_html()
  │       └── HTML table-based layout, all CSS inline, Gmail-compatible
  │
  └── 5. send_email.send_digest_email()
          └── Gmail SMTP, starttls on port 587
```

## Categories

| Key | Label | What it covers |
|---|---|---|
| `acquisitions_ma` | Acquisitions & M&A | RIA firm acquisitions, mergers, consolidations, firm sales |
| `breakaway_advisors` | Breakaway Advisors | Advisors leaving wirehouses/broker-dealers to go independent, team moves |
| `funding_investment` | Funding & Investment | VC/PE funding rounds, growth capital, tech investment in wealth management |
| `ai_wealthtech` | AI & Wealthtech | AI tools/platforms for advisors, competitive moves by wealthtech AI companies, regulatory/research news on AI in financial advice |

## Expected Outputs

| Output | Description |
|---|---|
| Email in recipients' inboxes | Branded HTML digest, subject: "RIA News Digest — Monday, February 23" |
| GitHub Actions log | Full run log visible in repo → Actions tab |
| Exit code 0 | Success — even if "no news today" |
| Exit code 1 | Failure — GitHub marks run as red and can notify via email |

## Edge Cases

| Scenario | Behavior |
|---|---|
| NewsData.io returns HTTP 429 (rate limit) | Log warning, continue with RSS-only |
| NewsData.io returns HTTP 401 (bad key) | Raise `ValueError`, fail fast with clear message |
| NewsData.io key not set | Log warning, proceed RSS-only |
| RSS feed unreachable or malformed | Log warning, skip that feed, continue with others |
| Article older than 24h in RSS | Filtered out by `_is_within_24h()` |
| 0 articles fetched | Skip GPT call, send "no news today" email |
| GPT returns invalid JSON | Log raw response, return empty categories, send "no news" email |
| GPT returns unknown category | Filter out that article, log warning |
| Gmail SMTP auth fails | Re-raise with instructions to use App Password, exit 1 |
| Gmail SMTP times out (30s) | Log error, return False, exit 1 |

## Troubleshooting

### Email not arriving
1. Check GitHub Actions log (repo → Actions → latest run)
2. Check spam/junk folder
3. Verify `EMAIL_RECIPIENTS` secret is correct and comma-separated

### SMTPAuthenticationError
- Gmail is rejecting the login. You must use an App Password, not your regular Gmail password.
- Generate one: Google Account → Security → 2-Step Verification → App Passwords
- The password is 16 characters, no spaces (Gmail may show it with spaces — ignore them)

### No articles fetched
- RSS feeds may be slow during off-hours. This is expected — the "no news" email will send.
- If it persists, manually test RSS feeds: `python tools/fetch_news.py`

### GPT returning empty results
- Check that `OPENAI_API_KEY` is valid and has remaining quota
- Test the key: `python tools/summarize_news.py`

### Rate limit on NewsData.io
- Free tier allows 2 API calls/day (resets daily). The cron runs once/day so this should not occur.
- If manually triggering multiple times in a day, the second+ runs will use RSS-only mode.

## Cost Profile (Monthly)
| Component | Cost |
|---|---|
| NewsData.io | $0 (free tier) |
| OpenAI GPT-4o-mini (~8k tokens/day) | ~$0.04 |
| Gmail SMTP | $0 |
| GitHub Actions (~10 min/day on ubuntu-latest) | $0 (well within free tier) |
| **Total** | **~$0.04/month** |

## Maintenance Notes
- **RSS feed changes**: If a feed URL goes stale, update `RSS_FEEDS` in `tools/fetch_news.py`
- **New categories**: Add to `VALID_CATEGORIES` in `summarize_news.py` and `CATEGORY_CONFIG` in `send_email.py`
- **New RSS sources**: Add tuple `("Source Name", "https://feed-url")` to `RSS_FEEDS`
- **Timezone change**: Update cron expression in `.github/workflows/daily_digest.yml`
  - IST = UTC+5:30, so 9am IST = 3:30am UTC = `30 3 * * *`

## Lessons Learned (from initial test run 2026-02-23)

**NewsData.io query syntax**: The free tier does not support complex `OR` operator queries. Simple phrase queries work best (e.g., `"wealth management" acquisition`). GPT-4o-mini handles relevance filtering, so broad queries are fine.

**NewsData.io `country=us` filter**: Too restrictive for niche RIA industry news — returns 0 results. Removed. Language filter (`language=en`) is sufficient.

**RSS feed URLs verified working** (as of 2026-02-23):
  - AdvisorHub: `https://advisorhub.com/feed/` ✓
  - RIABiz: `https://riabiz.com/rss` ✓
  - WealthManagement.com: `https://www.wealthmanagement.com/rss.xml` ✓
  - Financial Planning: `https://www.financial-planning.com/feed/` — XML parse error, monitor

**RSS feeds that are broken** (as of 2026-02-23):
  - ThinkAdvisor `/feed/` → 404 (URL changed, find new one)
  - InvestmentNews `/feed` → 403 (blocked scrapers)

**72h rolling window**: Changed from 24h to 72h to capture Friday articles in Monday's digest. Industry publications don't publish on weekends, so a 24h window on Monday morning always yields 0 results.

**openai library version**: `openai==1.35.0` is incompatible with `httpx>=0.28`. Use `openai>=1.55.0`. Pinned in `requirements.txt`.

**macOS SSL for RSS**: Python on macOS may fail SSL certificate verification when feedparser fetches URLs directly. Fixed by using `requests` to fetch feed content first, then passing bytes to `feedparser.parse()` — requests bundles `certifi` which handles macOS SSL correctly.
