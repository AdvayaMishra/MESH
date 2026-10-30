"""Inactive SCIM creation adapter. A durable caller must reserve each POST first."""

import re

from fastapi import HTTPException

from app.lifecycle_integrations import SCIMClient


class ProvisioningSCIMClient(SCIMClient):
    def collection(
        self, method: str, *, payload: dict | None = None, params: dict | None = None
    ) -> dict:
        if self.binding is None or not self.binding.allow_provisioning:
            raise HTTPException(503, "SCIM provisioning is disabled for this organization")
        return self._request(
            method,
            "Users",
            payload=payload,
            params=params,
            expected_statuses={201} if method == "POST" else {200},
        )

    def confirmed(
        self, external_id: str, email: str, subject: str, *, inactive: bool = True
    ) -> dict:
        data = self.user(external_id, email)
        if data.get("externalId") != subject or (inactive and data["active"] is not False):
            raise HTTPException(409, "Provisioning identity or inactive state does not match")
        return {"id": data["id"], "active": data["active"]}

    def find(self, subject: str, email: str, *, inactive: bool = True) -> dict | None:
        if not re.fullmatch(r"mesh:[a-f0-9-]{36}:[a-f0-9-]{36}", subject):
            raise HTTPException(422, "Invalid provisioning subject")
        data = self.collection(
            "GET", params={"filter": 'externalId eq "' + subject + '"', "count": 2}
        )
        count, rows = data.get("totalResults"), data.get("Resources")
        if (
            type(count) is not int
            or count not in {0, 1}
            or not isinstance(rows, list)
            or len(rows) != count
        ):
            raise HTTPException(409, "Provisioning discovery is incomplete or ambiguous")
        if not count:
            return None
        resource = rows[0]
        if not isinstance(resource, dict) or not isinstance(resource.get("id"), str):
            raise HTTPException(503, "Provisioning result has no verified resource identifier")
        return self.confirmed(resource["id"], email, subject, inactive=inactive)

    def create_inactive(self, subject: str, email: str) -> dict:
        data = self.collection(
            "POST",
            payload={
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                "userName": email,
                "externalId": subject,
                "active": False,
            },
        )
        if not isinstance(data.get("id"), str):
            raise HTTPException(503, "Created account could not be verified")
        return self.confirmed(data["id"], email, subject)
