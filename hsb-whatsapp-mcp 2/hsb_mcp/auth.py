import asyncio
import json
import time

import jwt
from mcp.server.auth.provider import AccessToken

from .config import Settings


def allowed_phones(settings: Settings, subject: str) -> set[str]:
    """Only a locally approved, immutable IdP subject can access an inbox."""
    policy = json.loads(settings.policy_file.read_text(encoding="utf-8"))
    grant = policy.get("employees", {}).get(subject, [])
    if not isinstance(grant, list) or not all(isinstance(p, str) for p in grant):
        return set()
    return set(grant) & set(settings.allowed_phone_ids)


class JWTVerifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jwks = jwt.PyJWKClient(settings.jwks_url, timeout=5, lifespan=300)

    def decode(self, token: str):
        key = self.jwks.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token, key, algorithms=["RS256"], audience=self.settings.resource_url,
            issuer=self.settings.issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
        )

    async def verify_token(self, token: str):
        try:
            claims = await asyncio.to_thread(self.decode, token)
            subject = claims.get("sub")
            scope = claims.get("scope", "")
            if not isinstance(subject, str) or not isinstance(scope, str):
                return None
            scopes = scope.split()
            if "whatsapp.read" not in scopes or not allowed_phones(self.settings, subject):
                return None
            if claims["exp"] <= time.time():
                return None
            return AccessToken(
                token=token, client_id=str(claims.get("azp", claims.get("client_id", "hsb-chatgpt"))),
                scopes=scopes, expires_at=int(claims["exp"]), subject=subject,
                resource=self.settings.resource_url,
            )
        except (jwt.PyJWTError, OSError, ValueError, TypeError):
            return None
