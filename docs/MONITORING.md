# Monitoring

## How I'd know it's healthy

Start from the user (mobile app), then work inward.

1. **Golden signals at the ingress and the app**: request rate, error ratio (5xx), latency p50/p95/p99, saturation (CPU vs request, pool wait time).
2. **SLOs**, to be agreed. Strawman: 99.9% of requests non-5xx and 99% under 500 ms over 30 days. Alert on **error-budget burn rate**, not raw thresholds.
3. **Dependencies**: DB connection pool in-use/waiting, query latency, DB connection errors; Postgres connection count vs limit (from DB owner's metrics).
4. **Business signals**: webhooks received/accepted/duplicate/bad-signature per minute. A payments provider silently stopping sending is a failure no error rate shows.
5. **Batch**: last successful run timestamp, duration, failed Jobs.
6. **Platform**: pod restarts, HPA at max, pods not ready, cert expiry, ExternalSecret sync status.

The app already exposes `/metrics` (prometheus_client). Dashboards: one overview (the signals above), one DB/pool view.

## Page at 3am (user impact now, or imminent, needs a human now)

| Alert | Why it pages |
|---|---|
| Fast burn: 5xx > ~2% for 5 min (and 1h window agrees) | Users are failing right now. |
| p99 latency far above SLO for 10 min | App effectively down for mobile even if no 5xx. |
| No ready pods / availability < 50% | Total outage. |
| DB unreachable or pool exhausted (waiters > 0 sustained) | Cascading failure; HPA won't fix it and can worsen it. |
| HPA at maxReplicas **and** CPU still > 80% | Out of headroom during peak. |
| Webhooks: zero accepted for 15 min **during hours it normally flows**, or sustained bad-signature spike | Lost or mis-processed payments. |
| Batch has not succeeded in 36 h | Settlement is silently stale. Pages in daytime if overnight alert would be noise. |

## Look at it tomorrow (ticket / Slack, no page)

- Slow burn of error budget (e.g. 10% budget in 24h)
- Single pod restarts / OOMKills, CrashLoop on one pod
- HPA flapping, sustained scale to > 70% of max
- Batch run duration trending up, or one failed run that later retried successfully
- Cert expiring in < 14 days, ExternalSecret refresh failures
- Duplicate-webhook rate up; image vulnerability findings
- Resource requests far off actual usage (right-sizing)

## Rules I'd follow

- Every page has a runbook link and a clear first action; if a page has no action, it's not a page.
- Alert on symptoms (users hurting), keep causes (CPU, restarts) as ticket-level or dashboard unless they predict an outage.
- Review noisy alerts weekly; delete or demote the ones nobody acted on.
- Alerts are guesses until there is an SLO and a load test.

## Not built

Prometheus rules, ServiceMonitor, dashboards, and Alertmanager routing are not in the repo: they were requested in writing only, and thresholds depend on the SLO.
