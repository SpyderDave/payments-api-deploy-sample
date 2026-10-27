"""Sample payments-api service (stand-in for the real app; used to ground the manifests)."""
import hashlib
import hmac
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Header, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

WEBHOOK_SECRET = os.environ.get("PAYMENTS_WEBHOOK_SECRET", "")
POOL_MAX = int(os.environ.get("DB_POOL_MAX", "10"))

webhooks_total = Counter("webhooks_total", "Webhooks received", ["result"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pool size is explicit: replicas x DB_POOL_MAX must stay under Postgres max_connections.
    app.state.pool = await asyncpg.create_pool(
        os.environ["DATABASE_URL"], min_size=1, max_size=POOL_MAX, command_timeout=5
    )
    yield
    await app.state.pool.close()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    """Liveness: process is up. Deliberately does not touch the DB."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """Readiness: shallow on purpose. A DB blip should degrade, not remove every pod from the LB."""
    return {"status": "ready"}


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/v1/orders/{order_id}")
async def get_order(order_id: int, request: Request):
    row = await request.app.state.pool.fetchrow(
        "SELECT id, status, amount_cents FROM orders WHERE id = $1", order_id
    )
    if row is None:
        raise HTTPException(404, "order not found")
    return dict(row)


def valid_signature(body: bytes, signature: str) -> bool:
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@app.post("/webhooks/payments", status_code=202)
async def payments_webhook(
    request: Request,
    x_signature: str = Header(default=""),
    x_event_id: str = Header(default=""),
):
    body = await request.body()
    if not WEBHOOK_SECRET or not valid_signature(body, x_signature):
        webhooks_total.labels("bad_signature").inc()
        raise HTTPException(401, "bad signature")
    if not x_event_id:
        raise HTTPException(400, "missing event id")

    # Providers retry and deliver duplicates: dedupe on event id so processing is idempotent.
    inserted = await request.app.state.pool.fetchval(
        "INSERT INTO webhook_events (event_id, payload) VALUES ($1, $2) "
        "ON CONFLICT (event_id) DO NOTHING RETURNING 1",
        x_event_id,
        body.decode(),
    )
    webhooks_total.labels("accepted" if inserted else "duplicate").inc()
    return {"accepted": True}
