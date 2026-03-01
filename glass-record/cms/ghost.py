"""Ghost Admin API client — wired in MVP 6."""
import time

import httpx
import jwt
from pydantic_settings import BaseSettings


class GhostSettings(BaseSettings):
    ghost_admin_url: str = "http://localhost:2368"
    ghost_admin_api_key: str = "id:secret"  # format: "<id>:<hex-secret>"


class GhostClient:
    def __init__(self) -> None:
        s = GhostSettings()
        self.base_url = s.ghost_admin_url.rstrip("/") + "/ghost/api/admin"
        key_id, key_secret = s.ghost_admin_api_key.split(":", 1)
        self._key_id = key_id
        self._key_secret = bytes.fromhex(key_secret)

    def _make_token(self) -> str:
        iat = int(time.time())
        payload = {"iat": iat, "exp": iat + 300, "aud": "/admin/"}
        return jwt.encode(
            payload,
            self._key_secret,
            algorithm="HS256",
            headers={"kid": self._key_id},
        )

    async def create_post(
        self,
        title: str,
        html: str,
        status: str = "published",
        tags: list[str] | None = None,
    ) -> dict:
        headers = {"Authorization": f"Ghost {self._make_token()}"}
        payload = {
            "posts": [
                {
                    "title": title,
                    "html": html,
                    "status": status,
                    "tags": [{"name": t} for t in (tags or [])],
                }
            ]
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base_url}/posts/", json=payload, headers=headers
            )
            r.raise_for_status()
        return r.json()["posts"][0]
