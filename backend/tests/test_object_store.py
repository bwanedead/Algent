"""Object store: SigV4 against AWS's published test vectors, the R2 request shapes, backend selection, hash-skip uploads. No network."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from algent_backend.publishing import asset_store, object_store

SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
R2_ENV = {"R2_ACCOUNT_ID": "acct", "R2_ACCESS_KEY_ID": "AKID", "R2_SECRET_ACCESS_KEY": "sek", "R2_BUCKET": "ohmega", "R2_PUBLIC_BASE": "https://pub-x.r2.dev/"}


def test_sigv4_get_object_vector() -> None:
    """AWS docs, 'Example: GET Object' (Range header), us-east-1."""
    sig, signed = object_store.signature(
        "GET", "/test.txt", {}, {"Host": "examplebucket.s3.amazonaws.com", "Range": "bytes=0-9", "x-amz-content-sha256": EMPTY,
                                 "x-amz-date": "20130524T000000Z"}, EMPTY, secret=SECRET, region="us-east-1", service="s3", amz_date="20130524T000000Z")
    assert signed == "host;range;x-amz-content-sha256;x-amz-date"
    assert sig == "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"


def test_sigv4_list_objects_vector() -> None:
    """AWS docs, 'Example: GET Bucket (List Objects)' (query string)."""
    sig, _ = object_store.signature(
        "GET", "/", {"max-keys": "2", "prefix": "J"}, {"Host": "examplebucket.s3.amazonaws.com", "x-amz-content-sha256": EMPTY,
                                                       "x-amz-date": "20130524T000000Z"}, EMPTY, secret=SECRET, region="us-east-1",
        service="s3", amz_date="20130524T000000Z")
    assert sig == "34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"


def test_sigv4_put_object_vector() -> None:
    """AWS docs, 'Example: PUT Object' (a key needing percent-encoding, extra signed headers)."""
    body = b"Welcome to Amazon S3."
    h = hashlib.sha256(body).hexdigest()
    assert h == "44ce7dd67c959e0d3524ffac1771dfbba87d2b6b4b4e99e42034a8b803f8b072"
    sig, signed = object_store.signature(
        "PUT", "/test$file.text", {}, {"Host": "examplebucket.s3.amazonaws.com", "Date": "Fri, 24 May 2013 00:00:00 GMT",
                                       "x-amz-date": "20130524T000000Z", "x-amz-storage-class": "REDUCED_REDUNDANCY", "x-amz-content-sha256": h},
        h, secret=SECRET, region="us-east-1", service="s3", amz_date="20130524T000000Z")
    assert signed == "date;host;x-amz-content-sha256;x-amz-date;x-amz-storage-class"
    assert sig == "98ad721746da40c64f1a55b78f14c238d841ea1380cd77a1b5971af0ece108bd"


def test_signing_key_vector() -> None:
    """AWS docs, 'Deriving a signing key' (IAM example)."""
    assert object_store.signing_key("wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "20120215", "us-east-1", "iam").hex() == \
        "f4780e2d9f65fa895f9c67b32ce1baf0b0d8a43505a000a1a9e090d414db404d"


class FakeCall:
    def __init__(self, status: int = 200, body: bytes = b"", headers: dict | None = None) -> None:
        self.calls: list[tuple[str, str, dict, bytes]] = []
        self.status, self.body, self.headers = status, body, headers or {}

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        return self.status, self.headers, self.body


def _r2(call: FakeCall) -> object_store.R2Store:
    return object_store.R2Store("acct", "AKID", "sek", "ohmega", "https://pub-x.r2.dev/", call=call,
                                now=lambda: datetime(2026, 10, 22, 12, 0, 0, tzinfo=timezone.utc))


def test_r2_put_is_a_signed_path_style_request_with_cache_and_encoding() -> None:
    call = FakeCall()
    status = _r2(call).put("docs/daily/x.json.gz", b"abc", content_type="application/gzip", cache_control="public, max-age=60",
                           content_encoding=None)
    method, url, headers, body = call.calls[0]
    assert status == 200 and method == "PUT" and body == b"abc"
    assert url == "https://acct.r2.cloudflarestorage.com/ohmega/docs/daily/x.json.gz"
    assert headers["Content-Type"] == "application/gzip" and headers["Cache-Control"] == "public, max-age=60"
    assert headers["x-amz-content-sha256"] == hashlib.sha256(b"abc").hexdigest() and headers["x-amz-date"] == "20261022T120000Z"
    auth = headers["Authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKID/20261022/auto/s3/aws4_request, SignedHeaders=")
    assert "cache-control;content-type;host;x-amz-content-sha256;x-amz-date" in auth
    call2 = FakeCall()
    _r2(call2).put("a.json", b"{}", content_type="application/json", cache_control="x", content_encoding="gzip")
    assert call2.calls[0][2]["Content-Encoding"] == "gzip" and "content-encoding" in call2.calls[0][2]["Authorization"]


def test_r2_get_head_delete_and_public_url() -> None:
    assert _r2(FakeCall(200, b"hello")).get("k") == b"hello"
    assert _r2(FakeCall(404)).get("k") is None
    assert _r2(FakeCall(200, headers={"etag": "x"})).head("k") == {"etag": "x"}
    assert _r2(FakeCall(404)).head("k") is None
    d = FakeCall(204)
    assert _r2(d).delete("k") is True and d.calls[0][0] == "DELETE"
    assert _r2(FakeCall()).public_url("/docs/a.gz") == "https://pub-x.r2.dev/docs/a.gz"


def test_r2_list_follows_continuation_tokens() -> None:
    page1 = (b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>true</IsTruncated>'
             b'<NextContinuationToken>T1</NextContinuationToken><Contents><Key>a/1</Key><Size>3</Size><ETag>"e1"</ETag></Contents></ListBucketResult>')
    page2 = (b'<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><IsTruncated>false</IsTruncated>'
             b'<Contents><Key>a/2</Key><Size>5</Size><ETag>"e2"</ETag></Contents></ListBucketResult>')
    pages = [page1, page2]

    def call(method, url, headers, body):
        return 200, {}, pages.pop(0)

    seen = []

    def spy(method, url, headers, body):
        seen.append(url)
        return call(method, url, headers, body)

    rows = _r2(FakeCall()).__class__("acct", "AKID", "sek", "ohmega", "https://p", call=spy).list("a/")
    assert [r["key"] for r in rows] == ["a/1", "a/2"] and rows[1]["size"] == 5
    assert "continuation-token=T1" in seen[1] and "list-type=2" in seen[0] and "prefix=a%2F" in seen[0]


def test_select_follows_the_flag_and_needs_every_name(monkeypatch) -> None:
    assert object_store.select("r2", env={}) is None
    assert object_store.select("r2", env={k: v for k, v in R2_ENV.items() if k != "R2_BUCKET"}) is None
    s = object_store.select("r2", env=R2_ENV)
    assert s is not None and s.name == "r2" and s.public_url("x") == "https://pub-x.r2.dev/x"
    sup = object_store.select("supabase", env={"SUPABASE_URL": "https://a.supabase.co/", "SUPABASE_SERVICE_ROLE_KEY": "k"})
    assert sup is not None and sup.public_url("a/b") == "https://a.supabase.co/storage/v1/object/public/published-assets/a/b"
    assert object_store.select("r2", env={**R2_ENV, "ALGENT_DB_PUBLISH": "0"}) is None            # paused
    monkeypatch.setenv("ALGENT_OBJECT_BACKEND", "supabase")
    from algent_backend.database import flags

    assert flags.object_backend() == "supabase"


def test_asset_upload_through_r2_skips_unchanged_content(monkeypatch, tmp_path) -> None:
    for k, v in R2_ENV.items():
        monkeypatch.setenv(k, v)
    call = FakeCall()
    manifest = tmp_path / "m.json"
    out = asset_store.upload({"/analytics/s/hero.webp": b"img"}, http=lambda m, u, h, b: call(m, u, h, b)[0], manifest=manifest)
    assert out == {"assets": 1, "skipped": 0, "failed": [], "ok": True}
    m, url, headers, _ = call.calls[0]
    assert m == "PUT" and url == "https://acct.r2.cloudflarestorage.com/ohmega/analytics/s/hero.webp" and headers["Content-Type"] == "image/webp"
    again = asset_store.upload({"/analytics/s/hero.webp": b"img"}, http=lambda m, u, h, b: call(m, u, h, b)[0], manifest=manifest)
    assert again["skipped"] == 1 and len(call.calls) == 1
    bad = asset_store.upload({"/x/y.png": b"1"}, http=lambda *a: 403, manifest=manifest)
    assert bad["ok"] is False and bad["failed"] == ["/x/y.png (403)"]
    assert asset_store.public_url("/analytics/s/hero.webp") == "https://pub-x.r2.dev/analytics/s/hero.webp"


def test_noop_without_r2_names(monkeypatch) -> None:
    for k in object_store.R2_ENV:
        monkeypatch.delenv(k, raising=False)
    out = asset_store.upload({"/a/b.png": b"x"})
    assert out["ok"] is True and out["assets"] == 0 and "off" in out["note"]
    assert asset_store.enabled() is False


@pytest.mark.parametrize("key", ["a b/c.json", "ü/x.json", "plain/x.json"])
def test_keys_are_percent_encoded_in_the_request_path(key) -> None:
    call = FakeCall()
    _r2(call).put(key, b"1", content_type="application/json", cache_control="x")
    url = call.calls[0][1]
    assert " " not in url and "ü" not in url
