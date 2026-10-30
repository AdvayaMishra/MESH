"""Reviewed tenant-bound SCIM state changes; local rehire still needs owner activation."""

import json
import re
from time import monotonic

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.core.config import settings
from app.lifecycle_guards import require_reviewed_account
from app.models import Employee, IntegrationAccount, LifecyclePlan, Membership, now
from app.services import emit, scoped


class SCIMClient:
    def __init__(self, organization: str, client: httpx.Client | None = None):
        self.binding = settings().scim_bindings.get(organization)
        if self.binding is None:
            raise HTTPException(503, "SCIM is not configured for this organization")
        self.client = client

    def request(
        self,
        method: str,
        external_id: str,
        payload: dict | None = None,
        *,
        if_match: str | None = None,
    ) -> dict:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", external_id):
            raise HTTPException(422, "Invalid SCIM user identifier")
        return self._request(
            method,
            "Users/" + external_id,
            payload=payload,
            expected_statuses={200} if method == "GET" else {200, 204},
            if_match=if_match,
        )

    def _request(
        self,
        method: str,
        resource: str,
        *,
        payload: dict | None = None,
        params: dict | None = None,
        expected_statuses: set[int] | None = None,
        if_match: str | None = None,
    ) -> dict:
        valid = resource == "Users" and method in {"GET", "POST"}
        valid = (
            valid
            or bool(re.fullmatch(r"Users/[A-Za-z0-9][A-Za-z0-9_-]{0,127}", resource))
            and method in {"GET", "PATCH"}
        )
        if not valid:
            raise HTTPException(422, "Unsupported SCIM operation")
        binding = self.binding
        if binding is None:
            raise HTTPException(503, "SCIM is not configured")
        if if_match is not None:
            if_match = self.etag(if_match)
        if method == "PATCH" and binding.require_version and if_match is None:
            raise HTTPException(503, "SCIM conditional update requires a verified resource version")
        deadline = monotonic() + 20

        def receive(client):
            with client.stream(
                method,
                binding.base_url + "/" + resource,
                headers={
                    "Authorization": "Bearer " + binding.token.get_secret_value(),
                    "Accept": "application/scim+json",
                    "Content-Type": "application/scim+json",
                    "Accept-Encoding": "identity",
                    **({"If-Match": if_match} if if_match is not None else {}),
                },
                json=payload,
                params=params,
                timeout=10,
                follow_redirects=False,
            ) as response:
                response.raise_for_status()
                if expected_statuses is not None and response.status_code not in expected_statuses:
                    raise ValueError("Unexpected SCIM response status")
                if (
                    response.headers.get("content-encoding", "identity").strip().lower()
                    != "identity"
                    or monotonic() >= deadline
                ):
                    raise ValueError("SCIM response encoding or time bound exceeded")
                content = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() >= deadline or len(content) + len(chunk) > 131072:
                        raise ValueError("SCIM response time or size bound exceeded")
                    content.extend(chunk)
                if monotonic() >= deadline:
                    raise ValueError("SCIM response time bound exceeded")
                data = json.loads(content) if content else {}
                if not isinstance(data, dict):
                    raise ValueError("SCIM response is not an object")
                if method == "GET" and resource.startswith("Users/"):
                    etag = response.headers.get("etag")
                    if etag is not None:
                        etag = self.etag(etag)
                        meta = data.get("meta", {})
                        if not isinstance(meta, dict) or (
                            meta.get("version") is not None and meta["version"] != etag
                        ):
                            raise ValueError("SCIM header and resource versions disagree")
                        data = {**data, "meta": {**meta, "version": etag}}
                return data

        try:
            if self.client:
                return receive(self.client)
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                return receive(client)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 412:
                raise HTTPException(
                    409, "SCIM resource changed before conditional update"
                ) from None
            raise HTTPException(503, "SCIM operation failed or could not be verified") from None
        except (httpx.HTTPError, ValueError, RecursionError):
            raise HTTPException(503, "SCIM operation failed or could not be verified") from None

    @staticmethod
    def etag(value) -> str:
        if not isinstance(value, str) or not re.fullmatch(r'(?:W/)?"[!#-~]{1,128}"', value):
            raise HTTPException(503, "SCIM resource version is invalid")
        return value

    def user(self, external_id: str, expected_email: str) -> dict:
        data = self.request("GET", external_id)
        username = data.get("userName")
        if (
            data.get("id") != external_id
            or not isinstance(username, str)
            or username.strip().lower() != expected_email.strip().lower()
            or type(data.get("active")) is not bool
        ):
            raise HTTPException(409, "External account identity or activation state does not match")
        return data

    def set_active(self, external_id: str, expected_email: str, active: bool) -> None:
        if active and (self.binding is None or not self.binding.allow_activation):
            raise HTTPException(503, "SCIM activation is disabled for this organization")
        current = self.user(external_id, expected_email)
        if current["active"] is active:
            return
        meta = current.get("meta", {})
        version = meta.get("version") if isinstance(meta, dict) else None
        if version is not None:
            version = self.etag(version)
        self.request(
            "PATCH",
            external_id,
            {
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [{"op": "replace", "path": "active", "value": active}],
            },
            if_match=version,
        )
        if self.user(external_id, expected_email)["active"] is not active:
            raise HTTPException(503, "External account state is not yet verified")

    def revoke(self, external_id: str, expected_email: str) -> None:
        self.set_active(external_id, expected_email, False)

    def restore(self, external_id: str, expected_email: str) -> None:
        self.set_active(external_id, expected_email, True)


def revoke_scim(db: Session, organization: str, payload: dict) -> None:
    actor = Principal("lifecycle-worker", organization, "system")
    plan = scoped(db, LifecyclePlan, actor, payload["plan_id"], lock=True)
    if plan.status == "completed":
        return
    if plan.kind != "offboarding" or plan.status != "reconciliation_required":
        raise HTTPException(409, "Pending offboarding plan required")
    employee = scoped(db, Employee, actor, plan.employee_id)
    member = db.get(Membership, (organization, employee.user_id))
    approver = db.get(Membership, (organization, plan.approved_by))
    if (
        member is None
        or member.active
        or employee.status != "offboarded"
        or approver is None
        or not approver.active
        or approver.role != "owner"
        or plan.proposed_by == plan.approved_by
    ):
        raise HTTPException(409, "Local revocation and active independent approval required")
    account = scoped(db, IntegrationAccount, actor, payload["account_id"])
    if account.provider != "scim" or account.user_id != member.user_id:
        raise HTTPException(409, "External account does not belong to this employee")
    steps = plan.proposed["integrations"]
    step = next((step for step in steps if step["id"] == account.id), None)
    if step is None:
        raise HTTPException(409, "Account is absent from the reviewed access plan")
    if step["state"] in {"verified_revoked", "human_attested"}:
        return
    require_reviewed_account(step, account, member)
    SCIMClient(organization).revoke(account.external_id, member.email)
    plan.proposed = {
        **plan.proposed,
        "integrations": [
            {**item, "state": "verified_revoked"} if item["id"] == account.id else item
            for item in steps
        ],
    }
    plan.history = [
        *plan.history,
        {
            "action": "external_revocation_verified",
            "provider": "scim",
            "account_id": account.id,
            "actor": actor.user_id,
            "at": now().isoformat(),
        },
    ]
    if all(
        item["state"] in {"verified_revoked", "human_attested"}
        for item in plan.proposed["integrations"]
    ):
        plan.status = "completed"
    emit(db, actor, "employee.external_revocation.verified", plan.id)


def record_failure(db: Session, organization: str, payload: dict, terminal: bool) -> None:
    actor = Principal("lifecycle-worker", organization, "system")
    plan = db.scalar(
        select(LifecyclePlan).where(
            LifecyclePlan.organization_id == organization,
            LifecyclePlan.id == payload.get("plan_id"),
        )
    )
    if (
        plan is None
        or plan.status != "reconciliation_required"
        or plan.kind not in {"offboarding", "rehire"}
    ):
        return
    plan = scoped(db, LifecyclePlan, actor, plan.id, lock=True)
    operation = "external_restoration" if plan.kind == "rehire" else "external_revocation"
    state = "failed_manual_review_required" if terminal else "retrying"
    plan.proposed = {
        **plan.proposed,
        "integrations": [
            {**item, "state": state} if item["id"] == payload.get("account_id") else item
            for item in plan.proposed["integrations"]
        ],
    }
    plan.history = [
        *plan.history,
        {"action": operation + "_" + state, "actor": actor.user_id, "at": now().isoformat()},
    ]
    emit(db, actor, "employee." + operation + "." + state, plan.id)


def restore_scim(db: Session, organization: str, payload: dict) -> None:
    from app.rehire import review_rehire

    worker = Principal("lifecycle-worker", organization, "system")
    plan = scoped(db, LifecyclePlan, worker, payload["plan_id"], lock=True)
    if plan.status in {"completed", "cancelled", "rejected"}:
        return
    request = plan.proposed.get("restoration_request", {})
    if plan.kind != "rehire" or request.get("provider_sessions_revoked") is not True:
        raise HTTPException(409, "Explicit owner restoration request required")
    actor = Principal(str(request.get("actor", "")), organization, "owner")
    plan, employee, member = review_rehire(db, actor, plan.id)
    if employee is None or member is None:
        return
    account = scoped(db, IntegrationAccount, actor, payload["account_id"])
    if account.provider != "scim" or account.user_id != member.user_id:
        raise HTTPException(409, "External account does not belong to this employee")
    step = next((item for item in plan.proposed["integrations"] if item["id"] == account.id), None)
    if step is None:
        raise HTTPException(409, "External account is absent from the reviewed restoration")
    if step["state"] == "verified_restored":
        return
    require_reviewed_account(step, account, member)
    SCIMClient(organization).restore(account.external_id, member.email)
    plan.proposed = {
        **plan.proposed,
        "integrations": [
            {**item, "state": "verified_restored"} if item["id"] == account.id else item
            for item in plan.proposed["integrations"]
        ],
    }
    plan.history = [
        *plan.history,
        {
            "action": "external_restoration_verified",
            "provider": "scim",
            "account_id": account.id,
            "actor": "lifecycle-worker",
            "at": now().isoformat(),
        },
    ]
    emit(db, worker, "employee.external_restoration.verified", plan.id)
