# payments-api-deploy

Kubernetes deployment for the payments-api (FastAPI on :8000, Postgres, payments webhooks, daily batch).
Helm chart, delivered by GitOps (Argo CD) from GitHub Actions. Start with [docs/DESIGN.md](docs/DESIGN.md).

## Runtime architecture

```mermaid
flowchart LR
    Mobile["Mobile app<br/>2-3k rps at peak"] -->|HTTPS| Ing
    Provider["Payments provider"] -->|"HTTPS webhooks<br/>(HMAC signed)"| Ing

    subgraph Cluster["Kubernetes cluster (namespace payments-api-env)"]
        Ing["Ingress (nginx + cert-manager TLS)"] --> Svc["Service :80"]
        Svc --> P1["API pod<br/>zone a"]
        Svc --> P2["API pod<br/>zone b"]
        Svc --> P3["API pod<br/>zone c"]
        HPA["HPA<br/>CPU 60%<br/>prod 6 to 24 pods"] -.scales.-> Svc
        Cron["CronJob daily batch<br/>same image, concurrency Forbid"]
        ESO["External Secrets Operator"] -.creates Secret.-> P1
        ESO -.creates Secret.-> Cron
    end

    Store[("Secret store")] --> ESO
    P1 & P2 & P3 -->|"5432, pool max 10 per pod"| DB[("Managed Postgres<br/>outside cluster")]
    Cron -->|5432| DB
    Prom["Prometheus"] -.scrapes /metrics.-> P1
```

## Delivery flow

```mermaid
flowchart TD
    PR["Pull request"] --> CI["app-ci<br/>lint, test"]
    CI -->|merge to main| Build["Build image<br/>Trivy scan, cosign sign<br/>push, get digest"]
    Build --> PS["promote-staging<br/>sets image.digest in values-staging.yaml"]
    PS --> V1["validate-manifests<br/>helm lint, template, kubeconform, Trivy"]
    V1 -->|auto-merge| Git[("main branch<br/>source of truth")]
    Git --> ArgoS["Argo CD syncs staging"]
    ArgoS --> Soak["Verify and soak in staging"]
    Soak -->|manual run| PP["promote-prod<br/>environment approval<br/>copies staging digest, verifies signature"]
    PP --> V2["Prod PR<br/>validate-manifests + CODEOWNERS review"]
    V2 -->|merge| Git
    Git --> ArgoP["Argo CD syncs prod<br/>rolling update, maxUnavailable 0"]
    ArgoP -.bad release.-> Rev["git revert the PR<br/>Argo rolls back"]
```

## What happens on a pod rollout

```mermaid
sequenceDiagram
    participant A as Argo CD
    participant K as Kubernetes
    participant N as New pod
    participant O as Old pod
    participant L as Ingress / endpoints

    A->>K: apply new digest
    K->>N: start (startupProbe on /healthz)
    N-->>K: /readyz OK
    K->>L: add N to endpoints
    K->>O: remove from endpoints, preStop sleep 10s
    Note over O,L: In-flight requests drain
    K->>O: SIGTERM, uvicorn graceful shutdown (30s)
    Note over K: If N never becomes ready, rollout stalls and old pods keep serving
```

## Repository layout

```
app/                    Sample FastAPI service + batch job (stand-in for the real code)
tests/                  Smoke tests
Dockerfile
charts/payments-api/    Helm chart: Deployment, Service, Ingress, HPA, PDB, ConfigMap, ExternalSecret, CronJob, NetworkPolicy
                        values.yaml + values-staging.yaml + values-prod.yaml
argocd/                 Argo CD Applications (GitOps)
.github/workflows/      app-ci, validate-manifests, promote-staging, promote-prod
docs/DESIGN.md          Decisions, assumptions, open questions, what was left out   <- start here
docs/DELIVERY.md        Staging -> prod
docs/MONITORING.md      Health, 3am pages vs next-morning
```

## Try it locally

```sh
pip install -r requirements-dev.txt && pytest -q
helm lint charts/payments-api -f charts/payments-api/values-prod.yaml
helm template payments-api charts/payments-api -f charts/payments-api/values-prod.yaml
```

Placeholders to fill before use: image org (`example-org`), hostnames, secret paths, DB CIDR, Argo repo URL/cluster names, and the initial image digest in each values file.
