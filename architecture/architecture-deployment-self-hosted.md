# Deployment Path 2: Self-Hosted Cloud Infrastructure

**Version:** 2.0-template | **License:** CC BY 4.0
**Source:** Derived from [Reference Architecture](./reference-architecture.md) §6 and [Shared Responsibility Model](./shared-responsibility.md)
**Purpose:** Architecture guide for deploying the governance platform onto your own managed cloud infrastructure using an AI coding agent for development. Covers the target architecture, production pivot from prototype, cost model, security responsibilities, and decision criteria.

---

## Overview

An AI coding agent drafts and executes code against the codified specification. The build runs locally during development, then deploys onto your own cloud infrastructure: container orchestration, managed PostgreSQL, serverless functions, and Infrastructure as Code. You own everything.

**What you get:** Full data sovereignty, network-level isolation, complete governance over the CI/CD pipeline, and the ability to integrate with any internal system without platform constraints.

**What you own:** Everything. Infrastructure, application code, data, agent behaviour, invariant enforcement, security tooling, and the deployment pipeline.

**What the cloud provider owns:** Physical infrastructure, hypervisor, and managed service engine uptime (compute, database engine, networking fabric).

---

## Target Architecture

### Component Stack

| Component | Implementation | Notes |
|---|---|---|
| **Frontend** | React (or equivalent SPA) | Served via Nginx in container. Static build artefact. |
| **Backend** | Python FastAPI (or equivalent) | API-layer gate enforcement. All invariants checked here. |
| **Database** | PostgreSQL on managed relational database service | RLS policies, schema-level constraints, generated columns for computed scores. |
| **Container orchestration** | ECS Fargate / EKS / GKE / equivalent | Serverless containers preferred. No node management overhead. |
| **Load balancer** | Application Load Balancer | HTTPS termination. Health checks on backend containers. |
| **File storage** | S3-compatible object storage | Evidence attachments, audit artefact exports. Presigned URL upload/download. |
| **Identity** | OIDC provider (Okta, Azure AD, Cognito, etc.) | Abstracted behind a provider interface. Group claims mapped to platform roles. |
| **Secrets** | Managed secrets service | DB credentials, OIDC config, API keys. Injected into container environment. |
| **Infrastructure as Code** | Terraform / CDK / Pulumi | Entire environment reproducible and auditable. No manual provisioning. |
| **CI/CD** | GitHub Actions / GitLab CI / equivalent | Automated build, test, scan, deploy pipeline. |

### Architecture Diagram (Logical)

```
┌─────────────────────────────────────────────────────────┐
│                      Internet                           │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTPS
                       ↓
              ┌────────────────┐
              │  Load Balancer │  ← TLS termination, health checks
              └───────┬────────┘
                      │
         ┌────────────┴────────────┐
         ↓                         ↓
┌────────────────┐        ┌────────────────┐
│   Frontend     │        │    Backend     │  ← API-layer gate enforcement
│   (Container)  │        │   (Container)  │  ← RBAC middleware
└────────────────┘        └───────┬────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ↓             ↓              ↓
           ┌──────────────┐ ┌─────────┐  ┌──────────────┐
           │  PostgreSQL  │ │   S3    │  │ OIDC Provider│
           │  (Managed)   │ │(Object) │  │  (External)  │
           └──────────────┘ └─────────┘  └──────────────┘
                  │
                  ↓
           ┌──────────────┐
           │ Secrets Mgr  │
           └──────────────┘
```

---

## Production Pivot from Prototype

The application is designed to minimise production code changes. A local prototype using SQLite and local file storage requires changes to exactly four files to pivot to cloud-hosted PostgreSQL.

### 4-File Pivot

| File | Change | Effort |
|---|---|---|
| `database.py` (or equivalent) | Read `DATABASE_URL` from environment variable instead of hardcoded SQLite path | Low |
| `attachments.py` (or equivalent) | Replace local file writes with S3-compatible presigned URL upload and download | Medium |
| `auth/provider.py` (or equivalent) | Implement OIDC token validation using JWKS endpoint (stub already in place from prototype) | Medium |
| `main.py` (or equivalent) | Read `ALLOWED_ORIGINS` from environment variable; set `COOKIE_SECURE=true` for HTTPS | Low |

**Critical constraint:** No changes to models, schemas, CRUD operations, or governance logic are required. If the pivot requires modifying business logic, the prototype's abstraction boundaries were not clean enough.

### 7-Step Deployment Sequence

| Step | Task | Effort | Details |
|---|---|---|---|
| 1. Containerise | Add Dockerfile for backend (FastAPI + uvicorn) and frontend (React + Nginx). Create docker-compose.yml for local dev with PostgreSQL. | Low | Test full lifecycle locally against PostgreSQL before cloud deployment. |
| 2. Database | Replace local DB with managed PostgreSQL via `DATABASE_URL` env var. Run full migration. Seed with initial roles and test data. | Low | Validate all constraints, generated columns, and RLS policies work on PostgreSQL. |
| 3. File storage | Replace local `/uploads` with S3-compatible presigned URL upload and download. Update attachment endpoints. | Medium | Configure bucket policies, encryption-at-rest, and access logging. |
| 4. Secrets | Move all secrets to managed secrets service (DB URL, SECRET_KEY, OIDC vars). Inject into container task definition. | Low | No secrets in code, environment files, or container images. |
| 5. Infrastructure | Push Docker images to container registry. Create cluster and task definitions. Configure load balancer with HTTPS listener. Set DNS. | Medium | Use IaC (Terraform/CDK). No manual console provisioning. |
| 6. Auth | Set `AUTH_PROVIDER=oidc` in secrets. Configure OIDC app in identity provider. Map group claims to platform role groups. Implement `OIDCProvider.validate_token()`. | Medium | Test role sync with at least 3 different role groups before go-live. |
| 7. CORS | Update `ALLOWED_ORIGINS` to production domain. Set `COOKIE_SECURE=true`. Verify cross-origin behaviour. | Low | Test from a different origin to confirm CORS is enforced. |

---

## Cost Model (Reference)

Estimated monthly cost for a low-traffic, single-environment deployment. Actual costs vary by cloud provider, region, and usage patterns.

| Service | Configuration | Estimated Monthly Cost |
|---|---|---|
| Container compute | 2 tasks × 0.25 vCPU / 0.5 GB each (frontend + backend) | ~$15-20 |
| Managed PostgreSQL | Smallest instance, 20 GB SSD, single-AZ | ~$15-20 |
| Application Load Balancer | Low traffic, HTTPS listener | ~$18 |
| Object storage | < 10 GB for attachments and evidence | ~$2-3 |
| TLS certificate | Managed (e.g. ACM) | Free |
| DNS | 1 hosted zone | ~$0.50 |
| Container registry | Docker image storage | ~$1-2 |
| Secrets manager | ~10 secrets | ~$0.40 |
| **Total** | | **~$52-64/month** |

### Cost Scaling Considerations

| Growth Factor | Impact | Mitigation |
|---|---|---|
| More users | Minimal until >50 concurrent. Container scaling is incremental. | Auto-scaling policy on container tasks. |
| More data | PostgreSQL storage grows linearly. Evidence attachments grow in S3. | Monitor storage. Upgrade instance tier when approaching limits. |
| Multi-environment | Each environment (dev, staging, prod) duplicates infrastructure cost. | Use smaller instances for non-prod. Share the load balancer where possible. |
| Multi-region | Full stack duplication per region. | Only deploy multi-region if regulatory requirements mandate it. |

---

## Shared Responsibility Across Service Models

This path spans all three cloud service models simultaneously. The responsibility boundary shifts at each layer.

### IaaS (Compute, VPC, Node Groups)

**Cloud provider:** Secures underlying compute, network, and storage fabric.
**You:** Operating system patching (if using EC2/VMs), network configuration (VPC, security groups, NACLs), and everything running on top of the compute layer. Fargate/serverless shifts OS patching to the provider.

### PaaS (Managed Database, Serverless Functions, API Gateway)

**Cloud provider:** Manages the runtime, engine uptime, and patching of the managed service.
**You:** Data model design, access controls (database users, connection security, RLS policies), and all application logic running inside those services.

### Supporting Services (Identity, Audit Logging, Secrets Management)

**Cloud provider:** Manages the service engine.
**You:** Configuration. Who has access. What is logged. How secrets are scoped, rotated, and who can read them.

---

## Security Responsibilities (Yours)

Everything below is your responsibility. The cloud provider does not do this for you.

### Application Security

| Responsibility | Detail |
|---|---|
| **AppSec scanning** | SAST and DAST integrated into CI/CD pipeline. AI-generated code is subject to the same scanning standards as any human-written code. |
| **Dependency scanning** | Automated vulnerability scanning of all dependencies (npm, pip, etc.) on every build. |
| **Container scanning** | Image vulnerability scanning before push to registry. No images with critical CVEs in production. |
| **Secrets hygiene** | No secrets in code, Dockerfiles, environment files, or CI/CD logs. All secrets via managed secrets service. |

### Infrastructure Security

| Responsibility | Detail |
|---|---|
| **Network isolation** | Backend containers not directly internet-accessible. Load balancer is the only ingress point. Database in private subnet. |
| **Encryption** | TLS in transit (enforced at load balancer). Encryption at rest on database and object storage (provider-managed or customer-managed keys). |
| **Access control** | IAM roles scoped to least privilege. No shared credentials. Service accounts for CI/CD with minimal permissions. |
| **Logging and monitoring** | Access logs on load balancer. Query logs on database. CloudTrail or equivalent for infrastructure changes. Application-level audit_log table for governance events. |
| **Backup and recovery** | Automated database backups with tested restore procedure. RTO and RPO defined and validated. |

### Governance Controls

| Responsibility | Detail |
|---|---|
| **IaC governance** | All infrastructure changes via IaC. No manual console changes in production. Code review required for IaC changes. |
| **Change management** | Deployment pipeline enforces: build → test → scan → approve → deploy. No direct pushes to production. |
| **Incident response** | Runbook for platform incidents (database failure, container crash, auth outage). Tested at least annually. |

---

## Vendor Lock-in

**Overall risk: LOW.** Specification is portable. IaC is reproducible. PostgreSQL is standard. Moving providers requires IaC rewrite, not application rewrite. Full assessment: [Shared Responsibility Model](./shared-responsibility.md#6-vendor-lock-in-comparison).

## Decision Gate

Before committing to self-hosted production deployment, confirm:

```
□ Infrastructure engineering capacity identified (internal or contracted)
□ IaC tooling selected and team is proficient
□ CI/CD pipeline designed with AppSec scanning integrated
□ OIDC provider selected and group-to-role mapping designed
□ Cost model projected for 12-month steady state including multi-environment
□ Backup and recovery RTO/RPO defined and testable
□ Incident response runbook drafted for platform-level failures
```

For guidance on when this path is appropriate vs. SaaS or vendor platforms: [Shared Responsibility Model §7](./shared-responsibility.md#7-decision-framework).

---

*This deployment guide is released under CC BY 4.0. Adapt freely with attribution.*
