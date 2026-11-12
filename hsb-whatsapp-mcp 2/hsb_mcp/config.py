from dataclasses import dataclass
import os
from pathlib import Path
import re
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    policy_file: Path
    public_url: str
    issuer: str
    jwks_url: str
    app_secret: str
    verify_token: str
    meta_access_token: str
    graph_version: str
    allowed_phone_ids: frozenset[str]
    max_webhook_bytes: int = 2_000_000
    max_media_bytes: int = 25_000_000

    @classmethod
    def from_env(cls):
        return cls(
            data_dir=Path(os.getenv("HSB_DATA_DIR", "./data")),
            policy_file=Path(os.getenv("HSB_ACCESS_POLICY", "./access-policy.json")),
            public_url=os.getenv("HSB_PUBLIC_URL", "").rstrip("/"),
            issuer=os.getenv("OAUTH_ISSUER", "").strip(),
            jwks_url=os.getenv("OAUTH_JWKS_URL", ""),
            app_secret=os.getenv("META_APP_SECRET", ""),
            verify_token=os.getenv("META_WEBHOOK_VERIFY_TOKEN", ""),
            meta_access_token=os.getenv("META_ACCESS_TOKEN", ""),
            graph_version=os.getenv("META_GRAPH_VERSION", ""),
            allowed_phone_ids=frozenset(
                p.strip() for p in os.getenv("META_PHONE_NUMBER_IDS", "").split(",") if p.strip()
            ),
        )

    @property
    def resource_url(self):
        return self.public_url + "/mcp"

    def validate_http(self):
        for label, value in [
            ("HSB_PUBLIC_URL", self.public_url),
            ("OAUTH_ISSUER", self.issuer),
            ("OAUTH_JWKS_URL", self.jwks_url),
        ]:
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
                raise ValueError(f"{label} must be your real HTTPS URL, without a query or fragment")
            if parsed.username or parsed.password:
                raise ValueError(f"Do not put credentials in {label}")
        if urlparse(self.public_url).path:
            raise ValueError("Use a dedicated origin in HSB_PUBLIC_URL, without a path")
        if not self.app_secret or len(self.verify_token) < 32:
            raise ValueError("Configure META_APP_SECRET and a random verify token of at least 32 characters")
        if not self.allowed_phone_ids or not all(p.isdigit() for p in self.allowed_phone_ids):
            raise ValueError("META_PHONE_NUMBER_IDS must contain your actual numeric phone-number IDs")
        if not re.fullmatch(r"v\d+\.\d+", self.graph_version):
            raise ValueError("Set META_GRAPH_VERSION to a supported version shown by your Meta app")
        if not self.policy_file.is_file():
            raise ValueError("Create the employee access-policy file before starting HTTP")
