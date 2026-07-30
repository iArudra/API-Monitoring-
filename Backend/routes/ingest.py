"""
POST /api/v1/events         - single event
POST /api/v1/events/batch   - list of events (preferred — Person A's
                               agent should batch and send every few
                               seconds, not one HTTP call per API call
                               it observes. One call per observed call
                               will drown this endpoint under real load.)

Expected event JSON shape (this IS the contract Person A codes against):
{
  "ts": "2026-08-05T14:32:01.123Z",     // ISO8601, required
  "source_env": "dev",                   // required
  "agent_id": "agent-dev-01",            // optional
  "target_service": "stripe",            // required
  "endpoint": "/v1/charges",             // optional
  "method": "POST",                      // optional
  "status_code": 200,                    // optional, null if no response
  "latency_ms": 142.5,                   // optional, null if timed out
  "payload_size_b": 1024,                // optional
  "error_type": null,                    // "timeout"|"connection_error"|"http_error"|null
  "error_message": null
}
"""
from flask import Blueprint, request, jsonify, current_app
from db import get_pool
from config import config
import uuid

bp = Blueprint("ingest", __name__, url_prefix="/api/v1")

REQUIRED_FIELDS = ("ts", "source_env", "target_service")

INSERT_SQL = """
    INSERT INTO events (
        event_id, ts, source_env, agent_id, target_service, endpoint,
        method, status_code, latency_ms, payload_size_b, error_type, error_message
    ) VALUES (
        %(event_id)s, %(ts)s, %(source_env)s, %(agent_id)s, %(target_service)s,
        %(endpoint)s, %(method)s, %(status_code)s, %(latency_ms)s,
        %(payload_size_b)s, %(error_type)s, %(error_message)s
    )
"""


def _check_auth(source_env):
    """
    Per-environment API key check. Header: X-Agent-Key
    Skipped entirely if AGENT_API_KEYS isn't configured, so you can get
    the pipeline working end-to-end before wiring auth — but don't ship
    the demo without it configured.
    """
    keys = config.agent_keys_by_env
    if not keys:
        return True  # auth not configured yet — allow through
    provided = request.headers.get("X-Agent-Key", "")
    expected = keys.get(source_env)
    return expected is not None and provided == expected


def _validate(event):
    missing = [f for f in REQUIRED_FIELDS if not event.get(f)]
    if missing:
        return f"missing required fields: {', '.join(missing)}"
    return None


def _normalize(event):
    """Fills defaults so the INSERT never chokes on a missing optional key."""
    return {
        "event_id": event.get("event_id") or str(uuid.uuid4()),
        "ts": event["ts"],
        "source_env": event["source_env"],
        "agent_id": event.get("agent_id"),
        "target_service": event["target_service"],
        "endpoint": event.get("endpoint"),
        "method": event.get("method"),
        "status_code": event.get("status_code"),
        "latency_ms": event.get("latency_ms"),
        "payload_size_b": event.get("payload_size_b"),
        "error_type": event.get("error_type"),
        "error_message": event.get("error_message"),
    }


@bp.route("/events", methods=["POST"])
def ingest_single():
    event = request.get_json(silent=True)
    if not event:
        return jsonify(error="invalid or missing JSON body"), 400

    if not _check_auth(event.get("source_env")):
        return jsonify(error="unauthorized"), 401

    err = _validate(event)
    if err:
        return jsonify(error=err), 400

    row = _normalize(event)
    pool = get_pool()
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(INSERT_SQL, row)
    except Exception as e:
        current_app.logger.exception("ingest_single failed")
        return jsonify(error="internal error storing event"), 500

    return jsonify(status="ok", event_id=row["event_id"]), 201


@bp.route("/events/batch", methods=["POST"])
def ingest_batch():
    body = request.get_json(silent=True)
    events = body.get("events") if isinstance(body, dict) else None
    if not events or not isinstance(events, list):
        return jsonify(error="expected JSON body: {\"events\": [...]}"), 400

    if len(events) > 1000:
        return jsonify(error="batch too large, max 1000 events per request"), 400

    accepted, rejected = [], []
    rows = []
    for i, event in enumerate(events):
        if not _check_auth(event.get("source_env")):
            rejected.append({"index": i, "error": "unauthorized"})
            continue
        err = _validate(event)
        if err:
            rejected.append({"index": i, "error": err})
            continue
        row = _normalize(event)
        rows.append(row)
        accepted.append(row["event_id"])

    if rows:
        pool = get_pool()
        try:
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(INSERT_SQL, rows)
        except Exception:
            current_app.logger.exception("ingest_batch failed")
            return jsonify(error="internal error storing batch"), 500

    return jsonify(
        status="ok",
        accepted_count=len(accepted),
        rejected_count=len(rejected),
        rejected=rejected,
    ), 201
