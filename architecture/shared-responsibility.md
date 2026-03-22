# Shared Responsibility Model

**Version:** 1.0 | **License:** CC BY 4.0
**Source:** Derived from [Reference Architecture](./reference-architecture.md) §6 and both deployment path documents.
**Purpose:** Comparative analysis of security responsibility boundaries across three deployment models for governance platforms built with agentic AI. Covers what the platform/provider secures, what you own, observed failure patterns, and a decision framework for selecting the appropriate deployment path.

> **Design principle:** The responsibility boundary must be explicit before the first build starts. Ambiguity in ownership is the root cause of the failure patterns documented below.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Deployment Path Comparison](#2-deployment-path-comparison)
3. [Responsibility Matrix](#3-responsibility-matrix)
4. [Path 1: Agentic SaaS Platforms](#4-path-1-agentic-saas-platforms)
5. [Path 2: Self-Hosted Cloud Infrastructure](#5-path-2-self-hosted-cloud-infrastructure)
6. [Vendor Lock-in Comparison](#6-vendor-lock-in-comparison)
7. [Decision Framework](#7-decision-framework)
8. [Observed Failure Patterns](#8-observed-failure-patterns)

---

## 1. Overview

Building a governance platform with agentic AI introduces a shared responsibility boundary that is distinct from traditional SaaS or IaaS models. The AI agent is a third actor: it generates code, creates database structures, and modifies application logic. The question "who is responsible for the security of the generated output?" must be answered before the first prompt.

Three deployment paths are available. Each shifts the responsibility boundary differently.

| Path | Builder Provides | Platform/Provider Provides | Agent Generates |
|---|---|---|---|
| **Path 1: Agentic SaaS** | Specification, prompts, RBAC config, data model, invariant enforcement validation | Hosting, database engine, auth, TLS, deployment pipeline | Application code, schema DDL, API endpoints, UI components |
| **Path 2: Self-Hosted** | Specification, prompts, infrastructure (IaC), CI/CD, AppSec, all operations | Compute fabric, managed service engines (DB, storage, networking) | Application code, schema DDL, API endpoints, UI components |

In both paths, the agent generates the same artefacts. The difference is who operates and secures the runtime.

---

## 2. Deployment Path Comparison

| Dimension | Path 1: Agentic SaaS | Path 2: Self-Hosted |
|---|---|---|
| **Speed to first deployment** | Hours to days | Days to weeks |
| **Infrastructure overhead** | None (platform-managed) | Full (IaC, CI/CD, monitoring) |
| **Data sovereignty** | Platform-hosted (review DPA terms) | Full control (your VPC, your region) |
| **AppSec scanning** | Manual post-build or CI/CD via GitHub sync | Integrated into your pipeline |
| **Cost model** | Per-prompt + per-operation + hosting | Infrastructure + compute + storage |
| **Vendor lock-in** | Medium (SaaS) to Low (GitHub-connected) | Low |
| **Team requirement** | GRC practitioner + specification | GRC practitioner + infrastructure engineer |
| **Production readiness** | Prototype to stakeholder demo. Production requires validation. | Production-grade with proper pipeline |

---

## 3. Responsibility Matrix

### Application Layer

| Responsibility | Path 1: Agentic SaaS | Path 2: Self-Hosted |
|---|---|---|
| Application code correctness | **You** (validate agent output) | **You** (validate agent output) |
| Schema design and integrity | **You** (specify) / Agent (generates) | **You** (specify) / Agent (generates) |
| Row Level Security (RLS) | **You** (validate against RBAC spec) | **You** (validate against RBAC spec) |
| API endpoint security | **You** (validate role checks) | **You** (validate role checks) |
| Invariant enforcement | **You** (validate all paths) | **You** (validate all paths) |
| Input validation | **You** / Agent (generated, must validate) | **You** / Agent (generated, must validate) |
| Agent permission scope | **You** (define in specification) | **You** (define in specification) |

**Key insight:** Application-layer security responsibility is identical in both paths. The agent generates the code. You validate it. The platform does not validate governance logic correctness for you.

### Infrastructure Layer

| Responsibility | Path 1: Agentic SaaS | Path 2: Self-Hosted |
|---|---|---|
| Hosting infrastructure | **Platform** | **You** (IaC) |
| Database engine uptime | **Platform** | **Cloud provider** (managed service) |
| TLS / HTTPS | **Platform** | **You** (load balancer + certificate) |
| Network isolation | **Platform** | **You** (VPC, security groups, private subnets) |
| Container orchestration | **Platform** | **You** (ECS/EKS/GKE) |
| OS patching | **Platform** | **You** or **Cloud provider** (serverless shifts this) |
| Backup and recovery | **Platform** (verify SLA) | **You** (automated backups, tested restore) |
| Encryption at rest | **Platform** (verify) | **You** (configure on DB and storage) |
| Encryption in transit | **Platform** (TLS by default) | **You** (enforce at load balancer) |

### Identity and Access

| Responsibility | Path 1: Agentic SaaS | Path 2: Self-Hosted |
|---|---|---|
| Authentication mechanism | **Platform** (built-in auth) | **You** (OIDC provider integration) |
| RBAC role definitions | **You** | **You** |
| Role-to-user assignment | **You** | **You** |
| Session management | **Platform** | **You** (token validation, session config) |
| SSO / OIDC integration | Platform-dependent | **You** (full control) |

### Data Governance

| Responsibility | Path 1: Agentic SaaS | Path 2: Self-Hosted |
|---|---|---|
| Data residency | **Platform** (review DPA, region config) | **You** (choose region, enforce in IaC) |
| Data processing terms | **Platform** (review ToS for AI model usage) | **Cloud provider** (standard DPA) |
| Data portability | **You** (export regularly) | **You** (full ownership, standard formats) |
| Audit logging | **You** (application-level audit_log table) | **You** (application + infrastructure logging) |
| Data retention and deletion | **You** (application logic) + **Platform** (infra) | **You** (full control) |

---

## 4. Path 1: Agentic SaaS Platforms

### What the Platform Secures

The platform provides managed infrastructure equivalent to a PaaS: database engine, authentication service, TLS termination, deployment pipeline, and hosting. The platform's security certifications (SOC 2, ISO 27001, etc.) cover this infrastructure layer.

### What the Platform Does Not Secure

The platform's security certification does not extend to your application. The generated code, the schema design, the RLS policies, the API endpoint role checks, and the invariant enforcement are all your responsibility. The platform executes what the agent builds. If the agent builds insecure code, the platform runs insecure code.

### Two Operating Models

**Model A: GitHub-Connected (recommended).** Codebase lives in GitHub. Two-way sync. Full commit history. AppSec scanning in your CI/CD pipeline. Reduced vendor lock-in. See [deployment-saas.md](./deployment-saas.md) for full detail.

**Model B: Platform-Native.** Everything lives inside the platform. Faster to start. Higher lock-in. Requires explicit data portability planning and regular exports.

Full detail: [Deployment Path 1: Agentic SaaS](./deployment-saas.md)

---

## 5. Path 2: Self-Hosted Cloud Infrastructure

### What You Own

Everything. Infrastructure, application code, data, agent behaviour, invariant enforcement, security tooling, deployment pipeline, and the operational burden.

### What the Cloud Provider Owns

Physical infrastructure, hypervisor, and managed service engine uptime. The standard IaaS/PaaS shared responsibility model applies at the infrastructure layer.

### The Responsibility Stack

| Layer | Model | Provider Secures | You Secure |
|---|---|---|---|
| Compute, VPC, networking | IaaS | Hardware, hypervisor, network fabric | OS (if EC2), security groups, NACLs, routing |
| Managed database, serverless | PaaS | Engine uptime, patching | Schema, access controls, RLS, connection security |
| Identity, secrets, logging | Supporting services | Service engine | Configuration, access policies, rotation, scope |
| Application | Your code | Nothing | Everything: code, logic, security, correctness |

Full detail: [Deployment Path 2: Self-Hosted](./deployment-self-hosted.md)

---

## 6. Vendor Lock-in Comparison

| Component | Path 1A: GitHub-Connected | Path 1B: Platform-Native | Path 2: Self-Hosted |
|---|---|---|---|
| **Specification** | Portable (markdown) | Portable (markdown) | Portable (markdown) |
| **Codebase** | Portable (GitHub) | Platform-native (export required) | Portable (your repo) |
| **Database schema** | Portable (PostgreSQL DDL) | Portable (PostgreSQL DDL) | Portable (PostgreSQL DDL) |
| **Database data** | Platform-hosted (export required) | Platform-hosted (export required) | Your infrastructure |
| **Authentication** | Platform-native (migration required) | Platform-native (migration required) | Your OIDC provider |
| **File storage** | Platform-native | Platform-native | Your S3-compatible storage |
| **Overall risk** | **MEDIUM** | **HIGH** | **LOW** |

**The specification is always portable.** Regardless of deployment path, the codified rules, invariants, state transitions, and scoring model are markdown files that you own. If you need to migrate from one path to another, the specification is the rebuilding blueprint. The generated code is disposable. The specification is the asset.

---

## 7. Decision Framework

### Choose Path 1 (Agentic SaaS) when:

- Speed to prototype or stakeholder demo is the priority
- No infrastructure engineering capacity available
- Data classification permits platform-hosted storage (review DPA)
- Vendor lock-in risk is acceptable (or mitigated by GitHub sync)
- Budget favours per-use consumption over fixed infrastructure cost

### Choose Path 2 (Self-Hosted) when:

- Data sovereignty is a hard requirement (regulatory, contractual, or policy)
- Infrastructure engineering capacity is available (internal or contracted)
- Production deployment with full CI/CD, AppSec, and monitoring pipeline is required
- Long-term cost optimisation favours fixed infrastructure over per-prompt consumption
- Vendor lock-in must be minimised

### Choose a combination when:

- Prototype on Path 1 (SaaS) for rapid validation and stakeholder feedback
- Pivot to Path 2 (self-hosted) for production deployment using the 4-file pivot documented in [deployment-self-hosted.md](./deployment-self-hosted.md)
- The specification and schema are portable between paths. The application code may require adaptation but the governance logic does not change.

---

## 8. Observed Failure Patterns

### Pattern 1: Agent Permission Overreach

**Observed in:** Path 1 (both models)
**Description:** Without explicit scope constraints, agents default to broad database privileges. Observed: bulk deletes, test data creation in production tables, schema modifications without instruction.
**Root cause:** The specification did not define agent permission scope.
**Mitigation:** Define what the agent may and may not do before the first prompt. Explicitly: which tables, which operations (CREATE/READ/UPDATE/DELETE), which are prohibited.

### Pattern 2: Misconfigured Application-Layer Controls

**Observed in:** Both paths
**Description:** AI-generated scaffolding creates auth flows, RLS policies, and API endpoints. Their existence does not confirm correctness. RLS policies may not enforce correct data isolation. API endpoints may rely on UI-level hiding rather than server-side role checks.
**Root cause:** The specification did not define the expected behaviour of generated controls precisely enough for validation.
**Mitigation:** After initial build, validate every RLS policy, every API endpoint role check, and every role definition against the codified specification. Treat this as a mandatory gate before any stakeholder access.

### Pattern 3: Assumed Infrastructure Security

**Observed in:** Path 1
**Description:** Builder assumes that because the platform is SOC 2 certified, the application is secure. Platform certification covers infrastructure. Application security is the builder's responsibility.
**Root cause:** Misunderstanding of the shared responsibility boundary.
**Mitigation:** This document. Read it before the first prompt. Accept the boundary. Validate accordingly.

### Pattern 4: Data Portability Surprise

**Observed in:** Path 1B (platform-native)
**Description:** Builder discovers after significant data entry that the platform does not support bulk data export, or that exported data lacks relational integrity (IDs change, FKs break).
**Root cause:** Portability was not tested before committing production data.
**Mitigation:** Confirm export capability before the first production record is created. Export a test dataset and verify relational integrity is preserved.

---

*This shared responsibility model is released under CC BY 4.0. Adapt freely with attribution.*
