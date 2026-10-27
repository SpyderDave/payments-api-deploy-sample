import hashlib
import hmac
import os

os.environ["PAYMENTS_WEBHOOK_SECRET"] = "s3cret"

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import main  # noqa: E402

# Skip the DB-backed lifespan: these tests only exercise paths that never reach Postgres.
main.app.router.lifespan_context = FastAPI().router.lifespan_context
client = TestClient(main.app)


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz():
    assert client.get("/readyz").status_code == 200


def test_webhook_rejects_bad_signature():
    r = client.post("/webhooks/payments", content=b"{}", headers={"x-signature": "nope", "x-event-id": "e1"})
    assert r.status_code == 401


def test_signature_check():
    sig = hmac.new(b"s3cret", b"{}", hashlib.sha256).hexdigest()
    assert main.valid_signature(b"{}", sig)
    assert not main.valid_signature(b"{}", "")
