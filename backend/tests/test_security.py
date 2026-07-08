"""White-box unit tests for password hashing and token minting."""

from app.models import User, Role
from app.security import create_token, hash_password, verify_password


def test_hash_is_salted_and_not_plaintext():
    h1 = hash_password("demo1234")
    h2 = hash_password("demo1234")
    assert "demo1234" not in h1
    assert h1 != h2  # fresh salt every time


def test_verify_roundtrip():
    stored = hash_password("s3cret!")
    assert verify_password("s3cret!", stored)


def test_verify_rejects_wrong_password():
    stored = hash_password("s3cret!")
    assert not verify_password("s3cret", stored)
    assert not verify_password("", stored)


def test_verify_rejects_malformed_stored_hash():
    # A corrupted DB value must fail closed, not crash.
    assert not verify_password("anything", "not-a-valid-hash")
    assert not verify_password("anything", "")


def test_tokens_are_unique_and_long(db):
    user = User(username="u", password_hash="x", name="U", role=Role.admin)
    db.add(user)
    db.flush()
    t1 = create_token(db, user)
    t2 = create_token(db, user)
    assert t1 != t2
    assert len(t1) == 64  # 32 random bytes, hex
