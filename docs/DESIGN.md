# Design notes: payments-api on Kubernetes

One Helm chart (`charts/payments-api`) with `values-staging.yaml`/`values-prod.yaml`, reconciled by Argo CD. Helm because per-environment differences (host, secret path, replica bounds, pool size, DB CIDR) are plain values rather than JSON patches that break when resource order changes, and it is the format most teams already know. The cost is Go templating, so CI renders and validates both environments on every PR.

## What is deployed

| Piece | Decision | Why |
|---|---|---|
| Deployment | `maxUnavailable: 0`, surge 25%, `preStop` sleep 10s, 45s grace, uvicorn graceful shutdown 30s | Critical path for the mobile app: deploys must not drop in-flight requests. |
| HPA | CPU 60%, fast up (100%/min), slow down (10%/min, 10 min window). Prod min 6, max 24 | Evening ramp is ~10x. Floor of 6 = 2 per zone, so a zone loss at overnight load is survivable. |
| Spread / PDB | Hard zone spread, soft node spread, `maxUnavailable: 1` | Node drains and zone failures shouldn't take capacity below what the evening needs. |
| Probes | Startup + liveness on `/healthz` (no DB), readiness on `/readyz` (shallow) | If readiness checked the DB, a Postgres blip would eject *every* pod and turn a degraded service into a hard outage. DB health is alerted on instead. |
| Resources | Mem limit = request, **no CPU limit** | Avoids CFS throttling on tail latency. The numbers are placeholders: they must come from a load test. |
| Batch | Separate CronJob, `concurrencyPolicy: Forbid`, advisory lock, idempotent SQL | If it ran in the API it would run N times and steal CPU from requests. Same image, different command. |
| Webhooks | Same service, HMAC signature check, dedupe on event ID | Providers retry. Idempotency in the app is what makes retries safe; ingress never retries a POST on 5xx. |
| Secrets | External Secrets Operator -> k8s Secret | Nothing sensitive in git. Assumes ESO + a `ClusterSecretStore` named `platform-secrets`. |
| NetworkPolicy | Ingress only from ingress controller and monitoring; egress only DNS + Postgres | Limits blast radius of a compromised pod. |
| Pod security | non-root, read-only rootfs, drop ALL caps, seccomp RuntimeDefault | Cheap hardening. |
| Image | Pinned by **digest** in the values files, signed with cosign, signature verified before prod | What ran in staging is byte-identical to what runs in prod. |

## The part I'd worry about most: the DB connection budget

Postgres is out of scope to tune, but the app's use of it isn't. Total connections = replicas x `DB_POOL_MAX`. Prod ceiling is 24 x 10 = **240**. At 2-3k rps that's likely plenty per pod, but 240 may exceed what the DB can accept alongside other clients. A scale-up during a traffic spike is exactly when it would be exhausted, so HPA could make an incident worse. Options: lower `DB_POOL_MAX`/`maxReplicas`, or put a pooler (PgBouncer / provider proxy) in front. This needs an answer before go-live.

## Assumptions

- Separate clusters for staging and prod (Argo destinations `staging-cluster`, `prod-cluster`), K8s >= 1.27 (CronJob `timeZone`), 3 zones.
- ingress-nginx, cert-manager (`letsencrypt` issuer), External Secrets Operator, Argo CD, Prometheus Operator already exist.
- Image runs `uvicorn` as UID 10001 on :8000, exposes `/healthz`, `/readyz`, `/metrics`; batch is `python -m app.batch`. The `app/` directory here is a **sample stand-in** for the real code.
- Hostnames, secret paths, DB CIDR (10.0.0.0/16), batch schedule (04:00 UTC) are placeholders.
- Webhook provider needs a public HTTPS endpoint; it does not publish source IPs I can rely on.
- A single replica can handle roughly 150-250 rps. **Unmeasured guess**, which is why min/max are what they are.

## Questions before this goes live

1. What is Postgres `max_connections`, who else uses it, and is there a pooler? (see above)
2. What does the load profile look like per pod? I need a load test to set requests and HPA target.
3. What is the SLO? Alert thresholds in `MONITORING.md` are guesses until there is one.
4. Is the batch job really idempotent against production data, how long does it run, and does it lock rows that request traffic needs?
5. What happens to webhooks received while the service is down: does the provider retry, for how long? Is losing one acceptable?
6. Does the provider publish IPs/mTLS we can restrict to on the ingress?
7. Rollback plan for DB migrations: are they backward compatible with the previous app version (needed for rolling deploys)?
8. Who is on call, and where do pages go?

## Left out (and why)

- **Prometheus rules / dashboards / ServiceMonitor as code**: asked for in writing only; see `MONITORING.md`.
- **Canary / progressive delivery** (Argo Rollouts): rolling update + fast rollback is enough for v1; I'd add it once SLO-based analysis exists.
- **Separate Deployment for webhooks**: would stop a webhook storm from competing with mobile traffic. Worth it if the provider is bursty; not at this stage.
- **Multi-region / DR, cost tuning, cluster autoscaler config, service mesh, WAF**: assumed handled by the platform or out of two-hour scope.
- **Real app tests, DB migrations workflow**: sample app only has smoke tests.
- **Load test**: the single most valuable thing missing.
