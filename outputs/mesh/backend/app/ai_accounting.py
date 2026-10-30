"""Independent PostgreSQL model-call accounting; uncertain dispatches retain admission."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import Engine, case, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.ai import INPUT_ADMISSION_UNITS, OUTPUT_ADMISSION_UNITS, price, units
from app.ai_accounting_pool import engine_for
from app.ai_receipts_schema import ReconciliationInput
from app.auth import Principal
from app.core.config import AIUsagePolicy
from app.core.db import assert_runtime_role, tenant_context
from app.core.time import as_utc
from app.models import (
    AIRequest,
    AIRequestEvent,
    AIUsage,
    Membership,
    Organization,
    identifier,
    now,
)

ACTIVE = ("reserved", "dispatched", "ambiguous")
PURPOSE_PERMISSION = {
    "owner": "finance.read",
    "hr": "employee.read",
    "devtrack": "project.read",
    "vader": "security.read",
}


def period(value: datetime) -> datetime:
    return as_utc(value).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_period_filter(month: datetime):
    end = (
        month.replace(month=month.month + 1)
        if month.month < 12
        else month.replace(year=month.year + 1, month=1)
    )
    return or_(
        AIUsage.admission_period_start == month,
        AIUsage.admission_period_start.is_(None)
        & (AIUsage.created_at >= month)
        & (AIUsage.created_at < end),
    )


class SQLAccounting:
    def __init__(self, engine: Engine, actor: Principal):
        if engine.dialect.name != "postgresql":
            raise HTTPException(503, "Paid model dispatch requires durable PostgreSQL accounting")
        self.factory = sessionmaker(engine, expire_on_commit=False)
        self.actor = actor
        self.clock = now

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        try:
            with self.factory.begin() as db:
                assert_runtime_role(db)
                tenant_context(db, self.actor.organization_id, self.actor.user_id)
                db.execute(text("SET LOCAL statement_timeout='5s'"))
                db.execute(text("SET LOCAL lock_timeout='2s'"))
                yield db
        except SQLAlchemyError:
            raise HTTPException(
                503, "AI accounting unavailable; no automatic regeneration"
            ) from None

    def authorize(self, db: Session, permission: str):
        organization = db.get(Organization, self.actor.organization_id, populate_existing=True)
        member = db.get(
            Membership,
            (self.actor.organization_id, self.actor.user_id),
            populate_existing=True,
        )
        if (
            organization is None
            or organization.status != "active"
            or member is None
            or not member.active
        ):
            raise HTTPException(403, "Active model-accounting authority required")
        Principal(member.user_id, self.actor.organization_id, member.role).require(permission)

    def request(self, db: Session, request_id: str) -> AIRequest:
        record = db.scalar(
            select(AIRequest)
            .where(
                AIRequest.organization_id == self.actor.organization_id,
                AIRequest.id == request_id,
            )
            .with_for_update()
        )
        if record is None:
            raise HTTPException(404, "AI request not found")
        return record

    def event(self, db: Session, record: AIRequest, kind: str, details: dict | None = None):
        position = (
            int(
                db.scalar(
                    select(func.coalesce(func.max(AIRequestEvent.position), 0)).where(
                        AIRequestEvent.organization_id == record.organization_id,
                        AIRequestEvent.request_id == record.id,
                    )
                )
                or 0
            )
            + 1
        )
        db.add(
            AIRequestEvent(
                organization_id=record.organization_id,
                request_id=record.id,
                position=position,
                actor_id=self.actor.user_id,
                kind=kind,
                details=details or {},
            )
        )
        db.flush()

    def admit(self, db: Session, policy: AIUsagePolicy, month: datetime):
        if db.get_bind().dialect.name == "postgresql":
            key = int.from_bytes(
                hashlib.sha256(
                    ("mesh-ai-admission-v1:" + self.actor.organization_id).encode()
                ).digest()[:8],
                "big",
                signed=True,
            )
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        successful = db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(AIUsage.input_units), 0),
                func.coalesce(func.sum(AIUsage.output_units), 0),
                func.coalesce(func.sum(AIUsage.estimated_cost), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                or_(
                                    AIUsage.estimated_cost.is_(None),
                                    AIUsage.billing_currency.is_(None),
                                    AIUsage.billing_currency != policy.currency,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                or_(
                                    AIUsage.input_units < 0,
                                    AIUsage.output_units < 0,
                                    AIUsage.estimated_cost < 0,
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(
                AIUsage.organization_id == self.actor.organization_id,
                usage_period_filter(month),
                AIUsage.provider != "local-deterministic",
            )
        ).one()
        active = AIRequest.status.in_(ACTIVE)
        charged = AIRequest.status == "reconciled_charge"
        in_reserve = case(
            (
                AIRequest.observed_input_units > AIRequest.reserved_input_units,
                AIRequest.observed_input_units,
            ),
            else_=AIRequest.reserved_input_units,
        )
        out_reserve = case(
            (
                AIRequest.observed_output_units > AIRequest.reserved_output_units,
                AIRequest.observed_output_units,
            ),
            else_=AIRequest.reserved_output_units,
        )
        amount = case(
            (
                active,
                case(
                    (AIRequest.reserved_cost.is_(None), AIRequest.observed_cost),
                    (
                        AIRequest.observed_cost > AIRequest.reserved_cost,
                        AIRequest.observed_cost,
                    ),
                    else_=AIRequest.reserved_cost,
                ),
            ),
            (charged, AIRequest.observed_cost),
            else_=0,
        )
        currency = case(
            (active, func.coalesce(AIRequest.currency, AIRequest.observed_currency)),
            (charged, AIRequest.observed_currency),
            else_=policy.currency,
        )
        incomplete = or_(
            amount.is_(None),
            currency.is_(None),
            currency != policy.currency,
            active
            & AIRequest.currency.is_not(None)
            & AIRequest.observed_currency.is_not(None)
            & (AIRequest.currency != AIRequest.observed_currency),
        )
        pending = db.execute(
            select(
                func.count(),
                func.coalesce(
                    func.sum(
                        case(
                            (active, in_reserve),
                            (charged, AIRequest.observed_input_units),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (active, out_reserve),
                            (charged, AIRequest.observed_output_units),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(func.sum(amount), 0),
                func.coalesce(func.sum(case((incomplete, 1), else_=0)), 0),
            ).where(
                AIRequest.organization_id == self.actor.organization_id,
                AIRequest.period_start == month,
                AIRequest.status.in_((*ACTIVE, "reconciled_charge", "reconciled_no_charge")),
            )
        ).one()
        if successful[5]:
            raise HTTPException(503, "Historical AI usage requires accounting review")
        if (
            successful[0] + pending[0] >= policy.monthly_requests
            or successful[1] + pending[1] + INPUT_ADMISSION_UNITS > policy.monthly_input_units
            or successful[2] + pending[2] + OUTPUT_ADMISSION_UNITS > policy.monthly_output_units
        ):
            raise HTTPException(429, "Organization AI usage admission limit reached")
        if policy.monthly_cost_limit is not None:
            if successful[4] or pending[4]:
                raise HTTPException(503, "AI costs are incomplete or use another currency")
            if (
                Decimal(successful[3])
                + Decimal(pending[3])
                + price(policy, INPUT_ADMISSION_UNITS, OUTPUT_ADMISSION_UNITS)
                > policy.monthly_cost_limit
            ):
                raise HTTPException(429, "Organization AI cost admission limit reached")

    def reserve(
        self,
        purpose: str,
        policy: AIUsagePolicy,
        context_digest: str,
        endpoint_digest: str,
    ) -> AIRequest:
        with self.transaction() as db:
            self.authorize(db, PURPOSE_PERMISSION[purpose])
            current = self.clock()
            month = period(current)
            self.admit(db, policy, month)
            record = AIRequest(
                id=identifier(),
                organization_id=self.actor.organization_id,
                requested_by=self.actor.user_id,
                purpose=purpose,
                provider=policy.provider,
                model=policy.model,
                policy_snapshot=policy.model_dump(mode="json"),
                context_digest=context_digest,
                endpoint_digest=endpoint_digest,
                period_start=month,
                reserved_input_units=INPUT_ADMISSION_UNITS,
                reserved_output_units=OUTPUT_ADMISSION_UNITS,
                reserved_cost=price(policy, INPUT_ADMISSION_UNITS, OUTPUT_ADMISSION_UNITS)
                if policy.currency
                else None,
                currency=policy.currency,
                dispatch_deadline=current + timedelta(seconds=60),
            )
            db.add(record)
            db.flush()
            self.event(db, record, "reserved")
        return record

    def dispatch(self, request_id: str, token: str) -> AIRequest:
        expired = False
        with self.transaction() as db:
            record = self.request(db, request_id)
            self.authorize(db, PURPOSE_PERMISSION[record.purpose])
            if record.status != "reserved":
                raise HTTPException(409, "AI request is no longer awaiting dispatch")
            current = self.clock()
            if as_utc(record.dispatch_deadline) <= current or as_utc(record.period_start) != period(
                current
            ):
                record.status, record.settled_at = "cancelled", current
                self.event(db, record, "cancelled", {"reason": "pre_dispatch_expired"})
                expired = True
            else:
                record.status, record.dispatch_token, record.dispatched_at = (
                    "dispatched",
                    token,
                    current,
                )
                record.dispatch_deadline = current + timedelta(seconds=90)
                self.event(db, record, "dispatched")
        if expired:
            raise HTTPException(409, "AI dispatch reservation expired; generation was not sent")
        return record

    def not_dispatched(self, request_id: str, token: str):
        with self.transaction() as db:
            record = self.request(db, request_id)
            if record.status not in {
                "reserved",
                "dispatched",
            } or record.dispatch_token not in {
                None,
                token,
            }:
                return
            record.status, record.settled_at = "not_dispatched", self.clock()
            self.event(db, record, "not_dispatched", {"reason": "trusted_pre_send_failure"})

    def ambiguous(self, request_id: str, token: str, observed: tuple[int, int] | None = None):
        with self.transaction() as db:
            record = self.request(db, request_id)
            if record.dispatch_token != token or record.status in {
                "succeeded",
                "not_dispatched",
                "cancelled",
            }:
                return
            before = (
                record.observed_input_units,
                record.observed_output_units,
                record.observed_cost,
                record.observed_currency,
            )
            if observed is not None:
                input_units, output_units = units(observed[0]), units(observed[1])
                input_units = max(input_units, record.observed_input_units or 0)
                output_units = max(output_units, record.observed_output_units or 0)
                record.observed_input_units, record.observed_output_units = (
                    input_units,
                    output_units,
                )
                frozen = AIUsagePolicy.model_validate(record.policy_snapshot)
                observed_cost = (
                    price(frozen, input_units, output_units) if frozen.currency else None
                )
                # A late observation cannot erase a larger owner-reported
                # charge. Preserve a different observed currency too, so
                # admission remains incomplete rather than silently converting.
                if record.observed_currency in {None, frozen.currency}:
                    if observed_cost is not None:
                        record.observed_cost = max(
                            record.observed_cost or Decimal(0), observed_cost
                        )
                    record.observed_currency = frozen.currency
            if record.status != "ambiguous":
                late = record.status.startswith("reconciled_")
                record.status, record.settled_at = "ambiguous", None
                record.reconciliation_digest = None
                self.event(
                    db,
                    record,
                    "late_observation" if late else "ambiguous",
                    {
                        "reason": "provider_or_settlement_uncertain",
                        "input_units": record.observed_input_units,
                        "output_units": record.observed_output_units,
                        "estimated_cost": str(record.observed_cost)
                        if record.observed_cost is not None
                        else None,
                        "currency": record.observed_currency,
                        "provider_invoice_verified": False,
                    },
                )
            elif before != (
                record.observed_input_units,
                record.observed_output_units,
                record.observed_cost,
                record.observed_currency,
            ):
                self.event(
                    db,
                    record,
                    "observation_amended",
                    {
                        "input_units": record.observed_input_units,
                        "output_units": record.observed_output_units,
                        "estimated_cost": str(record.observed_cost)
                        if record.observed_cost is not None
                        else None,
                        "currency": record.observed_currency,
                        "provider_invoice_verified": False,
                    },
                )

    def succeed(
        self,
        request_id: str,
        token: str,
        provider: str,
        input_units: int,
        output_units: int,
    ) -> AIRequest:
        input_units, output_units = units(input_units), units(output_units)
        with self.transaction() as db:
            record = self.request(db, request_id)
            if record.dispatch_token != token or record.provider != provider:
                raise HTTPException(409, "AI dispatch ownership changed")
            if record.status == "succeeded":
                if (record.observed_input_units, record.observed_output_units) != (
                    input_units,
                    output_units,
                ):
                    raise HTTPException(409, "AI request already has another usage observation")
                return record
            if (
                record.status != "dispatched"
                or input_units > record.reserved_input_units
                or output_units > record.reserved_output_units
            ):
                raise HTTPException(409, "AI request needs accounting review")
            frozen = AIUsagePolicy.model_validate(record.policy_snapshot)
            cost = price(frozen, input_units, output_units) if frozen.currency else None
            pricing = (
                {
                    "input_per_million": str(frozen.input_price_per_million),
                    "output_per_million": str(frozen.output_price_per_million),
                    "source": "operator-configured; estimate, not provider invoice",
                }
                if frozen.currency
                else None
            )
            db.add(
                AIUsage(
                    organization_id=record.organization_id,
                    request_id=record.id,
                    admission_period_start=record.period_start,
                    provider=provider,
                    purpose=record.purpose,
                    model=record.model,
                    input_units=input_units,
                    output_units=output_units,
                    estimated_cost=cost,
                    billing_currency=frozen.currency,
                    pricing=pricing,
                )
            )
            record.status, record.settled_at = "succeeded", self.clock()
            record.observed_input_units, record.observed_output_units = (
                input_units,
                output_units,
            )
            record.observed_cost, record.observed_currency = cost, frozen.currency
            self.event(
                db,
                record,
                "succeeded",
                {"source": "provider_units_operator_price_estimate"},
            )
        return record

    def cancel_expired(self, request_id: str) -> AIRequest:
        with self.transaction() as db:
            self.authorize(db, "finance.read")
            record = self.request(db, request_id)
            if record.status == "cancelled":
                return record
            if record.status != "reserved" or as_utc(record.dispatch_deadline) > self.clock():
                raise HTTPException(
                    409, "Only an expired request awaiting dispatch can be cancelled"
                )
            record.status, record.settled_at = "cancelled", self.clock()
            self.event(
                db,
                record,
                "cancelled",
                {"reason": "owner_cancelled_expired_pre_dispatch"},
            )
        return record

    def reconcile(self, request_id: str, data: ReconciliationInput) -> AIRequest:
        digest = hashlib.sha256(
            json.dumps(
                {"actor": self.actor.user_id, "report": data.model_dump(mode="json")},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        with self.transaction() as db:
            self.authorize(db, "finance.read")
            record = self.request(db, request_id)
            if record.status.startswith("reconciled_"):
                if record.reconciliation_digest != digest:
                    raise HTTPException(409, "AI request already has another accounting report")
                return record
            if (
                record.status not in {"dispatched", "ambiguous"}
                or as_utc(record.dispatch_deadline) > self.clock()
            ):
                raise HTTPException(
                    409, "AI dispatch is not eligible for accounting reconciliation"
                )
            record.status = (
                "reconciled_charge" if data.outcome == "charge" else "reconciled_no_charge"
            )
            record.settled_at, record.reconciliation_digest = self.clock(), digest
            record.observed_input_units, record.observed_output_units = (
                data.input_units,
                data.output_units,
            )
            record.observed_cost, record.observed_currency = data.amount, data.currency
            self.event(
                db,
                record,
                record.status,
                {
                    "reference": data.reference,
                    "worker_stopped_attested": True,
                    "provider_billing_reviewed_attested": True,
                    "source": "owner_report",
                    "provider_invoice_verified": False,
                    "input_units": data.input_units,
                    "output_units": data.output_units,
                    "amount": str(data.amount) if data.amount is not None else None,
                    "currency": data.currency,
                },
            )
        return record


def store_for(db: Session, actor: Principal) -> SQLAccounting:
    engine = db.get_bind()
    if not isinstance(engine, Engine):
        raise HTTPException(503, "Independent model accounting connection is unavailable")
    return SQLAccounting(engine_for(engine), actor)
