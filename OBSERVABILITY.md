# Observability & Logging

This application now emits production-friendly JSON logs and exposes health &
client-side telemetry endpoints suitable for Heroku deployments.

## Runtime configuration

Set the following config vars on Heroku (`heroku config:set ...`):

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | Root logging level for application logs. |
| `REQUEST_LOG_SAMPLE_RATE` | `1.0` | Fraction of requests to log in detail (0.0–1.0). |
| `RESPONSE_BODY_MAX_BYTES` | `2048` | Maximum response body size included in logs (0 disables). |
| `SENSITIVE_FIELDS` | `password,token,email,phone` | Comma separated field names redacted from logs. |
| `CLIENT_LOG_RATE_LIMIT` | `10` | Browser log events allowed per IP in the configured window. |
| `CLIENT_LOG_WINDOW_SECONDS` | `60` | Rolling window for the client log rate limiter. |
| `LOG_SLACK_WEBHOOK_URL` | _(unset)_ | Optional Slack webhook for ERROR alerts. |
| `DATABASE_URL` | _(unset)_ | Neon / Postgres URL (falls back to SQLite if missing/unreachable). |

## Logging format

Application logs are single-line JSON with the following fields:

```
ts, level, logger, msg, request_id, method, path, status, duration_ms,
client_ip, user_agent, route, db_time_ms, error_type, error, stack, extra_context
```

Logs automatically inherit the active correlation ID (`X-Request-ID`). Sensitive
keys from `SENSITIVE_FIELDS` are replaced with `[REDACTED]` before emission.

## Health & telemetry endpoints

- `GET /health` — returns `{"status": "ok"}` without touching the database.
- `POST /client-logs` — accepts small browser error payloads, applies rate
  limiting and redaction, and records them as `client_log` events server-side.

## Browser error collection

Include `/static/client-logger.js` (already referenced by `templates/index.html`)
when serving pages. The script forwards `window.onerror` and
`unhandledrejection` events via `navigator.sendBeacon` or a fallback `fetch`
call to `/client-logs`.

## Deployment tips

- The `Procfile` continues to run `gunicorn app:app`; application-level request
  logging replaces Gunicorn access logs, so no extra flags are required.
- Ensure `DATABASE_URL` is configured; the app tolerates temporary outages and
  logs failures during bootstrap without crashing.
- Optional: provide `LOG_SLACK_WEBHOOK_URL` to receive critical alerts in Slack.

## Validation

Run tests locally before deployment:

```bash
pip install -r requirements.txt
pytest -q
```

Smoke tests after deployment:

```bash
curl -i https://nekeyoklama-349f67d5e636.herokuapp.com/health
curl -i -H "X-Request-ID: demo-123" https://nekeyoklama-349f67d5e636.herokuapp.com/health
curl -i -X POST -H "Content-Type: application/json" \
  -d '{"level":"error","message":"client"}' \
  https://nekeyoklama-349f67d5e636.herokuapp.com/client-logs
```
