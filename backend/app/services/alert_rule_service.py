"""CRUD for admin-defined custom alert rules (see app/models/alert_rule.py
for what a rule means and app/insights/anomaly.py for how it's evaluated).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_rule import AlertRule, AlertRuleMetric, AlertRuleScope
from app.models.anomaly_event import AnomalySeverity
from app.models.audit_log import AuditAction
from app.services import audit_service


async def list_rules(session: AsyncSession, branch: str) -> list[AlertRule]:
    rows = (
        await session.execute(
            select(AlertRule).where(AlertRule.branch == branch).order_by(AlertRule.name)
        )
    ).scalars().all()
    return list(rows)


async def get_rule(session: AsyncSession, rule_id: int, branch: str) -> AlertRule | None:
    """Scoped by branch too, not just id -- a branch-scoped admin must
    never be able to read/edit/delete another branch's rule just by
    guessing its numeric id."""
    return (
        await session.execute(
            select(AlertRule).where(AlertRule.id == rule_id, AlertRule.branch == branch)
        )
    ).scalar_one_or_none()


async def create_rule(
    session: AsyncSession,
    branch: str,
    name: str,
    scope: AlertRuleScope,
    metric: AlertRuleMetric,
    window_minutes: int,
    threshold: int,
    severity: AnomalySeverity,
    enabled: bool,
    actor_user_id: str,
) -> AlertRule:
    row = AlertRule(
        branch=branch,
        name=name,
        scope=scope,
        metric=metric,
        window_minutes=window_minutes,
        threshold=threshold,
        severity=severity,
        enabled=enabled,
    )
    session.add(row)
    await audit_service.record(
        session,
        action=AuditAction.ALERT_RULE_CREATED,
        actor_user_id=actor_user_id,
        branch=branch,
        detail=f'branch={branch} name="{name}" scope={scope.value} metric={metric.value}',
    )
    await session.commit()
    await session.refresh(row)
    return row


async def update_rule(
    session: AsyncSession,
    row: AlertRule,
    name: str,
    scope: AlertRuleScope,
    metric: AlertRuleMetric,
    window_minutes: int,
    threshold: int,
    severity: AnomalySeverity,
    enabled: bool,
    actor_user_id: str,
) -> AlertRule:
    row.name = name
    row.scope = scope
    row.metric = metric
    row.window_minutes = window_minutes
    row.threshold = threshold
    row.severity = severity
    row.enabled = enabled
    await audit_service.record(
        session,
        action=AuditAction.ALERT_RULE_UPDATED,
        actor_user_id=actor_user_id,
        branch=row.branch,
        detail=f'branch={row.branch} id={row.id} name="{name}"',
    )
    await session.commit()
    await session.refresh(row)
    return row


async def delete_rule(session: AsyncSession, row: AlertRule, actor_user_id: str) -> None:
    await audit_service.record(
        session,
        action=AuditAction.ALERT_RULE_DELETED,
        actor_user_id=actor_user_id,
        branch=row.branch,
        detail=f'branch={row.branch} id={row.id} name="{row.name}"',
    )
    await session.delete(row)
    await session.commit()
