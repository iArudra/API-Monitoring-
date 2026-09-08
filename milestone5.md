# Milestone 5: Verification & End-to-End Walkthrough

To ensure the entire CentralWatch V2 Security platform operates cohesively, perform the following end-to-end verification.

## 1. Verify the Hybrid Security Gateway (WAF)
1. **Register a Restricted User:**
   Register a user whose `allowed_cidrs` is deliberately set to an external subnet (`10.0.0.0/8`).
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/auth/register" -Method POST -ContentType "application/json" -Body '{"email":"hacker@test.com","password":"password123","name":"Hacker", "allowed_cidrs":["10.0.0.0/8"]}'
   ```
2. **Login to obtain the Token:**
   ```powershell
   $RES = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" -Method POST -ContentType "application/json" -Body '{"email":"hacker@test.com","password":"password123"}'
   $HACKER_TOKEN = $RES.access_token
   ```
3. **Attempt Access:**
   Try to access `/auth/profile` from your local machine (`127.0.0.1`).
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/auth/profile" -Method GET -Headers @{ Authorization = "Bearer $HACKER_TOKEN" }
   ```
   **Expected Result:** A `403 Forbidden` response is instantly returned. 

## 2. Verify the OWASP ASTF Scanner
1. **Register an Admin User (Open CIDR):**
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/auth/register" -Method POST -ContentType "application/json" -Body '{"email":"admin@test.com","password":"admin123","name":"Admin", "allowed_cidrs":["0.0.0.0/0"]}'
   
   $RES = Invoke-RestMethod -Uri "http://localhost:8000/auth/login" -Method POST -ContentType "application/json" -Body '{"email":"admin@test.com","password":"admin123"}'
   $ADMIN_TOKEN = $RES.access_token
   ```
2. **Trigger the Scan:**
   ```powershell
   Invoke-RestMethod -Uri "http://localhost:8000/centralwatch/security-scan?target_url=http://127.0.0.1:8000" -Method POST -Headers @{ Authorization = "Bearer $ADMIN_TOKEN" }
   ```
   **Expected Result:** You will receive a `200 OK` response. Checking the `docker logs centralwatch-demo-app` will show the JAR downloading and running the API audit.

## 3. Verify the Grafana Dashboard & Telemetry
1. Open Grafana (`http://localhost:3000`).
2. Navigate to **Dashboards -> Security & Threat Intelligence**.
3. **Verify:**
   - The **Security Attack Rate** panel shows a spike in the `centralwatch_security_violations_total` metric caused by the hacker's 403 attempt.
   - The **Live Threat Intelligence Log Stream** displays the structured JSON log detailing the `IP_SUBNET_VIOLATION`.
   - The **Threat Scanner Control Panel** correctly displays the UI to trigger future scans.
