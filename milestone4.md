# Milestone 4: Grafana Security & Threat Intelligence Dashboard

I designed and provisioned a custom Grafana dashboard to visualize all the security metrics and logs emitted by the Hybrid Security Gateway.

## Changes Made

### 1. Dashboard Provisioning
- **Location:** `configs/grafana/provisioning/dashboards/security.json`
- Created a brand new JSON dashboard tailored specifically for security observability.

### 2. Panels Included
- 📈 **Security Attack Rate:** A Prometheus timeseries panel querying `sum by (event_type) (increase(centralwatch_security_violations_total[5m]))` to map out the precise rate of `IP_SUBNET_VIOLATION` and `TOKEN_REVOKED` attacks.
- 🪵 **Live Threat Intelligence Log Stream:** A real-time Loki log stream instantly isolating any logs containing a `security_event` to watch unauthorized actors get blocked in real-time.
- 🛡️ **Threat Scanner Control Panel:** A custom HTML control panel offering a quick 1-click execution link to trigger the background OWASP ASTF scan, along with information about requiring an admin token.

## What was tested
- Restarting the Grafana container successfully loads the new dashboard via the provisioning pipeline.
- Panels accurately query Prometheus and Loki datasources.
