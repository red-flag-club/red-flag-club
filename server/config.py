"""Settings from the environment. Secrets never come from the repository."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from server import ROOT

PROVIDERS = ("tiingo", "massive", "payload", "fixture")
SCAN_SOURCES = ("off", "massive", "payload", "fixture")
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
MIN_TOKEN_LEN = 16


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    token: str | None = None
    host: str = "127.0.0.1"
    port: int = 8765
    provider: str = "tiingo"
    tiingo_key: str | None = None
    massive_key: str | None = None
    sec_contact: str | None = None
    data_dir: Path = ROOT / "data" / "server"
    payload_dir: Path | None = None
    allowed_hosts: tuple[str, ...] = field(default_factory=tuple)
    today_ttl_min: int = 240
    scan_source: str = "off"
    schedule: bool = False
    scan_times: tuple[str, ...] = ("10:00", "12:30", "15:00", "17:30")
    site_prices: bool = False                 # spec 006: off until the data licence is checked
    site_discussions: str | None = None       # e.g. https://github.com/red-flag-club/red-flag-club/discussions
    site_url: str | None = None               # spec 007: public URL, for social-share previews
    stories_submit_url: str | None = None     # spec 007: the Cloudflare Worker that takes stories
    turnstile_sitekey: str | None = None      # spec 007: optional bot check on the share form

    @classmethod
    def from_env(cls, env=os.environ) -> "Settings":
        hosts = tuple(h.strip() for h in env.get("PD_ALLOWED_HOSTS", "").split(",") if h.strip())
        return cls(
            token=env.get("PD_MCP_TOKEN") or None,
            host=env.get("PD_HOST", "127.0.0.1"),
            port=int(env.get("PD_PORT", "8765")),
            provider=env.get("PD_PROVIDER", "tiingo").lower(),
            tiingo_key=env.get("TIINGO_API_KEY") or None,
            massive_key=env.get("MASSIVE_API_KEY") or None,
            sec_contact=env.get("PD_SEC_CONTACT") or None,
            data_dir=Path(env.get("PD_DATA_DIR") or ROOT / "data" / "server"),
            payload_dir=Path(env["PD_PAYLOAD_DIR"]) if env.get("PD_PAYLOAD_DIR") else None,
            allowed_hosts=hosts,
            today_ttl_min=int(env.get("PD_TODAY_TTL_MIN", "240")),
            scan_source=env.get("PD_SCAN_SOURCE", "off").lower(),
            schedule=env.get("PD_SCHEDULE", "off").lower() in ("on", "1", "true", "yes"),
            scan_times=tuple(t.strip() for t in env.get("PD_SCAN_TIMES", "10:00,12:30,15:00,17:30").split(",")
                             if t.strip()),
            site_prices=env.get("PD_SITE_PRICES", "off").lower() in ("on", "1", "true", "yes"),
            site_discussions=env.get("PD_SITE_DISCUSSIONS") or None,
            site_url=env.get("PD_SITE_URL") or None,
            stories_submit_url=env.get("PD_STORIES_SUBMIT_URL") or None,
            turnstile_sitekey=env.get("PD_TURNSTILE_SITEKEY") or None,
        )

    def validate(self) -> "Settings":
        """FR-008: no token is only allowed when nothing outside this machine
        can reach the server."""
        if self.provider not in PROVIDERS:
            raise ConfigError(f"PD_PROVIDER must be one of {', '.join(PROVIDERS)}")
        if self.host not in LOCAL_HOSTS and not self.token:
            raise ConfigError(f"refusing to listen on {self.host} without PD_MCP_TOKEN")
        if self.token and len(self.token) < MIN_TOKEN_LEN:
            raise ConfigError(f"PD_MCP_TOKEN must be at least {MIN_TOKEN_LEN} characters")
        if self.provider == "tiingo" and not self.tiingo_key:
            raise ConfigError("PD_PROVIDER=tiingo needs TIINGO_API_KEY")
        if self.provider == "massive" and not self.massive_key:
            raise ConfigError("PD_PROVIDER=massive needs MASSIVE_API_KEY")
        if self.scan_source not in SCAN_SOURCES:
            raise ConfigError(f"PD_SCAN_SOURCE must be one of {', '.join(SCAN_SOURCES)}")
        if self.scan_source == "massive" and not self.massive_key:
            raise ConfigError("PD_SCAN_SOURCE=massive needs MASSIVE_API_KEY")
        if self.scan_source == "payload" and not self.payload_dir:
            raise ConfigError("PD_SCAN_SOURCE=payload needs PD_PAYLOAD_DIR")
        for t in self.scan_times:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
                raise ConfigError(f"PD_SCAN_TIMES entries must be HH:MM, got {t!r}")
        if self.schedule and self.scan_source == "off":
            raise ConfigError("PD_SCHEDULE=on needs a PD_SCAN_SOURCE")
        if self.provider == "payload" and not self.payload_dir:
            raise ConfigError("PD_PROVIDER=payload needs PD_PAYLOAD_DIR")
        for name, v in (("PD_SITE_DISCUSSIONS", self.site_discussions), ("PD_SITE_URL", self.site_url),
                        ("PD_STORIES_SUBMIT_URL", self.stories_submit_url)):
            if v and not v.startswith("https://"):
                raise ConfigError(f"{name} must be an https:// URL")
        return self

    @property
    def site_dir(self) -> Path:
        return self.data_dir / "site"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "pd.duckdb"
