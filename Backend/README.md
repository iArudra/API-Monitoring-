# CentralWatch backend (Person B)

Flask ingestion + query API on TimescaleDB.

## 1. Install TimescaleDB on your VM (Ubuntu)

```bash
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y
curl -fsSL https://packagecloud.io/install/repositories/timescale/timescaledb/script.deb.sh | sudo bash
sudo apt install -y timescaledb-2-postgresql-16
sudo timescaledb-tune --quiet --yes
sudo systemctl restart postgresql
```

## 2. Create the database and user

```bash
sudo -u postgres psql -c "CREATE USER centralwatch WITH PASSWORD 'changeme';"
sudo -u postgres psql -c "CREATE DATABASE centralwatch OWNER centralwatch;"
sudo -u postgres psql -d centralwatch -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
psql -h localhost -U centralwatch -d centralwatch -f schema.sql
```

If `create_hypertable` or `add_continuous_aggregate_policy` errors out, run
`\dx` in psql and confirm `timescaledb` is listed under extensions — that's
the #1 cause of failure here.

## 3. Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env with your real DB password + agent keys
```

## 4. Run it

Dev/testing:
```bash
python app.py
curl http://localhost:5000/health
```

Anything beyond a handful of manual test requests — use gunicorn, not the
Flask dev server:
```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## 5. Smoke test the pipeline manually

```bash
# insert a fake event
curl -X POST http://localhost:5000/api/v1/events \
  -H "Content-Type: application/json" \
  -d '{"ts":"2026-08-05T10:00:00Z","source_env":"dev","target_service":"stripe","endpoint":"/v1/charges","method":"POST","status_code":200,"latency_ms":142.5}'

# register the service so it shows up in /services even with no traffic
psql -h localhost -U centralwatch -d centralwatch -c \
  "INSERT INTO services (service_name, display_name, provider) VALUES ('stripe','Stripe','stripe') ON CONFLICT DO NOTHING;"

curl http://localhost:5000/api/v1/services
curl "http://localhost:5000/api/v1/services/stripe/timeseries?since=1 hour"
```

Note: `/services` and `/timeseries` read from the `events_1min` continuous
aggregate, which refreshes on its own schedule (every 1 minute per the
policy in schema.sql) — don't panic if a just-inserted event doesn't show
up in those endpoints for up to a minute. `/events/batch` and the raw
`events` table are immediate.

## 6. Alert engine — run on a schedule

```bash
crontab -e
# add:
* * * * * cd /path/to/centralwatch-backend && venv/bin/python -m alerts.engine >> alerts.log 2>&1
```

Or test it manually first: `python -m alerts.engine`

## What's NOT done yet (your remaining Person B tasks per the tracker)

- Quota / rate-limit tracking (uses `services.quota_limit` — column exists,
  logic doesn't yet)
- Anomaly detection (z-score) beyond the current fixed thresholds
- Auth is a simple shared-key check per environment — fine for a student
  demo, don't present it as production-grade in your report

## Handing off to Person A / Person C

- Person A's collector agent must POST to `/api/v1/events/batch` with the
  JSON shape documented at the top of `routes/ingest.py`. Send that file's
  docstring to them directly — it's the contract.
- Person C's dashboard should hit `/api/v1/services`, `/api/v1/services/<name>/timeseries`,
  `/api/v1/environments/compare`, and `/api/v1/alerts`.
