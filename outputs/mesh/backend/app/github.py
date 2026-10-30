import time

import httpx
import jwt
from fastapi import HTTPException

from app.core.config import settings


class GitHubApp:
    def token(self, installation_id: int, organization_id: str) -> str:
        config = settings()
        if config.github_installations.get(str(installation_id)) != organization_id:
            raise HTTPException(403, "GitHub installation is not bound to this organization")
        if not config.github_app_id or not config.github_private_key:
            raise HTTPException(503, "GitHub App credentials are not configured")
        issued = int(time.time()) - 30
        try:
            assertion = jwt.encode(
                {"iat": issued, "exp": issued + 300, "iss": config.github_app_id},
                config.github_private_key.get_secret_value(),
                algorithm="RS256",
            )
        except (jwt.PyJWTError, ValueError):
            raise HTTPException(503, "GitHub App signing key is invalid") from None
        try:
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                response = client.post(
                    f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                    headers={
                        "Authorization": "Bearer " + assertion,
                        "Accept": "application/vnd.github+json",
                    },
                    json={"permissions": {"contents": "read"}},
                )
                response.raise_for_status()
                return str(response.json()["token"])
        except (httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(503, "GitHub installation token could not be obtained") from None

    def authorized(self, full_name: str, installation_id: int, organization_id: str) -> bool:
        token = self.token(installation_id, organization_id)
        try:
            with httpx.Client(timeout=10, follow_redirects=False) as client:
                # Installation token sees only repositories explicitly granted to this installation.
                result = client.get(
                    "https://api.github.com/repos/" + full_name,
                    headers={
                        "Authorization": "Bearer " + token,
                        "Accept": "application/vnd.github+json",
                    },
                )
                if result.status_code in {403, 404}:
                    return False
                result.raise_for_status()
                data = result.json()
                return data.get("full_name", "").lower() == full_name.lower() and not data.get(
                    "disabled", False
                )
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "Repository authorization unavailable") from None
