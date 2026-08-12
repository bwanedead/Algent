"""
Posting to X — the write half of our X integration.

Reads use an app-only **bearer token**, which cannot post: bearer identifies the app, and
``POST /2/tweets`` needs to know which ACCOUNT is speaking. So writes use OAuth 1.0a user
context, and the two sets of credentials are deliberately separate — reads run on one account's
bearer, writes on the site account's tokens, and neither can be mistaken for the other.

OAuth 1.0a is signed here rather than via a library because none is installed. It is short and
fully specified (RFC 5849), and the alternative — OAuth 2.0 with refresh-token rotation — buys
nothing for a single fixed account that never needs a consent screen.

Every write asserts WHO IT IS FIRST. A credential that quietly resolves to the wrong account
would publish under someone else's name, which is not a failure we can take back.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TWEETS_ENDPOINT = "https://api.x.com/2/tweets"
_ME_ENDPOINT = "https://api.x.com/2/users/me"
_MEDIA_ENDPOINT = "https://upload.twitter.com/1.1/media/upload.json"
_TIMEOUT_S = 30.0
_MEDIA_TIMEOUT_S = 60.0

#: The write credentials. Distinct from X_BEARER_TOKEN, which is read-only app auth.
_ENV = ("X_API_KEY", "X_API_KEY_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
_HANDLE_ENV = "X_POST_HANDLE"

#: t.co rewrites every link to a fixed width, so a long URL costs the same as a short one and
#: the raw string length is not what X counts.
TCO_LEN = 23
#: Timeline card before "Show more". Radar still writes to this size on purpose — one thought.
#: It is not a write ceiling.
CARD = 280
#: What POST /2/tweets accepts for Premium long posts. The API raised this from 4k to 25k.
#: Articles (~100k, formatted) are a different UI product and are not this endpoint.
#: We do not invent a 280 cap on top of X's actual limit.
LIMIT = 25_000


class XWriteError(RuntimeError):
    """A write could not be attempted or was refused."""


@dataclass(frozen=True)
class Posted:
    id: str
    text: str
    url: str


def write_configured() -> bool:
    """True when every write credential is present. Never touches the values.

    Imports the config package first because that is what loads backend/.env — without it a
    caller that has not already touched config sees no credentials and concludes, wrongly, that
    posting is unconfigured.
    """
    import algent_backend.config  # noqa: F401 — imported for the .env side effect

    return all(os.environ.get(name) for name in _ENV)


def _quote(value: str) -> str:
    return urllib.parse.quote(str(value), safe="~")


def _auth_header(method: str, url: str, *, params: dict[str, str] | None = None) -> str:
    """RFC 5849 HMAC-SHA1. A JSON body is NOT signed — only the query params and oauth fields."""
    missing = [name for name in _ENV if not os.environ.get(name)]
    if missing:
        raise XWriteError(f"missing X write credentials: {', '.join(missing)}")
    oauth = {
        "oauth_consumer_key": os.environ["X_API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": os.environ["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    norm = "&".join(
        f"{_quote(k)}={_quote(v)}" for k, v in sorted({**oauth, **(params or {})}.items())
    )
    base = "&".join([method.upper(), _quote(url), _quote(norm)])
    key = f'{_quote(os.environ["X_API_KEY_SECRET"])}&{_quote(os.environ["X_ACCESS_TOKEN_SECRET"])}'
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest(),
    ).decode()
    return "OAuth " + ", ".join(f'{_quote(k)}="{_quote(v)}"' for k, v in sorted(oauth.items()))


def whoami() -> str:
    """The handle these credentials actually post as. Raises rather than guessing."""
    import httpx

    resp = httpx.get(
        _ME_ENDPOINT, headers={"Authorization": _auth_header("GET", _ME_ENDPOINT)},
        timeout=_TIMEOUT_S,
    )
    if resp.status_code != 200:
        raise XWriteError(f"identity check failed ({resp.status_code}): {resp.text[:200]}")
    return str((resp.json().get("data") or {}).get("username") or "")


def assert_identity() -> str:
    """Confirm the tokens speak for the configured account, and return the handle.

    The cheap guard against the expensive mistake. Credentials get rotated, copied between
    apps and pasted into the wrong line; every one of those failures looks like success until
    something lands on a stranger's timeline.
    """
    expected = (os.environ.get(_HANDLE_ENV) or "").lstrip("@")
    actual = whoami()
    if expected and actual.lower() != expected.lower():
        raise XWriteError(
            f"these credentials post as @{actual}, not the configured @{expected} — refusing",
        )
    return actual


def billable_length(text: str) -> int:
    """X's count, not Python's: every URL costs TCO_LEN however long it reads."""
    out = 0
    for token in text.split(" "):
        stripped = token.strip()
        if stripped.startswith(("http://", "https://")):
            out += TCO_LEN + 1
        else:
            out += len(token) + 1
    return max(0, out - 1)


def upload_media(path: str | os.PathLike[str]) -> str:
    """Upload an image and return the media_id the tweets endpoint expects.

    X still takes image bytes on the v1.1 upload host; v2 create-post then attaches
    the id. A missing file or a non-image is a write error, not a silent skip.
    """
    import httpx

    file_path = Path(path)
    if not file_path.is_file():
        raise XWriteError(f"media file not found: {file_path}")
    suffix = file_path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".webp": "image/webp"}.get(suffix)
    if mime is None:
        raise XWriteError(f"unsupported media type: {file_path.suffix}")

    with file_path.open("rb") as fh:
        resp = httpx.post(
            _MEDIA_ENDPOINT,
            headers={"Authorization": _auth_header("POST", _MEDIA_ENDPOINT)},
            files={"media": (file_path.name, fh, mime)},
            timeout=_MEDIA_TIMEOUT_S,
        )
    if resp.status_code not in (200, 201):
        raise XWriteError(f"media upload failed ({resp.status_code}): {resp.text[:200]}")
    media_id = str((resp.json() or {}).get("media_id_string") or (resp.json() or {}).get("media_id") or "")
    if not media_id:
        raise XWriteError("media upload returned no media_id")
    return media_id


def post(text: str, *, media_ids: list[str] | None = None,
         verify_identity: bool = True) -> Posted:
    """Publish one post. Raises XWriteError on anything short of success."""
    import httpx

    if not text.strip():
        raise XWriteError("refusing to post empty text")
    length = billable_length(text)
    if length > LIMIT:
        raise XWriteError(
            f"post is {length} characters, over X's {LIMIT} long-post limit"
        )

    handle = assert_identity() if verify_identity else (
        os.environ.get(_HANDLE_ENV) or "").lstrip("@")

    payload: dict[str, Any] = {"text": text}
    if media_ids:
        payload["media"] = {"media_ids": [str(m) for m in media_ids]}

    resp = httpx.post(
        _TWEETS_ENDPOINT,
        headers={
            "Authorization": _auth_header("POST", _TWEETS_ENDPOINT),
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=_TIMEOUT_S,
    )
    if resp.status_code not in (200, 201):
        hint = ""
        if resp.status_code == 403 and "oauth1-permissions" in resp.text:
            # Worth naming: the app setting alone never reaches tokens that already exist.
            hint = (" — app permissions are baked into the access token when it is created, so "
                    "the token must be REGENERATED after setting Read and Write")
        raise XWriteError(f"post failed ({resp.status_code}): {resp.text[:200]}{hint}")

    data = resp.json().get("data") or {}
    tid = str(data.get("id") or "")
    return Posted(id=tid, text=str(data.get("text") or text),
                  url=f"https://x.com/{handle}/status/{tid}")
