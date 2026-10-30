"""Self-service TOTP adapter; Supabase remains the sole factor/OTP authority."""

from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

from app.api import DB, Who
from app.identity_provider import SupabaseAuth, Tokens, provider_tokens
from app.schemas import Input
from app.sessions import revoke_all

router = APIRouter(prefix="/api/v1/auth/mfa")
Authorization = Annotated[str, Header()]


class EnrollmentInput(Input):
    friendly_name: Annotated[str, Field(min_length=1, max_length=100)] = "MESH authenticator"


class TotpSecret(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    qr_code: str = Field(min_length=1, max_length=1048576, repr=False)
    secret: str = Field(min_length=16, max_length=256, repr=False)
    uri: str = Field(min_length=1, max_length=4096, repr=False)

    @model_validator(mode="after")
    def provisioning_uri(self):
        parts = urlsplit(self.uri)
        if (
            parts.scheme != "otpauth"
            or parts.netloc != "totp"
            or parse_qs(parts.query).get("secret") != [self.secret]
        ):
            raise ValueError("Invalid TOTP provisioning URI")
        return self


class EnrollmentOutput(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    id: UUID
    type: Literal["totp"]
    friendly_name: str = Field(max_length=100)
    totp: TotpSecret = Field(repr=False)


class FactorOutput(BaseModel):
    id: UUID
    factor_type: str = Field(max_length=30)
    friendly_name: str | None = Field(default=None, max_length=100)
    status: Literal["verified", "unverified"]


class FactorList(BaseModel):
    factors: list[FactorOutput] = Field(default_factory=list, max_length=100)


class ChallengeOutput(BaseModel):
    id: UUID
    expires_at: int = Field(gt=0)


class VerifyInput(Input):
    challenge_id: UUID
    code: SecretStr = Field(min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def digits(cls, value: SecretStr) -> SecretStr:
        if not all("0" <= char <= "9" for char in value.get_secret_value()):
            raise ValueError("TOTP code must contain six digits")
        return value


class UnenrollOutput(BaseModel):
    factor_id: UUID
    mesh_sessions_revoked: int
    requires_new_login: bool = True


def validated[T: BaseModel](model: type[T], data: dict) -> T:
    try:
        return model.model_validate(data)
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(503, "Identity provider returned invalid MFA metadata") from None


def factors(token: str) -> list[FactorOutput]:
    profile = SupabaseAuth().request("user", {}, token=token, method="GET")
    raw = profile.get("factors")
    return validated(FactorList, {"factors": [] if raw is None else raw}).factors


def own_totp(token: str, factor_id: UUID) -> FactorOutput:
    record = next((factor for factor in factors(token) if factor.id == factor_id), None)
    if record is None:
        raise HTTPException(404, "MFA factor not found")
    if record.factor_type != "totp":
        raise HTTPException(409, "This backend workflow supports TOTP factors only")
    return record


@router.get("/factors", response_model=list[FactorOutput])
def factor_list(who: Who, authorization: Authorization):
    return factors(authorization.split(" ", 1)[1])


@router.post("/enroll", response_model=EnrollmentOutput, status_code=201)
def enroll(data: EnrollmentInput, who: Who, authorization: Authorization):
    result = SupabaseAuth().request(
        "factors",
        {"factor_type": "totp", "issuer": "MESH", "friendly_name": data.friendly_name},
        token=authorization.split(" ", 1)[1],
    )
    return validated(EnrollmentOutput, result)


@router.post("/factors/{factor_id}/challenge", response_model=ChallengeOutput)
def challenge(factor_id: UUID, who: Who, authorization: Authorization):
    token = authorization.split(" ", 1)[1]
    own_totp(token, factor_id)
    return validated(
        ChallengeOutput, SupabaseAuth().request(f"factors/{factor_id}/challenge", {}, token=token)
    )


@router.post("/factors/{factor_id}/verify", response_model=Tokens)
def verify(factor_id: UUID, data: VerifyInput, who: Who, db: DB, authorization: Authorization):
    token = authorization.split(" ", 1)[1]
    own_totp(token, factor_id)
    result = SupabaseAuth().request(
        f"factors/{factor_id}/verify",
        {
            "challenge_id": str(data.challenge_id),
            "code": data.code.get_secret_value(),
        },
        token=token,
    )
    session = provider_tokens(result)
    revoke_all(db, who.user_id, keep=who.session_id, reason="mfa_verified")
    return session


@router.delete("/factors/{factor_id}", response_model=UnenrollOutput)
def unenroll(factor_id: UUID, who: Who, db: DB, authorization: Authorization):
    token = authorization.split(" ", 1)[1]
    record = own_totp(token, factor_id)
    if record.status == "verified" and who.aal != "aal2":
        raise HTTPException(
            403, "Current MFA assurance level 2 is required to remove a verified factor"
        )
    SupabaseAuth().request(f"factors/{factor_id}", {}, token=token, method="DELETE")
    count = (
        revoke_all(db, who.user_id, reason="mfa_factor_removed")
        if record.status == "verified"
        else 0
    )
    return UnenrollOutput(
        factor_id=factor_id,
        mesh_sessions_revoked=count,
        requires_new_login=record.status == "verified",
    )
