"""Bounded S3 resource policy observations; no reachability or access decisions."""

from app.cloud_context_schema import Coverage
from app.cloud_iam_inventory import IAMInventory


class S3PolicyInventory:
    def __init__(self, client, graph, guard):
        self.client, self.graph, self.guard = client, graph, guard
        self.statements = IAMInventory(None, graph, guard)
        self.count = 0
        self.state = "complete"
        self.reason = None

    def bucket(self, name, node):
        try:
            self.guard()
            if node is None:
                raise ValueError("Bucket identity unresolved")
            document = self.client.get_bucket_policy(Bucket=name)["Policy"]
            self.statements.statements(node, document, "resource")
            self.count += 1
        except Exception as error:
            response = getattr(error, "response", {})
            code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
            if code == "NoSuchBucketPolicy":
                return
            self.state = "partial"
            self.reason = (
                "access_denied"
                if code in {"AccessDenied", "AccessDeniedException"}
                else "provider_unavailable"
            )
            if len(self.graph.errors) < 1000:
                self.graph.errors.append(self.reason)

    def finish(self, inventory_failed):
        state = "partial" if inventory_failed else self.state
        self.graph.layer_coverage["s3.resource_policies"] = Coverage.model_validate(
            {
                "scope": self.graph.scopes["s3"],
                "check": "s3.resource_policies",
                "state": state,
                "timestamps": self.graph.times(),
                "observed_count": self.count,
                "expected_total": None,
                "configured_limit": self.graph.max_nodes,
                "truncated": inventory_failed,
                "reason_code": self.reason or ("not_collected" if inventory_failed else None),
            }
        )
