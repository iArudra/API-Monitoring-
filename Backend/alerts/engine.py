"""
Threshold-based alert engine. This is intentionally a standalone script,
NOT a background thread inside the Flask app — running it as a separate
process invoked by cron every minute is more reliable for a student
project (if it crashes, it doesn't take ingestion down with it; if
ingestion restarts, this doesn't reset).

Run manually to test:
    python -m alerts.engine

Run on a schedule (cron, every minute):
    * * * * * cd /path/to/centralwatch-backend && /path/to/venv/bin/python -m alerts.engine >> alerts.log 2>&1

Rules implemented (start here, add more once these are proven to fire
correctly on real fault-injected traffic from Person D):
  1. error_rate_threshold : error rate > 5% over last 5 minutes, min 10 calls
  2. latency_spike        : avg latency > 3x the service's 1-hour baseline
  3. service_down         : 100% error rate over last 5 minutes, min 3 calls
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_pool

ERROR_RATE_THRESHOLD = 0.05
MIN_CALLS_FOR_ERROR_RATE = 10
LATENCY_SPIKE_MULTIPLIER = 3.0
MIN_CALLS_FOR_DOWN = 3


def _already_open(cur, rule_name, service, env):
    """Avoid spamming duplicate alerts every minute while a condition persists."""
    cur.execute(
        """
        SELECT 1 FROM alerts
        WHERE rule_name = %(rule_name)s
          AND target_service = %(service)s
          AND source_env IS NOT DISTINCT FROM %(env)s
          AND resolved = FALSE
          AND triggered_at > now() - INTERVAL '10 minutes'
        LIMIT 1;
        """,
        {"rule_name": rule_name, "service": service, "env": env},
    )
    return cur.fetchone() is not None


def _raise_alert(cur, rule_name, severity, service, env, message, details):
    if _already_open(cur, rule_name, service, env):
        return False
    cur.execute(
        """
        INSERT INTO alerts (rule_name, severity, source_env, target_service, message, details)
        VALUES (%(rule_name)s, %(severity)s, %(env)s, %(service)s, %(message)s, %(details)s);
        """,
        {
            "rule_name": rule_name,
            "severity": severity,
            "env": env,
            "service": service,
            "message": message,
            "details": details and __import__("json").dumps(details),
        },
    )
    return True


def check_error_rate_and_down(cur):
    cur.execute(
        """
        SELECT source_env, target_service,
               sum(call_count) AS calls,
               sum(error_count) AS errors
        FROM events_1min
        WHERE bucket > now() - INTERVAL '5 minutes'
        GROUP BY source_env, target_service;
        """
    )
    fired = 0
    for env, service, calls, errors in cur.fetchall():
        if calls == 0:
            continue
        error_rate = errors / calls

        if calls >= MIN_CALLS_FOR_DOWN and errors == calls:
            if _raise_alert(
                cur, "service_down", "critical", service, env,
                f"{service} in {env} appears down: {errors}/{calls} calls failed in last 5 min",
                {"calls": calls, "errors": errors},
            ):
                fired += 1
            continue  # don't also fire error_rate_threshold for the same window

        if calls >= MIN_CALLS_FOR_ERROR_RATE and error_rate > ERROR_RATE_THRESHOLD:
            if _raise_alert(
                cur, "error_rate_threshold", "warning", service, env,
                f"{service} in {env} error rate {error_rate:.1%} over last 5 min (threshold {ERROR_RATE_THRESHOLD:.0%})",
                {"calls": calls, "errors": errors, "error_rate": round(error_rate, 4)},
            ):
                fired += 1
    return fired


def check_latency_spikes(cur):
    cur.execute(
        """
        WITH recent AS (
            SELECT source_env, target_service, avg(avg_latency_ms) AS recent_avg
            FROM events_1min
            WHERE bucket > now() - INTERVAL '5 minutes'
            GROUP BY source_env, target_service
        ),
        baseline AS (
            SELECT source_env, target_service, avg(avg_latency_ms) AS baseline_avg
            FROM events_1min
            WHERE bucket > now() - INTERVAL '1 hour'
              AND bucket <= now() - INTERVAL '5 minutes'
            GROUP BY source_env, target_service
        )
        SELECT r.source_env, r.target_service, r.recent_avg, b.baseline_avg
        FROM recent r
        JOIN baseline b
          ON b.source_env = r.source_env AND b.target_service = r.target_service
        WHERE b.baseline_avg IS NOT NULL AND b.baseline_avg > 0;
        """
    )
    fired = 0
    for env, service, recent_avg, baseline_avg in cur.fetchall():
        if recent_avg is None:
            continue
        if recent_avg > baseline_avg * LATENCY_SPIKE_MULTIPLIER:
            if _raise_alert(
                cur, "latency_spike", "warning", service, env,
                f"{service} in {env} latency {recent_avg:.0f}ms vs {baseline_avg:.0f}ms baseline "
                f"(>{LATENCY_SPIKE_MULTIPLIER}x)",
                {"recent_avg_ms": round(recent_avg, 1), "baseline_avg_ms": round(baseline_avg, 1)},
            ):
                fired += 1
    return fired


def run():
    pool = get_pool()
    total_fired = 0
    with pool.connection() as conn:
        with conn.cursor() as cur:
            total_fired += check_error_rate_and_down(cur)
            total_fired += check_latency_spikes(cur)
        conn.commit()
    print(f"alert engine run complete: {total_fired} new alert(s) fired")


if __name__ == "__main__":
    run()
