"""
send_email.py — Renders a branded HTML email digest and sends via Gmail SMTP.

Design:
  - Header: dark navy #0A1628
  - Body: light gray #F8FAFC background, white article cards
  - Accent blue: #2563EB
  - Table-based layout for Gmail compatibility
  - All CSS inline
"""

import smtplib
import socket
import logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category display config
# ---------------------------------------------------------------------------
CATEGORY_CONFIG = {
    "acquisitions_ma": {
        "label": "Acquisitions & M&A",
        "badge_bg": "#1E3A5F",
        "badge_color": "#FFFFFF",
        "icon": "🏦",
    },
    "breakaway_advisors": {
        "label": "Breakaway Advisors",
        "badge_bg": "#1E3A5F",
        "badge_color": "#FFFFFF",
        "icon": "🚀",
    },
    "funding_investment": {
        "label": "Funding & Investment",
        "badge_bg": "#1E3A5F",
        "badge_color": "#FFFFFF",
        "icon": "💰",
    },
    "ai_wealthtech": {
        "label": "AI & Wealthtech",
        "badge_bg": "#1E3A5F",
        "badge_color": "#FFFFFF",
        "icon": "🤖",
    },
}


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def _format_date_for_subject() -> str:
    """Returns e.g. 'Monday, February 23'"""
    now = datetime.now(timezone.utc)
    return now.strftime("%A, %B %-d")


def _format_date_for_header() -> str:
    """Returns e.g. 'Monday, February 23, 2026'"""
    now = datetime.now(timezone.utc)
    return now.strftime("%A, %B %-d, %Y")


def _render_article_card(article: dict) -> str:
    title = article.get("title", "Untitled")
    url = article.get("url", "#")
    source = article.get("source", "")
    published = article.get("published", "")
    summary = article.get("summary", "")

    # Format date display
    date_display = ""
    if published:
        try:
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            date_display = dt.strftime("%b %-d, %Y")
        except Exception:
            date_display = published[:10]

    meta = " · ".join(filter(None, [source, date_display]))

    return f"""
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;">
      <tr>
        <td style="background:#FFFFFF;border-radius:8px;padding:20px;border:1px solid #E2E8F0;">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td>
                <a href="{url}" style="font-size:17px;font-weight:700;color:#0A1628;text-decoration:none;line-height:1.4;display:block;margin-bottom:6px;">{title}</a>
              </td>
            </tr>
            <tr>
              <td style="font-size:12px;color:#64748B;margin-bottom:10px;padding-bottom:12px;">{meta}</td>
            </tr>
            <tr>
              <td style="font-size:14px;color:#374151;line-height:1.6;padding-bottom:14px;">{summary}</td>
            </tr>
            <tr>
              <td>
                <a href="{url}" style="font-size:13px;color:#2563EB;text-decoration:none;font-weight:600;">Read more →</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>"""


def _render_category_section(category_key: str, articles: list[dict]) -> str:
    if not articles:
        return ""

    config = CATEGORY_CONFIG.get(category_key, {
        "label": category_key,
        "badge_bg": "#1E3A5F",
        "badge_color": "#FFFFFF",
        "icon": "📰",
    })

    cards_html = "".join(_render_article_card(a) for a in articles)

    return f"""
    <!-- Category: {config['label']} -->
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:32px;">
      <tr>
        <td>
          <!-- Category header -->
          <table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-bottom:16px;">
            <tr>
              <td>
                <span style="display:inline-block;background:{config['badge_bg']};color:{config['badge_color']};font-size:13px;font-weight:700;padding:6px 14px;border-radius:20px;text-transform:uppercase;letter-spacing:0.5px;">
                  {config['icon']} &nbsp;{config['label']}
                </span>
              </td>
            </tr>
          </table>
          <!-- Article cards -->
          {cards_html}
        </td>
      </tr>
    </table>"""


def render_email_html(categorized: dict[str, list[dict]]) -> str:
    """
    Render the full HTML email.

    Args:
        categorized: Dict from summarize_news.py with keys acquisitions_ma,
                     breakaway_advisors, funding_investment

    Returns:
        HTML string ready to send.
    """
    total_articles = sum(len(v) for v in categorized.values())
    date_header = _format_date_for_header()

    if total_articles == 0:
        body_content = """
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="padding:40px;text-align:center;color:#64748B;font-size:15px;">
              No relevant RIA industry news was found in the last 24 hours.<br>
              Check back tomorrow.
            </td>
          </tr>
        </table>"""
    else:
        sections = ""
        for cat_key in ["acquisitions_ma", "breakaway_advisors", "funding_investment", "ai_wealthtech"]:
            articles = categorized.get(cat_key, [])
            sections += _render_category_section(cat_key, articles)

        body_content = f"""
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="padding:32px 40px;">
              {sections}
            </td>
          </tr>
        </table>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FastTrackr AI — Daily RIA News Digest</title>
</head>
<body style="margin:0;padding:0;background-color:#F8FAFC;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#F8FAFC">
    <tr>
      <td align="center" style="padding:24px 16px;">

        <!-- Email container -->
        <table width="640" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;width:100%;">

          <!-- Header -->
          <tr>
            <td style="background:#0A1628;border-radius:12px 12px 0 0;padding:32px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td>
                    <div style="font-size:12px;color:#94A3B8;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;font-weight:600;">FastTrackr AI</div>
                    <div style="font-size:24px;font-weight:800;color:#FFFFFF;margin-bottom:6px;line-height:1.2;">Daily RIA News Digest</div>
                    <div style="font-size:14px;color:#94A3B8;">{date_header}</div>
                  </td>
                  <td align="right" valign="middle">
                    <div style="font-size:32px;">📊</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="background:#F8FAFC;padding:0;">
              {body_content}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:#0A1628;border-radius:0 0 12px 12px;padding:24px 40px;">
              <table width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="color:#94A3B8;font-size:12px;line-height:1.6;">
                    <a href="https://fasttrackr.ai" style="color:#60A5FA;text-decoration:none;font-weight:600;">fasttrackr.ai</a>
                    &nbsp;·&nbsp; Daily digest for the FastTrackr AI team
                    <br>
                    News sourced from NewsData.io, ThinkAdvisor, WealthManagement.com, Financial Planning, and InvestmentNews.
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
        <!-- /Email container -->

      </td>
    </tr>
  </table>

</body>
</html>"""

    return html


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------

def send_digest_email(
    html: str,
    gmail_user: str,
    gmail_app_password: str,
    recipients: list[str],
    has_news: bool = True,
) -> bool:
    """
    Send the HTML digest via Gmail SMTP.

    Args:
        html: Rendered HTML string
        gmail_user: Sender Gmail address
        gmail_app_password: 16-char Gmail App Password
        recipients: List of recipient email addresses
        has_news: If False, subject line reflects no-news state

    Returns:
        True on success, False on failure.
    """
    date_str = _format_date_for_subject()

    if has_news:
        subject = f"RIA News Digest — {date_str}"
    else:
        subject = f"RIA News Digest — No news today ({date_str})"

    # Build MIME message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"FastTrackr AI <{gmail_user}>"
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=False)

    # Plain text fallback via BeautifulSoup
    plain_text = BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()
    msg.attach(MIMEText(plain_text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(gmail_user, gmail_app_password)
            server.sendmail(gmail_user, recipients, msg.as_string())

        logger.info(f"Email sent to {len(recipients)} recipient(s): {', '.join(recipients)}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        raise smtplib.SMTPAuthenticationError(
            e.smtp_code,
            (
                f"Gmail authentication failed. Make sure GMAIL_APP_PASSWORD is a "
                f"16-character App Password (not your regular Gmail password). "
                f"Generate at: Google Account → Security → 2-Step Verification → App Passwords. "
                f"Original error: {e.smtp_error}"
            ),
        )

    except socket.timeout:
        logger.error("Gmail SMTP connection timed out.")
        return False

    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


if __name__ == "__main__":
    import os
    import json
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    from dotenv import load_dotenv
    load_dotenv()

    # Render a preview with dummy data
    dummy_categorized = {
        "acquisitions_ma": [
            {
                "title": "Mercer Advisors Acquires $500M Denver RIA",
                "url": "https://example.com/mercer",
                "source": "InvestmentNews",
                "published": "2026-02-23T10:00:00+00:00",
                "category": "acquisitions_ma",
                "summary": "Mercer Advisors announced the acquisition of a $500M AUM RIA firm headquartered in Denver, Colorado. The deal expands Mercer's presence in the Mountain West. For independent advisors, this signals continued consolidation pressure as large aggregators accelerate their buy-and-build strategies.",
            }
        ],
        "breakaway_advisors": [
            {
                "title": "Morgan Stanley Team Takes $1.2B Book Independent",
                "url": "https://example.com/ms",
                "source": "ThinkAdvisor",
                "published": "2026-02-23T08:00:00+00:00",
                "category": "breakaway_advisors",
                "summary": "A four-advisor team managing $1.2B AUM departed Morgan Stanley to launch their own RIA using the Schwab Advisor Services custodian platform. The team cited greater flexibility and higher payout as primary motivators. This move highlights the growing appeal of the independent model as wirehouses face mounting talent attrition.",
            }
        ],
        "funding_investment": [],
    }

    html = render_email_html(dummy_categorized)

    # Write preview to .tmp/
    os.makedirs(".tmp", exist_ok=True)
    preview_path = ".tmp/preview.html"
    with open(preview_path, "w") as f:
        f.write(html)
    print(f"HTML preview written to {preview_path}")

    # Optionally send
    gmail_user = os.getenv("GMAIL_USER", "")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD", "")
    recipients_raw = os.getenv("EMAIL_RECIPIENTS", "")

    if gmail_user and gmail_pass and recipients_raw:
        recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
        has_news = any(dummy_categorized.values())
        success = send_digest_email(html, gmail_user, gmail_pass, recipients, has_news)
        print(f"Email sent: {success}")
    else:
        print("Skipping email send — Gmail credentials not configured in .env")
