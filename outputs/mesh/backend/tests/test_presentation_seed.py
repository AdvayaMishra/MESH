import importlib.util
from pathlib import Path

from app.models import (
    Employee,
    Incident,
    Membership,
    Outbox,
    Project,
    RiskPolicy,
    SecurityEvent,
    Task,
)
from app.risk_engine import ALGORITHM, DEFAULT_THRESHOLDS, DEFAULT_WEIGHTS
from conftest import ANALYST2, ORG_A, ORG_B, OWNER
from sqlalchemy import func, select


def test_presentation_seed_is_scoped_synthetic_and_idempotent(db):
    path = Path(__file__).resolve().parents[2] / "scripts/seed_presentation.py"
    spec = importlib.util.spec_from_file_location("presentation_seed", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    db.get(Membership, (ORG_A, ANALYST2)).active = False
    db.add(
        RiskPolicy(
            organization_id=ORG_A,
            created_by=OWNER,
            version=1,
            algorithm_version=ALGORITHM,
            weights=DEFAULT_WEIGHTS,
            thresholds=DEFAULT_THRESHOLDS,
        )
    )
    db.commit()
    first = module.populate(db, ORG_A)
    db.commit()
    assert len(first["new_records"]["employees"]) == 3
    assert len(first["new_records"]["projects"]) == 3
    assert len(first["new_records"]["tasks"]) == 3
    assert (
        db.scalar(
            select(func.count())
            .select_from(SecurityEvent)
            .where(SecurityEvent.organization_id == ORG_A)
        )
        == 6
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(SecurityEvent)
            .where(SecurityEvent.synthetic.is_(False))
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count()).select_from(Incident).where(Incident.organization_id == ORG_A)
        )
        >= 2
    )
    assert (
        db.scalar(select(func.count()).select_from(Outbox).where(Outbox.topic == "mail.invitation"))
        == 0
    )
    for model in (Employee, Project, Task, SecurityEvent, Incident):
        assert (
            db.scalar(select(func.count()).select_from(model).where(model.organization_id == ORG_B))
            == 0
        )
    assert (
        db.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.email.like("%@example.invalid"), Membership.active.is_(True))
        )
        == 0
    )
    again = module.populate(db, ORG_A)
    db.commit()
    assert again["new_records"] == {}
    assert again["synthetic_assessment_id"] == first["synthetic_assessment_id"]
