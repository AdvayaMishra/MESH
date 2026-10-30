"""Explicit, idempotent presentation data; never email or provision external access."""

import argparse
import json
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from app.auth import Principal
from app.core.db import SessionFactory, assert_runtime_role, tenant_context
from app.models import (
    Budget,
    CostRecord,
    Department,
    Employee,
    LeaveRequest,
    Membership,
    Organization,
    Payroll,
    Project,
    ProjectMember,
    Sprint,
    Task,
    TaskDetail,
    now,
)
from app.project_governance import snapshot
from app.risk_api import RiskAssessmentInput, assess
from app.services import audit
from app.vader import simulate
from sqlalchemy import select


def populate(db, organization):
    """Caller supplies one transaction and an explicitly authorized tenant."""
    namespace = UUID(organization)
    tenant_context(db, organization, "presentation-seed")
    org = db.get(Organization, organization)
    if org is None or org.status != "active":
        raise ValueError("An active organization is required")
    members = db.scalars(
        select(Membership).where(
            Membership.organization_id == organization, Membership.active.is_(True)
        )
    ).all()

    def account(role):
        matches = [m for m in members if m.role == role]
        if len(matches) != 1:
            raise ValueError(
                "Exactly one active " + role + " is required for this presentation setup"
            )
        return matches[0]

    owner, developer, analyst = (
        account("owner"),
        account("junior_developer"),
        account("security_analyst"),
    )
    actor = Principal(owner.user_id, organization, "owner")
    tenant_context(db, organization, owner.user_id)
    created = {}

    def ident(label):
        return str(uuid5(namespace, "mesh-presentation-v1:" + label))

    def add(model, label, **values):
        key = ident(label)
        existing = db.get(model, key)
        if existing is not None:
            if existing.organization_id != organization:
                raise ValueError("Presentation ID scope mismatch")
            return existing
        item = model(id=key, organization_id=organization, **values)
        db.add(item)
        db.flush()
        audit(db, actor, "presentation.fixture.created", key)
        created.setdefault(model.__tablename__, []).append(key)
        return item

    for name in ("DEMO Engineering", "DEMO People", "DEMO Security"):
        existing = db.scalar(
            select(Department).where(
                Department.organization_id == organization, Department.name == name
            )
        )
        if existing is None:
            add(Department, "department:" + name, name=name)
    employees = []
    for index, (name, department) in enumerate(
        (
            ("DEMO Maya Rao", "DEMO Engineering"),
            ("DEMO Rohan Shah", "DEMO Security"),
            ("DEMO Ananya Das", "DEMO People"),
        )
    ):
        uid = ident("fictional-user:" + str(index))
        if db.get(Membership, (organization, uid)) is None:
            # No Auth account or login is created for fictional directory entries.
            db.add(
                Membership(
                    organization_id=organization,
                    user_id=uid,
                    email=f"presentation-{index}@example.invalid",
                    role="junior_developer",
                    active=False,
                )
            )
            db.flush()
        employees.append(
            add(
                Employee,
                "employee:" + str(index),
                user_id=uid,
                name=name,
                department=department,
                status="onboarding",
                verification_status="pending",
            )
        )
    policy = snapshot(db, organization)
    projects = []
    for index, (name, status) in enumerate(
        (
            ("DEMO Secure employee portal", "approved"),
            ("DEMO Expense insights", "proposed"),
            ("DEMO Security dashboard", "proposed"),
        )
    ):
        project = add(
            Project,
            "project:" + str(index),
            name=name,
            status=status,
            description="Fictional presentation fixture. Preloaded status is not evidence of a real approval or deployment.",
            proposer_id=developer.user_id,
            approval_policy=policy,
        )
        projects.append(project)
        membership = db.scalar(
            select(ProjectMember).where(
                ProjectMember.organization_id == organization,
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == developer.user_id,
            )
        )
        if membership is None:
            add(
                ProjectMember,
                "project-member:" + str(index),
                project_id=project.id,
                user_id=developer.user_id,
                manager=False,
            )
    today = now().date()
    sprint = add(
        Sprint,
        "sprint",
        project_id=projects[0].id,
        name="DEMO Presentation sprint",
        starts_on=today,
        ends_on=today + timedelta(days=7),
        status="active",
    )
    for index, (title, status, priority) in enumerate(
        (
            ("DEMO Review login validation", "todo", "high"),
            ("DEMO Add employee search", "in_progress", "normal"),
            ("DEMO Document test workflow", "done", "low"),
        )
    ):
        task = add(
            Task,
            "task:" + str(index),
            project_id=projects[0].id,
            assignee_id=developer.user_id,
            title=title,
            status=status,
        )
        if (
            db.scalar(
                select(TaskDetail).where(
                    TaskDetail.organization_id == organization, TaskDetail.task_id == task.id
                )
            )
            is None
        ):
            add(
                TaskDetail,
                "task-detail:" + str(index),
                task_id=task.id,
                priority=priority,
                deadline=now() + timedelta(days=index + 1),
                sprint_id=sprint.id,
            )
    period = today.strftime("%Y-%m")
    for index, (category, amount) in enumerate(
        (("cloud", "120"), ("tools", "80"), ("operations", "50"))
    ):
        add(
            CostRecord,
            "cost:" + str(index),
            period=period,
            department="DEMO Engineering",
            category=category,
            currency="USD",
            amount=Decimal(amount),
            source="manual",
        )
    if (
        db.scalar(
            select(Budget).where(
                Budget.organization_id == organization,
                Budget.period == period,
                Budget.currency == "USD",
            )
        )
        is None
    ):
        add(Budget, "budget", period=period, currency="USD", amount=Decimal("400"))
    for index, employee in enumerate(employees[:2]):
        add(
            Payroll,
            "payroll:" + str(index),
            employee_id=employee.id,
            period=period,
            currency="USD",
            gross=Decimal("1000"),
            deductions=Decimal("100"),
            net=Decimal("900"),
        )
        add(
            LeaveRequest,
            "leave:" + str(index),
            employee_id=employee.id,
            starts_on=today + timedelta(days=index + 3),
            ends_on=today + timedelta(days=index + 3),
            reason="DEMO fictional leave request for presentation; no real absence requested.",
            status="pending",
        )
    security_actor = Principal(analyst.user_id, organization, "security_analyst")
    tenant_context(db, organization, analyst.user_id)
    for index in range(2):
        simulate(db, security_actor, ident("security-scenario:" + str(index)))
    # Existing risk policy is reused; no policy or real observed event is invented.
    assessment = assess(
        RiskAssessmentInput(request_key="presentation-demo-v1", window_hours=168, synthetic=True),
        db,
        security_actor,
    )
    audit(db, actor, "presentation.fixture.seed_completed", organization)
    return {
        "organization_id": organization,
        "new_records": created,
        "synthetic_assessment_id": assessment.id,
        "fictional_auth_accounts_created": False,
        "external_emails_or_actions": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization", required=True, type=UUID)
    parser.add_argument("--apply-demo-data", required=True, action="store_true")
    parser.add_argument("--report", default="presentation-data-results.json")
    args = parser.parse_args()
    try:
        with SessionFactory.begin() as db:
            assert_runtime_role(db)
            result = populate(db, str(args.organization))
        from pathlib import Path

        Path(args.report).write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "committed": True,
                    "new_record_count": sum(map(len, result["new_records"].values())),
                    "synthetic_security": True,
                    "report": args.report,
                }
            )
        )
    except Exception as error:
        print(
            json.dumps(
                {
                    "committed": False,
                    "error_type": type(error).__name__,
                    "credentials_omitted": True,
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
