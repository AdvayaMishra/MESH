from fastapi import APIRouter
from sqlalchemy import func, select

from app.api import DB, Limit, Offset, P
from app.correlation import (
    CorrelationConfig,
    PolicyChange,
    PolicyHistory,
    PolicyOutput,
    authority,
    create_policy,
    effective,
    output,
)
from app.models import CorrelationPolicy
from app.services import audit

router = APIRouter(prefix="/api/v1/vader")


@router.get("/correlation-policy", response_model=PolicyOutput)
def policy_get(db: DB, p: P):
    p = authority(db, p)
    audit(db, p, "security.correlation_policy.read", p.organization_id)
    row, config = effective(db, p.organization_id)
    return output(row, config)


@router.put("/correlation-policy", response_model=PolicyOutput)
def policy_put(data: PolicyChange, db: DB, p: P):
    return create_policy(db, p, data)


@router.get("/correlation-policies", response_model=PolicyHistory)
def policy_history(db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    p = authority(db, p)
    audit(db, p, "security.correlation_policy.history", p.organization_id)
    query = select(CorrelationPolicy).where(CorrelationPolicy.organization_id == p.organization_id)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.scalars(
        query.order_by(CorrelationPolicy.version.desc()).limit(limit).offset(offset)
    ).all()
    return PolicyHistory(
        policies=[output(row, CorrelationConfig.model_validate(row.configuration)) for row in rows],
        total_policies=total,
        limit=limit,
        offset=offset,
    )
