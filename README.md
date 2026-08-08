# CentralWatch

CentralWatch is an end-to-end **observability demo**: a FastAPI application (`demo-app`) that
performs real business workflows against AWS and generates rich OpenTelemetry telemetry —
metrics, logs, and traces — which flow through an OpenTelemetry Collector into
**Prometheus** (metrics), **Loki** (logs) and **Tempo** (traces), visualized in **Grafana**.

The monitoring system is a **bystander**. It never sits in the application's request path:

```
                      Application traffic
  Browser ──> nginx (frontend) ──/api──> FastAPI (demo-app) ──boto3──> AWS
                                                    │
                                        OpenTelemetry SDK (OTLP over HTTP)
                                                    │
                                             otel-collector :4318
                                              ┌──────┼──────┐
                                              ▼      ▼      ▼
                                         Prometheus  Loki  Tempo
                                              └──────┼──────┘
                                                     ▼
                                                  Grafana
```

Two runtime modes are supported with **the same codebase** (everything is environment-driven):

| Mode | `AWS_ENDPOINT_URL` | `AWS_PROVISION_RESOURCES` | Backend |
| :--- | :--- | :--- | :--- |
| **LocalStack (dev, default)** | `http://localstack:4566` | `true` — resources auto-created | offline emulator |
| **Real AWS (production)** | empty | `false` — resources validated, fail fast | real AWS |

---

## 1. Quick start (LocalStack / dev)

Requires Docker + Docker Compose v2 only — **no pre-built images, no manually created
networks, no pre-created resources**.

```bash
docker compose up -d --build
```

This builds and starts all 8 services on one shared network (`centralwatch-network`):

| Service | Container | Host port | Purpose |
| :--- | :--- | :--- | :--- |
| `frontend` | `centralwatch-frontend` | `8080` | Serves the built React SPA, proxies `/api/*` → backend |
| `demo-app` | `centralwatch-demo-app` | `8000` | FastAPI app (`/docs` for Swagger) |
| `localstack` | `centralwatch-localstack` | `4566` | AWS emulation (S3, DynamoDB, SNS, SQS, Lambda) |
| `otel-collector` | `centralwatch-otel-collector` | `4317`/`4318`/`8889` | OTLP ingress, Prometheus endpoint |
| `prometheus` | `centralwatch-prometheus` | `9090` | Metrics store + query |
| `loki` | `centralwatch-loki` | `3100` | Logs store + query |
| `tempo` | `centralwatch-tempo` | `3200` | Traces store + TraceQL |
| `grafana` | `centralwatch-grafana` | `3000` | Dashboards (`admin` / `admin` by default) |

The demo app waits for LocalStack, then **auto-provisions** (idempotently): S3 bucket
`centralwatch-files`, DynamoDB tables `users` (with `email-index` GSI), `orders`, `files`,
SNS topic `centralwatch-notifications`, SQS queue `centralwatch-queue`, and Lambda function
`centralwatch-image-processor`. A reconcile loop re-creates anything that disappears.

Verify:

```bash
./scripts/healthcheck.sh          # deep health of every component
curl -s http://localhost:8000/healthz
curl -s http://localhost:8080/    # frontend
```

## 2. Authentication

Business endpoints (`/orders`, `/files`, `/images`, `/notifications`, `/queue`,
`/simulate`) require a **Bearer token** issued by `/auth/login`. Public endpoints:
`/auth/register`, `/auth/login`, `/healthz`, `/livez`, `/readyz`, `/docs`.

```bash
# Register + login
curl -s -X POST http://localhost:8000/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"secret123","name":"Alice"}'
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"secret123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")

# Protected call
curl -s -X POST http://localhost:8000/orders -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"usr_demo","items":[{"product_id":"p1","name":"Widget","quantity":2,"unit_price":9.99}]}'

# Without a token you get 401
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"x","items":[{"product_id":"p1","name":"W","quantity":1,"unit_price":1}]}'
```

Tokens are HMAC-signed (PBKDF2-hashed passwords, stateless tokens). The signing secret comes
from **`AUTH_TOKEN_SECRET`** — there is no default in code and the app **fails fast** at
startup if it is missing. The dev compose ships a documented dev-only default; the AWS compose
requires it with no default (see [AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md)).

## 3. Real AWS mode (production)

See **[AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md)** for the complete guide: the exact AWS resources
the code uses, least-privilege IAM policies (app role + Lambda execution role), and the
production compose file:

```bash
docker compose -f docker-compose.aws.yml up -d --build
```

In production mode the app **validates** every required resource at startup and exits with a
clear error if any are missing. `AUTH_TOKEN_SECRET` and `GRAFANA_ADMIN_PASSWORD` are required
(no defaults).

A ready-to-fill template with every real-AWS variable is provided at **`.env.aws.example`**
(copy it to `.env` for `docker compose` substitution, or to `demo-app/.env` for a bare uvicorn
run). Never commit the filled-in file — `.env` is gitignored.

> **Real-AWS verification status:** the real-AWS code path (empty endpoint, default credential
> chain, `AWS_PROVISION_RESOURCES=false` validation) is verified statically against the exact
> SDK calls in the source. It has **not** been exercised against a live AWS account in this
> environment — see the limitation note in `AWS_DEPLOYMENT.md`.

## 4. Frontend

The `frontend/` directory contains the **prebuilt** React SPA bundle. `nginx` serves it at
`http://localhost:8080` and proxies `/api/*` to the FastAPI backend (same-origin, no CORS).
Rebuild instructions for the SPA source are outside this repo's scope (only the built bundle
is tracked); the bundle is built with Vite and expects an axios `baseURL` of `/api`.

## 5. Telemetry contract (what the dashboards query)

### Metrics (Prometheus — via the Collector's `centralwatch` namespace)

| Metric | Labels |
| :--- | :--- |
| `centralwatch_http_server_duration_milliseconds_{bucket,sum,count}` | `http_method`, `http_status_code`, `http_target`, `service`, `instance`, `deployment_environment` |
| `centralwatch_orders_created_total` | `status` |
| `centralwatch_files_uploaded_total` | `status` |
| `centralwatch_images_processed_total` | `status` |
| `centralwatch_notifications_sent_total` | `channel`, `status` |
| `centralwatch_retry_attempts_total` | `operation` |

> The `environment` label is emitted as **`deployment_environment`** (the collector's
> `resource_to_telemetry_conversion` copies the app's `deployment.environment` resource
> attribute onto every metric) — `development` in dev mode, `production` on real AWS.
>
> **Label semantics:** in Prometheus the `service` label is the scrape-job static label (`centralwatch-collector`, the exporter hosting `/metrics`), while `service_name` is the app's OTel resource attribute (`centralwatch-demo-app`). In Tempo, `service.name` is the app (`centralwatch-demo-app`). Dashboards are consistent with this per datasource.


### Logs (Loki)

Labels: `job` (= `service.name`), `level` (**uppercase**: `INFO`/`ERROR`/`WARN`), `exporter`.
Every line is structured JSON with `traceid` / `spanid`, `endpoint`, `http.method`,
`status_code`, `duration_ms`, plus AWS fields (`aws.service`, `aws.operation`, `channel`, …).
`traceid` and `endpoint` are **JSON fields** — query them with the `| json` parser:

```logql
{job="centralwatch-demo-app"} | json | traceid != ""
{job="centralwatch-demo-app", level="ERROR"}
```

### Traces (Tempo)

`service.name=centralwatch-demo-app`. Automatic FastAPI/ASGI server spans, botocore AWS spans
(`S3.PutObject`, `S3.GetObject`, `S3.DeleteObject`, `S3.ListBuckets`, `DynamoDB.PutItem`,
`DynamoDB.GetItem`, `DynamoDB.Query`, `DynamoDB.Scan`, `DynamoDB.DeleteItem`, `centralwatch-notifications send`,
`SQS.SendMessage`, `SQS.ReceiveMessage`, `SQS.DeleteMessageBatch`, `Lambda.Invoke`), and manual
business spans (`User Registration`, `User Login`, `Order Creation`, `Notification Workflow`,
`Image Processing Workflow`, `Retry Operation` → `Retry Attempt N`).

```traceql
{ resource.service.name = "centralwatch-demo-app" } && { name = "S3.PutObject" }
```

## 6. Grafana dashboards

Six dashboards are provisioned into the **CentralWatch** folder (auto-loading via
`configs/grafana/provisioning/`):

1. **CentralWatch — Overview** (`overview.json`) — requests/sec, avg/P95/P99 latency, error &
   success rate, business totals.
2. **CentralWatch — API Monitoring** (`api-monitoring.json`) — requests by route/method/status,
   latency by route, error rate, duration histogram, top slow APIs.
3. **CentralWatch — AWS Services** (`aws-services.json`) — S3/Lambda/SNS/SQS/DynamoDB trace
   tables + waterfall.
4. **CentralWatch — Business Metrics** (`business-metrics.json`) — orders/files/images/
   notifications/retries with `channel`/`status`/`operation` breakdowns.
5. **CentralWatch — Tracing** (`tracing.json`) — recent/slowest traces, AWS & business span
   segments, waterfall.
6. **CentralWatch — Logs** (`logs.json`) — recent logs, ERROR/WARN streams, logs-by-traceid,
   logs-by-endpoint.

## 7. Health checks

```bash
./scripts/healthcheck.sh          # all containers + readiness + Prometheus scrape targets
curl -s http://localhost:8000/healthz    # liveness
curl -s http://localhost:8000/livez      # liveness
curl -s http://localhost:8000/readyz     # readiness (checks AWS reachability)
```

## 8. Troubleshooting

| Symptom | Cause / fix |
| :--- | :--- |
| `Failed to resolve 'otel-collector'` in app logs | containers on different networks — recreate with `docker compose down && docker compose up -d --build` (the compose file pins one explicit network) |
| `/images/process` returns 502/`Pending` Lambda | first Lambda sidecar pull is slow on LocalStack; the app warms it up in the background — wait ~60 s and retry. If permanently `Pending`, `docker compose restart localstack demo-app` |
| Lambda needs the Docker socket | required **only** in LocalStack mode. Docker Desktop path `/run/host-services/docker.proxy.sock`; on Linux set `DOCKER_SOCK_PATH=/var/run/docker.sock` |
| Grafana dashboards show "No data" | generate traffic first (see §2 / `AWS_DEPLOYMENT.md` runbook), then check Prometheus `http://localhost:9090` for `centralwatch_*` series |
| Tempo panels empty | traces are retained per the tempo config; re-run `/images/process` etc. and refresh |
| `AUTH_TOKEN_SECRET` startup error | set the env var (dev: any value; prod: strong secret) |
| Port already in use | change the host mapping in `docker-compose.yml` (`8000:8000` → `8010:8000`, …) |

## 9. Project layout

```
├── demo-app/                    # FastAPI application (built by Docker, no pre-built image)
│   ├── Dockerfile
│   ├── entrypoint.sh
│   ├── requirements.txt
│   ├── .env.example
│   └── app/
│       ├── main.py              # app factory, middleware, exception handlers
│       ├── deps.py              # DI container + auth dependency
│       ├── config/              # pydantic-settings
│       ├── routes/              # auth, orders, files, images, notifications, queue, simulate
│       ├── services/            # boto3 clients + AWS resource manager + Lambda code
│       ├── telemetry/           # instrumentation, logging, metrics, tracing
│       ├── models/ schemas/ utils/
├── configs/
│   ├── collector/config.yaml    # OTel collector pipelines
│   ├── prometheus/prometheus.yml
│   ├── loki/loki-config.yaml
│   ├── tempo/tempo.yaml
│   ├── nginx/frontend.conf
│   └── grafana/provisioning/    # datasources + 6 dashboards
├── frontend/dist/               # prebuilt React SPA
├── scripts/                     # start.sh, stop.sh, healthcheck.sh
├── docker-compose.yml           # dev stack (LocalStack)
├── docker-compose.aws.yml       # production stack (real AWS)
└── AWS_DEPLOYMENT.md            # resources, IAM, production runbook
```
