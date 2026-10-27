# Delivery: from commit to prod

**Principle:** git is the source of truth for what runs; CI builds and proves an artifact once; promotion moves the *same digest* forward.

```
PR -> app-ci (lint, test, build) -> merge to main
   -> build, scan (trivy), sign (cosign), push by digest
   -> promote-staging: bot PR bumps `image.digest` in `values-staging.yaml` -> auto-merge when validate-manifests passes
   -> Argo CD syncs staging
   -> smoke/verification, soak
   -> promote-prod (manual, environment approval): reads the digest *from staging*, verifies signature, opens PR for prod
   -> CODEOWNERS review + merge -> Argo CD syncs prod (rolling update)
```

## Decisions

- **GitOps (Argo CD) rather than `kubectl apply` from CI.** CI needs no cluster credentials, drift is self-healed, and every change to prod is a reviewed commit with an audit trail. Rollback is `git revert`.
- **Digests, not tags.** Tags are mutable; the digest that passed staging is the one that reaches prod.
- **Prod can only get what staging has.** `promote-prod` takes no input; it copies the staging digest. No skipping staging.
- **Two human gates for prod**: the GitHub `production` environment approval, then the PR review. For a payments-adjacent service that's deliberate; I'd drop one once confidence and SLO-based checks exist.
- **Manifests are validated on every PR**: `helm lint` and `helm template` for both environments, kubeconform (including the ExternalSecret CRD), trivy config scan, `required` checks in the chart fail the render if host, secret path or digest is missing.
- **Config differs between environments only in the values files** (host, secret path, replica bounds, pool size), so staging is a meaningful rehearsal.

## What gates staging -> prod

Today: time in staging plus a human. What I'd want next: automated post-deploy checks in staging (synthetic requests, signed test webhook, error rate and p99 compared with baseline) so the prod workflow can refuse to run when staging is unhealthy. Not built here.

## Rollback and failure modes

- Bad app version: revert the prod PR; Argo rolls back. Because `maxUnavailable: 0`, a version that fails readiness never takes traffic and the rollout just stalls rather than causing an outage.
- Bad manifest: caught by validate-manifests; `selfHeal` reverts manual drift.
- DB migrations must be backward compatible with the previous version (expand/contract), since rollback does not roll the schema back.
- Argo itself down: workloads keep running; only deploys pause.

## Setup this assumes (not in repo)

Branch protection on `main` (required checks: `validate-manifests`, `app-ci`), CODEOWNERS for `charts/payments-api/values-prod.yaml`, `production` environment with reviewers, and "allow auto-merge" enabled.
