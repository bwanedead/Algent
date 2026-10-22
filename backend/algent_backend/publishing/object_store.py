"""
Object store — where every published object goes (docs/architecture/database-budget.md, "storage architecture").

The worker server is the system of record; the site reads only files from a public bucket. Two backends sit behind one tiny interface
(``put`` / ``get`` / ``head`` / ``delete`` / ``list``), chosen by ``database/flags.OBJECT_BACKEND``:

* ``R2Store``       Cloudflare R2 through its S3-compatible API. Requests are signed with **AWS Signature V4 implemented on the standard
                    library** (hmac + hashlib), so no SDK is installed. Egress from R2 is free, which is why it is the default.
* ``SupabaseStore`` Supabase Storage (the previous home), kept selectable so switching back is a flag, not a rewrite.

Environment NAMES (values never live in the repo; ``docs/credentials.md``):
``R2_ACCOUNT_ID``, ``R2_ACCESS_KEY_ID``, ``R2_SECRET_ACCESS_KEY``, ``R2_BUCKET``, ``R2_PUBLIC_BASE`` (the r2.dev or custom-domain URL the
site reads from). Supabase: ``SUPABASE_URL``, ``SUPABASE_SERVICE_ROLE_KEY``.

The transport is injectable (``call(method, url, headers, body) -> (status, headers, body)``) so tests need no network. Nothing here
raises on a missing configuration: ``select()`` returns None and the callers' contract (never raise into a run, no-op when unconfigured)
holds.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Protocol

Reply = tuple[int, dict[str, str], bytes]
#: ``call(method, url, headers, body) -> (status, response headers, response body)``.
Call = Callable[[str, str, dict[str, str], bytes], Reply]

#: Supabase Storage bucket (migration 006); R2 uses ``R2_BUCKET``.
SUPABASE_BUCKET = "published-assets"
_EMPTY_SHA = hashlib.sha256(b"").hexdigest()
USER_AGENT = "ohmega-publisher/1.0 (+https://www.ohmega.monster)"


def default_call(method: str, url: str, headers: dict[str, str], body: bytes) -> Reply:
    """The real transport: urllib, 30 s timeout. An HTTP error status is a reply, not an exception."""
    # Cloudflare answers 403 to urllib's default User-Agent on public r2.dev URLs, so every request names itself. (Not a signed header.)
    req = urllib.request.Request(url, data=body if body else None, method=method, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:   # noqa: S310 - https URL built from our own env
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, exc.read() if exc.fp else b""


# ── AWS Signature Version 4 (stdlib) ──────────────────────────────────────────────────────────────

def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, date: str, region: str, service: str) -> bytes:
    """The derived key: HMAC chain over date, region, service and ``aws4_request`` (AWS SigV4 spec)."""
    return _hmac(_hmac(_hmac(_hmac(("AWS4" + secret).encode("utf-8"), date), region), service), "aws4_request")


def _encode(value: str, *, keep_slash: bool) -> str:
    return urllib.parse.quote(value, safe="/-_.~" if keep_slash else "-_.~")


def canonical_request(method: str, path: str, query: Mapping[str, str], headers: Mapping[str, str], payload_hash: str) -> tuple[str, str]:
    """(canonical request, signed-headers list). Header names are lower-cased and sorted; values trimmed."""
    hdrs = {k.lower(): " ".join(str(v).split()) for k, v in headers.items()}
    names = sorted(hdrs)
    q = "&".join(f"{_encode(k, keep_slash=False)}={_encode(v, keep_slash=False)}" for k, v in sorted(query.items()))
    canon_headers = "".join(f"{n}:{hdrs[n]}\n" for n in names)
    signed = ";".join(names)
    return "\n".join([method, _encode(path, keep_slash=True), q, canon_headers, signed, payload_hash]), signed


def signature(method: str, path: str, query: Mapping[str, str], headers: Mapping[str, str], payload_hash: str, *, secret: str,
              region: str, service: str, amz_date: str) -> tuple[str, str]:
    """(signature hex, signed-headers list) for one request. ``amz_date`` is ``YYYYMMDDTHHMMSSZ``."""
    canon, signed = canonical_request(method, path, query, headers, payload_hash)
    day = amz_date[:8]
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canon.encode("utf-8")).hexdigest()])
    sig = hmac.new(signing_key(secret, day, region, service), to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return sig, signed


def authorization(method: str, path: str, query: Mapping[str, str], headers: Mapping[str, str], payload_hash: str, *, access_key: str,
                  secret: str, region: str, service: str, amz_date: str) -> str:
    """The ``Authorization`` header value."""
    sig, signed = signature(method, path, query, headers, payload_hash, secret=secret, region=region, service=service, amz_date=amz_date)
    scope = f"{amz_date[:8]}/{region}/{service}/aws4_request"
    return f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={sig}"


# ── the interface ─────────────────────────────────────────────────────────────────────────────────

class ObjectStore(Protocol):
    name: str
    ident: str

    def put(self, key: str, data: bytes, *, content_type: str, cache_control: str, content_encoding: str | None = None) -> int: ...
    def get(self, key: str) -> bytes | None: ...
    def head(self, key: str) -> dict[str, str] | None: ...
    def delete(self, key: str) -> bool: ...
    def list(self, prefix: str = "") -> list[dict[str, Any]]: ...
    def public_url(self, key: str) -> str: ...


class R2Store:
    """Cloudflare R2 over the S3 API (path-style, region ``auto``, service ``s3``)."""

    name = "r2"

    @property
    def ident(self) -> str:
        return f"r2:{self.bucket}"
    REGION = "auto"

    def __init__(self, account_id: str, access_key: str, secret: str, bucket: str, public_base: str, *, call: Call | None = None,
                 now: Callable[[], datetime] | None = None, host: str | None = None, meter: Any = None) -> None:
        self.bucket, self.public_base = bucket, public_base.rstrip("/")
        self.host = host or f"{account_id}.r2.cloudflarestorage.com"
        self._access, self._secret = access_key, secret
        self._call = call or default_call
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._meter = meter

    def _request(self, method: str, key: str = "", *, query: Mapping[str, str] | None = None, body: bytes = b"",
                 extra: Mapping[str, str] | None = None) -> Reply:
        path = f"/{self.bucket}/{key}" if key else f"/{self.bucket}"
        query = dict(query or {})
        payload = hashlib.sha256(body).hexdigest() if body else _EMPTY_SHA
        amz_date = self._now().strftime("%Y%m%dT%H%M%SZ")
        headers = {"Host": self.host, "x-amz-content-sha256": payload, "x-amz-date": amz_date, **(extra or {})}
        headers["Authorization"] = authorization(method, path, query, headers, payload, access_key=self._access, secret=self._secret,
                                                 region=self.REGION, service="s3", amz_date=amz_date)
        qs = "&".join(f"{_encode(k, keep_slash=False)}={_encode(v, keep_slash=False)}" for k, v in sorted(query.items()))
        url = f"https://{self.host}{_encode(path, keep_slash=True)}" + (f"?{qs}" if qs else "")
        return self._metered(method, key, url, headers, body)

    def meter(self) -> Any:
        if self._meter is None:
            from .object_budget import meter

            self._meter = meter()
        return self._meter

    def _metered(self, method: str, key: str, url: str, headers: dict[str, str], body: bytes) -> Reply:
        """The free-tier guard around every call (object_budget.py): refuse past the hard stop, otherwise count the call and the bytes."""
        from .object_budget import CLASS_A, CLASS_B

        m = self.meter()
        cls = CLASS_A if method in ("PUT", "DELETE") or (method == "GET" and not key) else CLASS_B
        if (reason := m.acquire(cls, len(body) if method == "PUT" else 0, key)):
            m.refuse(reason)
            return 429, {"x-ohmega-guard": reason}, b""
        reply = self._call(method, url, headers, body)
        if 200 <= reply[0] < 300 and method in ("PUT", "DELETE"):
            m.record(cls, key=key, size=len(body) if method == "PUT" else None, removed=method == "DELETE", count=False)
        return reply

    def put(self, key: str, data: bytes, *, content_type: str, cache_control: str, content_encoding: str | None = None) -> int:
        extra = {"Content-Type": content_type, "Cache-Control": cache_control}
        if content_encoding:
            extra["Content-Encoding"] = content_encoding
        return self._request("PUT", key, body=data, extra=extra)[0]

    def get(self, key: str) -> bytes | None:
        status, _, body = self._request("GET", key)
        return body if status == 200 else None

    def head(self, key: str) -> dict[str, str] | None:
        status, headers, _ = self._request("HEAD", key)
        return headers if status == 200 else None

    def delete(self, key: str) -> bool:
        return self._request("DELETE", key)[0] in (200, 204)

    def list(self, prefix: str = "") -> list[dict[str, Any]]:
        """Every object under ``prefix`` as ``{key, size, etag, modified}`` (follows continuation tokens)."""
        out: list[dict[str, Any]] = []
        token = ""
        while True:
            q = {"list-type": "2", "prefix": prefix}
            if token:
                q["continuation-token"] = token
            status, _, body = self._request("GET", query=q)
            if status != 200:
                raise RuntimeError(f"R2 list failed ({status})")
            root = ET.fromstring(body)
            ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
            for c in root.findall(f"{ns}Contents"):
                out.append({"key": c.findtext(f"{ns}Key", ""), "size": int(c.findtext(f"{ns}Size", "0") or 0),
                            "etag": (c.findtext(f"{ns}ETag", "") or "").strip('"'), "modified": c.findtext(f"{ns}LastModified", "")})
            if root.findtext(f"{ns}IsTruncated", "false") == "true":
                token = root.findtext(f"{ns}NextContinuationToken", "")
                if token:
                    continue
            return out

    def public_url(self, key: str) -> str:
        return f"{self.public_base}/{key.lstrip('/')}"


class SupabaseStore:
    """Supabase Storage (service-role key, server only). Kept for a one-line switch back; the public bucket is ``published-assets``."""

    name = "supabase"
    ident = "supabase"

    def __init__(self, url: str, service_key: str, *, call: Call | None = None) -> None:
        self.base, self._key = url.rstrip("/"), service_key
        self._call = call or default_call

    def _auth(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key}", "apikey": self._key, **(extra or {})}

    def put(self, key: str, data: bytes, *, content_type: str, cache_control: str, content_encoding: str | None = None) -> int:
        headers = self._auth({"x-upsert": "true", "Content-Type": content_type, "Cache-Control": cache_control})
        return self._call("POST", f"{self.base}/storage/v1/object/{SUPABASE_BUCKET}/{key}", headers, data)[0]

    def get(self, key: str) -> bytes | None:
        status, _, body = self._call("GET", self.public_url(key), {}, b"")
        return body if status == 200 else None

    def head(self, key: str) -> dict[str, str] | None:
        status, headers, _ = self._call("HEAD", self.public_url(key), {}, b"")
        return headers if status == 200 else None

    def delete(self, key: str) -> bool:
        return self._call("DELETE", f"{self.base}/storage/v1/object/{SUPABASE_BUCKET}/{key}", self._auth(), b"")[0] in (200, 204)

    def list(self, prefix: str = "") -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        folder, _, _ = prefix.rpartition("/")
        offset = 0
        while True:
            body = json.dumps({"prefix": folder, "limit": 1000, "offset": offset}).encode("utf-8")
            status, _, raw = self._call("POST", f"{self.base}/storage/v1/object/list/{SUPABASE_BUCKET}",
                                        self._auth({"Content-Type": "application/json"}), body)
            if status != 200:
                raise RuntimeError(f"Supabase list failed ({status})")
            rows = json.loads(raw or b"[]")
            for r in rows:
                if r.get("id"):
                    name = f"{folder}/{r['name']}" if folder else r["name"]
                    if name.startswith(prefix):
                        out.append({"key": name, "size": int((r.get("metadata") or {}).get("size", 0)), "etag": "", "modified": r.get("updated_at", "")})
            if len(rows) < 1000:
                return out
            offset += 1000

    def public_url(self, key: str) -> str:
        return f"{self.base}/storage/v1/object/public/{SUPABASE_BUCKET}/{key.lstrip('/')}"


# ── selection ─────────────────────────────────────────────────────────────────────────────────────

R2_ENV = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET", "R2_PUBLIC_BASE")
_OFF = ("0", "false", "no", "off")


def paused(env: Mapping[str, str] | None = None) -> bool:
    """``ALGENT_DB_PUBLISH=0`` (or ``ALGENT_PUBLISH=0``) switches every publish off, as it always did."""
    env = os.environ if env is None else env
    return any(env.get(k, "1").strip().lower() in _OFF for k in ("ALGENT_DB_PUBLISH", "ALGENT_PUBLISH"))


def select(backend: str | None = None, *, env: Mapping[str, str] | None = None, call: Call | None = None,
           allow_unconfigured: bool = False) -> ObjectStore | None:
    """The configured store for ``backend`` (default: the flag), or None when its env names are not all set (or publishing is paused).
    ``allow_unconfigured`` builds a store with empty credentials for tests that inject their own transport."""
    from algent_backend.database import flags

    env = os.environ if env is None else env
    backend = backend or flags.object_backend()
    if paused(env) and not allow_unconfigured:
        return None
    if backend == "supabase":
        url, key = env.get("SUPABASE_URL", "").strip(), env.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if (url and key) or allow_unconfigured:
            return SupabaseStore(url, key, call=call)
        return None
    vals = [env.get(k, "").strip() for k in R2_ENV]
    if all(vals) or allow_unconfigured:
        return R2Store(*vals, call=call)
    return None


def held_dir():
    """Server-local publish state (content-hash manifests, the article index): gitignored, never in the site checkout.
    ``ALGENT_PUBLISH_HELD`` overrides the location (tests)."""
    from pathlib import Path

    if (env := os.environ.get("ALGENT_PUBLISH_HELD", "").strip()):
        return Path(env)
    from .site_git import repo_root

    return repo_root() / "backend" / "publish_held"


def configured() -> bool:
    return select() is not None


def public_base(env: Mapping[str, str] | None = None) -> str:
    """The URL prefix the site reads from (what the site's ``NEXT_PUBLIC_DATA_BASE`` must equal)."""
    s = select(env=env, allow_unconfigured=True)
    return s.public_url("").rstrip("/") if s else ""
