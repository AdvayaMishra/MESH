"""Validate AWS role/session identity before any tenant inventory access."""

import re
from dataclasses import dataclass
from typing import Literal, cast

_ROLE = re.compile(r"arn:(aws|aws-us-gov|aws-cn):iam::([0-9]{12}):role/([\w+=,.@/-]+)", re.ASCII)


@dataclass(frozen=True)
class AWSAccountIdentity:
    partition: Literal["aws", "aws-us-gov", "aws-cn"]
    account_id: str
    role_arn: str

    @classmethod
    def from_role(cls, role_arn: str) -> "AWSAccountIdentity":
        match = _ROLE.fullmatch(role_arn)
        if not match or len(role_arn) > 2048 or "//" in match[3] or match[3].endswith("/"):
            raise ValueError("Invalid operator-bound AWS role")
        return cls(cast(Literal["aws", "aws-us-gov", "aws-cn"], match[1]), match[2], role_arn)

    def verify_session(self, assumed_user: dict, caller: dict) -> None:
        """Compare independently queried credentials with the actual AssumeRole response.

        IAM role paths cannot be compared directly with STS session ARN paths.
        The returned assumed-role identity binds the target credential query instead.
        """
        arn = assumed_user.get("Arn")
        user_id = assumed_user.get("AssumedRoleId")
        prefix = f"arn:{self.partition}:sts::{self.account_id}:assumed-role/"
        role_name = self.role_arn.rsplit("/", 1)[1]
        if (
            not isinstance(arn, str)
            or not arn.startswith(prefix + role_name + "/")
            or arn[len(prefix) :].count("/") != 1
            or not arn.rsplit("/", 1)[1]
            or not isinstance(user_id, str)
            or not re.fullmatch(r"AROA[A-Z0-9]+:[\w+=,.@-]+", user_id, re.ASCII)
            or user_id.split(":", 1)[1] != arn.rsplit("/", 1)[1]
            or caller.get("Account") != self.account_id
            or caller.get("Arn") != arn
            or caller.get("UserId") != user_id
        ):
            raise ValueError("AWS assumed session identity mismatch")
