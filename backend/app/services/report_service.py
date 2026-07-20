"""Generates and sends periodic summary reports (see report_scheduler.py
for the automatic schedule, api/routes/reports.py for on-demand sending).

Reuses the same read-side queries the dashboard itself uses
(stats_service, insights_service) rather than computing anything new, and
export_service's CSV builder for the raw-event attachment -- no new
report-specific data model.
"""

import asyncio
import html
import logging
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.schemas.domains import CategoryStat, DomainStat
from app.schemas.insights import AnomalyEventOut
from app.schemas.summary import SummaryResponse
from app.services import export_service, insights_service, stats_service

logger = logging.getLogger(__name__)

_TOP_DOMAINS_LIMIT = 10
_RECENT_ANOMALIES_LIMIT = 20


def _domain_rows(items: list[DomainStat], value_attr: str) -> str:
    if not items:
        return "<tr><td>No data for this period.</td></tr>"
    return "".join(
        f"<tr><td>{html.escape(item.domain)}</td>"
        f"<td style='text-align:right'>{getattr(item, value_attr):,}</td></tr>"
        for item in items
    )


def _category_rows(items: list[CategoryStat]) -> str:
    if not items:
        return "<tr><td>No data for this period.</td></tr>"
    return "".join(
        f"<tr><td>{html.escape(item.category.value)}</td>"
        f"<td style='text-align:right'>{item.request_count:,}</td></tr>"
        for item in items
    )


def _anomaly_rows(items: list[AnomalyEventOut]) -> str:
    if not items:
        return "<tr><td>No anomalies recorded.</td></tr>"
    return "".join(
        f"<tr><td>{item.generated_at.isoformat()}</td>"
        f"<td>{html.escape(item.severity.value)}</td>"
        f"<td>{html.escape(item.title)}</td>"
        f"<td>{html.escape(item.description)}</td></tr>"
        for item in items
    )


def render_report_html(
    since: datetime,
    until: datetime,
    summary: SummaryResponse,
    top_domains: list[DomainStat],
    top_blocked: list[DomainStat],
    by_category: list[CategoryStat],
    anomalies: list[AnomalyEventOut],
    branch: str | None = None,
) -> str:
    title = f"Squid Watch report &mdash; {html.escape(branch)}" if branch else "Squid Watch report"
    return f"""\
<html>
<body style="font-family: -apple-system, Arial, sans-serif; color: #1a1a1a;">
  <h2>{title}</h2>
  <p>{since.isoformat()} &ndash; {until.isoformat()}</p>

  <h3>Summary</h3>
  <table cellpadding="4">
    <tr><td>Total requests</td><td style="text-align:right">{summary.total_requests:,}</td></tr>
    <tr><td>Blocked</td><td style="text-align:right">{summary.blocked_requests:,}</td></tr>
    <tr><td>Allowed</td><td style="text-align:right">{summary.allowed_requests:,}</td></tr>
    <tr><td>Active clients</td><td style="text-align:right">{summary.active_client_count:,}</td></tr>
  </table>

  <h3>Top domains by requests</h3>
  <table cellpadding="4">{_domain_rows(top_domains, "request_count")}</table>

  <h3>Top blocked domains</h3>
  <table cellpadding="4">{_domain_rows(top_blocked, "blocked_count")}</table>

  <h3>Usage by category</h3>
  <table cellpadding="4">{_category_rows(by_category)}</table>

  <h3>Recent anomalies</h3>
  <table cellpadding="4">{_anomaly_rows(anomalies)}</table>

  <p style="color:#666; font-size:12px;">Full event-level detail is attached as a CSV.</p>
</body>
</html>
"""


async def generate_report(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None = None
) -> str:
    summary = await stats_service.get_summary(session, since, until, range_param=None, branch=branch)
    top_domains = await stats_service.get_top_domains(
        session, since, until, limit=_TOP_DOMAINS_LIMIT, branch=branch
    )
    top_blocked = await stats_service.get_top_domains(
        session,
        since,
        until,
        limit=_TOP_DOMAINS_LIMIT,
        blocked_only=True,
        order_by="blocked",
        branch=branch,
    )
    by_category = await stats_service.get_usage_by_category(session, since, until, branch)
    recent_anomalies = await insights_service.list_recent(
        session, limit=_RECENT_ANOMALIES_LIMIT, offset=0, branch=branch
    )

    return render_report_html(
        since, until, summary, top_domains, top_blocked, by_category, recent_anomalies.items, branch
    )


def send_report_email(
    recipients: list[str], subject: str, html_body: str, csv_attachment: str | None = None
) -> None:
    """Synchronous (smtplib has no async API) -- callers on the event loop
    must run this via asyncio.to_thread, see generate_and_send_report."""
    settings = get_settings()
    if not settings.SMTP_HOST or not settings.SMTP_FROM_ADDRESS:
        raise RuntimeError("SMTP is not configured (SMTP_HOST / SMTP_FROM_ADDRESS missing).")

    message = MIMEMultipart()
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM_ADDRESS
    message["To"] = ", ".join(recipients)
    message.attach(MIMEText(html_body, "html"))

    if csv_attachment is not None:
        attachment = MIMEApplication(csv_attachment.encode("utf-8"), Name="events.csv")
        attachment["Content-Disposition"] = 'attachment; filename="events.csv"'
        message.attach(attachment)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM_ADDRESS, recipients, message.as_string())


async def generate_and_send_report(
    session: AsyncSession, since: datetime, until: datetime, branch: str | None = None
) -> bool:
    """Returns False (no-op) if REPORT_RECIPIENTS isn't configured -- mirrors
    alerting.maybe_alert's "no config, no-op" shape. `branch=None` reports on
    every branch combined; report_scheduler.py calls this once per
    configured branch instead so each branch gets its own, clearly labeled
    report."""
    settings = get_settings()
    if not settings.REPORT_RECIPIENTS:
        return False

    html_body = await generate_report(session, since, until, branch)
    csv_attachment = await export_service.export_as_csv(
        session, since, until, blocked_only=False, branch=branch
    )
    branch_suffix = f" ({branch})" if branch else ""
    subject = f"Squid Watch report{branch_suffix}: {since.date()} to {until.date()}"

    await asyncio.to_thread(
        send_report_email, settings.REPORT_RECIPIENTS, subject, html_body, csv_attachment
    )
    return True
