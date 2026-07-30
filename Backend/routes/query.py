"""
Read-only endpoints for the dashboard. All timestamps in responses are
ISO8601 UTC. All endpoints accept ?env=dev|staging|prod to filter by
environment; omit it to aggregate across all environments.
"""
from flask import Blueprint, request, jsonify
from db import get_pool

bp = Blueprint("query", __name__, url_prefix="/api/v1")


def _rows_to_dicts(cur):
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@bp.route("/services", methods=["GET"])
def list_services():
    """
    Health overview: every known service with its status over the last
    5 minutes, derived from the 1-minute rollup. Status logic:
      - 'down'     : 0 successful calls and >=1 error in the window
      - 'degraded' : error rate > 5% in the window
      - 'up'       : otherwise
      - 'unknown'  : no events in the window at all
    """
    sql = """
        WITH recent AS (
            SELECT target_service,
                   sum(call_count)  AS calls,
                   sum(error_count) AS errors,
                   avg(avg_latency_ms) AS avg_latency_ms
            FROM events_1min
            WHERE bucket > now() - INTERVAL '5 minutes'
            GROUP BY target_service
        )
        SELECT s.service_name,
               s.display_name,
               s.provider,
               COALESCE(r.calls, 0)  AS calls_5m,
               COALESCE(r.errors, 0) AS errors_5m,
               r.avg_latency_ms,
               CASE
                   WHEN r.calls IS NULL THEN 'unknown'
                   WHEN r.calls > 0 AND r.errors = r.calls THEN 'down'
                   WHEN r.calls > 0 AND (r.errors::float / r.calls) > 0.05 THEN 'degraded'
                   ELSE 'up'
               END AS status
        FROM services s
        LEFT JOIN recent r ON r.target_service = s.service_name
        ORDER BY s.service_name;
    """
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            return jsonify(_rows_to_dicts(cur))


@bp.route("/services/<service_name>/timeseries", methods=["GET"])
def service_timeseries(service_name):
    """
    Graph data for a single service. Query params:
      env      - optional, filter to one environment
      since    - ISO timestamp or interval like '1 hour', '6 hours', '7 days' (default '1 hour')
      bucket   - '1 minute' (default) or larger, e.g. '1 hour' for long ranges
    """
    env = request.args.get("env")
    since = request.args.get("since", "1 hour")
    bucket = request.args.get("bucket", "1 minute")

    allowed_buckets = {"1 minute", "5 minutes", "15 minutes", "1 hour", "1 day"}
    if bucket not in allowed_buckets:
        return jsonify(error=f"bucket must be one of {sorted(allowed_buckets)}"), 400

    params = {"service": service_name, "since": since}
    env_filter = ""
    if env:
        env_filter = "AND source_env = %(env)s"
        params["env"] = env

    sql = f"""
        SELECT time_bucket(%(bucket)s, bucket) AS t,
               sum(call_count)  AS calls,
               sum(error_count) AS errors,
               avg(avg_latency_ms) AS avg_latency_ms,
               max(max_latency_ms) AS max_latency_ms
        FROM events_1min
        WHERE target_service = %(service)s
          AND bucket > now() - %(since)s::interval
          {env_filter}
        GROUP BY t
        ORDER BY t;
    """
    params["bucket"] = bucket
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return jsonify(_rows_to_dicts(cur))


@bp.route("/services/<service_name>/p95", methods=["GET"])
def service_p95(service_name):
    """
    p95 latency computed on-demand from raw events (not the rollup —
    see schema.sql note on why percentile isn't pre-aggregated).
    Keep 'since' short (<= a few hours) or this scans a lot of rows.
    """
    env = request.args.get("env")
    since = request.args.get("since", "1 hour")

    params = {"service": service_name, "since": since}
    env_filter = ""
    if env:
        env_filter = "AND source_env = %(env)s"
        params["env"] = env

    sql = f"""
        SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms
        FROM events
        WHERE target_service = %(service)s
          AND ts > now() - %(since)s::interval
          AND latency_ms IS NOT NULL
          {env_filter};
    """
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return jsonify(p95_latency_ms=row[0] if row else None)


@bp.route("/environments/compare", methods=["GET"])
def compare_environments():
    """
    Cross-environment view: same service, side-by-side stats per env.
    This is what Person C's cross-env comparison view queries.
    """
    service = request.args.get("service")
    since = request.args.get("since", "1 hour")
    if not service:
        return jsonify(error="service query param is required"), 400

    sql = """
        SELECT source_env,
               sum(call_count)  AS calls,
               sum(error_count) AS errors,
               avg(avg_latency_ms) AS avg_latency_ms
        FROM events_1min
        WHERE target_service = %(service)s
          AND bucket > now() - %(since)s::interval
        GROUP BY source_env
        ORDER BY source_env;
    """
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"service": service, "since": since})
            return jsonify(_rows_to_dicts(cur))


@bp.route("/alerts", methods=["GET"])
def list_alerts():
    """
    Alert feed. Query params:
      resolved - 'true'/'false', omit for all
      limit    - default 50, max 500
    """
    resolved = request.args.get("resolved")
    limit = min(int(request.args.get("limit", 50)), 500)

    where = ""
    params = {"limit": limit}
    if resolved is not None:
        where = "WHERE resolved = %(resolved)s"
        params["resolved"] = resolved.lower() == "true"

    sql = f"""
        SELECT alert_id, triggered_at, rule_name, severity, source_env,
               target_service, message, details, resolved, resolved_at
        FROM alerts
        {where}
        ORDER BY triggered_at DESC
        LIMIT %(limit)s;
    """
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return jsonify(_rows_to_dicts(cur))
