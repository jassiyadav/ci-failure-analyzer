import hashlib
import hmac

from app.security import verify_signature

SECRET = "s3cr3t"
BODY = b'{"action": "completed"}'


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature():
    assert verify_signature(SECRET, BODY, sign(BODY))


def test_tampered_body_rejected():
    assert not verify_signature(SECRET, BODY + b" ", sign(BODY))


def test_wrong_secret_rejected():
    assert not verify_signature(SECRET, BODY, sign(BODY, "other"))


def test_missing_or_malformed_header_rejected():
    assert not verify_signature(SECRET, BODY, None)
    assert not verify_signature(SECRET, BODY, "sha1=abc")
    assert not verify_signature("", BODY, sign(BODY, ""))  # empty secret must never validate
