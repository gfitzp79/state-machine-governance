# Platform Prompt Library

**Version:** 1.0 | **License:** CC BY 4.0
**Source:** Derived from patterns proven in a production GRC platform build on an agentic SaaS deployment path (Lovable + Supabase).
**Purpose:** A reference library of copy-paste-ready prompt patterns for building governance platform modules. Each pattern is derived from a working implementation, not a hypothetical. Adapt the bracketed values to your entity, schema, and role model.

> **Companion to:** [Prompt Cycle](./prompt-cycle.md) (architectural guidance) and [Context Management](./context-management.md) (session discipline). This document is the implementation layer — what to type. Those documents explain when, why, and in what order.

> **Platform assumptions:** These prompts were developed and validated on a Lovable + Supabase stack. Core patterns (RLS, edge functions, React Query, phase gates) are portable to other agentic SaaS platforms. Schema conventions (uuid PKs, `gen_random_uuid()`, `has_role()`) are Supabase-specific and should be adapted for other database backends.

---

## Table of Contents

1. [Database and Schema](#1-database-and-schema)
2. [CRUD Registry Page](#2-crud-registry-page)
3. [Detail Page with Tabs](#3-detail-page-with-tabs)
4. [Settings and Admin Panels](#4-settings-and-admin-panels)
5. [Modal Forms](#5-modal-forms)
6. [AI-Powered Features](#6-ai-powered-features)
7. [Phase-Gated Workflows](#7-phase-gated-workflows)
8. [Linking and Relationship Management](#8-linking-and-relationship-management)
9. [Dashboard Widgets](#9-dashboard-widgets)
10. [Edge Functions](#10-edge-functions)
11. [Auth and RBAC](#11-auth-and-rbac)
12. [Naming Conventions](#12-naming-conventions)

---

## 1. Database and Schema

### 1.1 Create a New Entity Table with RLS

**When to use:** Scaffolding any new governance entity (risk, control, policy, treatment, exception). This is the baseline pattern — all governance entities share this structure.

**Preconditions:** `user_roles` table and `has_role()` function exist. `app_role` enum is defined. Supabase client is connected.

**Why it works:** The `lifecycle_state` default of `'draft'` enforces the state machine's initial state at the schema level, not the application layer. Human-readable IDs (`RISK-001`, `CTL-042`) are essential for audit trails and governance reporting — UUIDs alone are not adequate for regulatory documentation.

```
Create a new database table called `[table_name]` with the following columns:

- `id` (uuid, PK, default `gen_random_uuid()`)
- `[human_readable_id]` (text, unique, not null) — a short human-readable identifier like `RISK-001`
- `title` (text, not null)
- `description` (text, nullable)
- `lifecycle_state` (text, default `'draft'`)
- `created_by` (uuid, references `auth.users(id)`, nullable)
- `created_at` (timestamptz, default `now()`)
- `updated_at` (timestamptz, default `now()`)

Add RLS policies:
- SELECT: allow all authenticated users.
- INSERT: allow users with role `[creator_role]`.
- UPDATE: allow users with role `[editor_role]` or the row's `created_by`.
- DELETE: allow users with role `site_admin` only.

Use the `has_role(auth.uid(), '[role]')` function for all policy checks.
```

---

### 1.2 Add a Junction Table

**When to use:** Any many-to-many relationship between governance entities — risk ↔ control, policy ↔ control, risk ↔ treatment.

**Preconditions:** Both parent tables exist. `has_role()` is available.

**Critical note:** Junction tables in governance platforms often need to carry state, not just linkage. If the relationship has its own attributes (e.g. CE snapshot at assessment time for a risk ↔ control join), add those columns here rather than on either parent table. See [Scoring Model §9](../specification/scoring-model.md#9-fk-dependencies) for the CE snapshot pattern.

```
Create a junction table called `[parent_a]_[parent_b]_links` with:

- `id` (uuid, PK, default `gen_random_uuid()`)
- `[parent_a]_id` (uuid, FK → `[parent_a_table].id`, not null)
- `[parent_b]_id` (uuid, FK → `[parent_b_table].id`, not null)
- `linked_by` (uuid, nullable)
- `linked_at` (timestamptz, default `now()`)
- Unique constraint on `([parent_a]_id, [parent_b]_id)`

RLS: SELECT for all authenticated users. INSERT/DELETE for `[allowed_role]`.
```

---

## 2. CRUD Registry Page

### 2.1 Filterable Registry Page

**When to use:** Any module-level list view — Risk Register, Controls Library, Policy Register, Treatment Library.

**Preconditions:** Table exists in Supabase. React Query, shadcn/ui, and React Router are available.

**Why it works:** The `lifecycle_state` dropdown filter is the single most-used filter in governance platforms — analysts spend most of their time looking at records in a specific phase. Putting it in the top bar rather than a sidebar makes it immediately accessible. The role gate on the Create button enforces RBAC at the UI layer while schema-level RLS enforces it at the data layer.

```
Create a new page at route `/[entity-plural]` that displays all rows from the `[table_name]` table.

Layout:
- Page title: "[Entity] Register" with a subtitle describing the purpose.
- Top bar: search input (filters by `title`), a dropdown filter for `lifecycle_state`, and a "Create [Entity]" button (visible only to `[creator_role]`).
- Data table with columns:
  1. `[human_id]` — left-aligned, monospace, clickable link to `/[entity-plural]/:id`.
  2. `title` — primary text.
  3. `lifecycle_state` — rendered as a Badge with colour per state (draft=gray, active=green, retired=amber, closed=red).
  4. `created_at` — formatted as `YYYY-MM-DD`.
  5. Row action: kebab menu with "View details".
- Default sort: `created_at` descending.
- States: loading skeleton rows, empty state with guidance text and CTA button, error toast on fetch failure.
- Use TanStack React Query with key `['[entity-plural]']`.
```

---

## 3. Detail Page with Tabs

### 3.1 Entity Detail with Tabbed Layout

**When to use:** Any single-entity detail view that requires Overview, Linked Items, and History tabs. This is the standard detail page pattern across all governance modules.

**Preconditions:** Entity table exists. React Router param `:id`. shadcn Tabs component.

**Why it works:** The three-tab structure (Overview / Linked Items / History) maps directly to the three questions an analyst asks when reviewing a governance record: What is this? What is it connected to? What has happened to it? Keeping the audit log as a tab rather than a separate page means lifecycle history is always one click away.

```
Create a detail page at route `/[entity-plural]/:id` that loads a single row from `[table_name]` by `id`.

Layout:
- Breadcrumb: `[Module] > [Entity Register] > [title]`.
- Header: `[human_id]` as subtitle, `title` as H1, lifecycle badge, and action buttons (Edit, Delete — role-gated).
- Tabs:
  1. **Overview** — Card grid showing key fields: `[field_1]`, `[field_2]`, `lifecycle_state`, `created_at`, owner info.
  2. **Linked [Related Entity]** — Table of linked items from `[junction_table]` with add/remove capability for `[allowed_role]`.
  3. **History** — Audit log entries filtered by `entity_type = '[entity]'` and `entity_id = :id`, ordered newest first.

- Loading: full skeleton.
- Not found: "Entity not found" message with back link.
- All mutations use React Query `useMutation` with `onSuccess` invalidation of `['[entity]', id]`.
```

---

## 4. Settings and Admin Panels

### 4.1 Admin Settings Section with Cards

**When to use:** Platform configuration areas — RBAC settings, integration configuration, framework management.

**Preconditions:** Settings page exists. User has admin role. shadcn Card, Table, Dialog components.

```
In the Settings area, create a new section called "[Section Name]".

Layout: responsive two-card row on desktop, stacking on mobile. Glassmorphism style: `backdrop-blur-sm bg-card/80`, soft borders, muted background.
Only visible to `site_admin` role.

**Card A: "[Config Card Title]"**
- Subtitle: "[Description of what is configured here]"
- Display [N] read-only fields styled as disabled inputs with copy-to-clipboard icon buttons. Each copy shows a toast: "[Field name] copied."
- Bottom: link-style button "[View Documentation]" opening `[docs_url]` in new tab.

**Card B: "[Management Card Title]"**
- Subtitle: "[Description]"
- Table bound to `[table_name]`, ordered by `created_at` desc.
- Columns: [column_1 (text)], [column_2 (badge)], [column_3 (date)], [column_4 (user lookup)].
- Row action: delete with confirmation dialog.
- Empty state with title, subtitle, and CTA.
- "Add [Item]" button above table opens a modal form.

**Add Modal:**
- Fields: [text input for field_1], [dropdown for field_2 from enum].
- Validation: required fields, inline errors.
- Save: insert to `[table_name]`, refresh table, show success toast.
```

---

## 5. Modal Forms

### 5.1 Create/Edit Entity Modal

**When to use:** Creating or editing any governance entity. This is the standard form pattern — use it consistently across all modules.

**Preconditions:** shadcn Dialog, react-hook-form with zod validation, React Query mutations.

**Critical note on governance forms:** The `[owner_field]` pattern (populating from the `profiles` table) is essential for assigning Risk Owners, Control Owners, and Treatment Owners. These assignments have governance consequences — the platform must track named individuals, not just role labels. See [Codified Rules §2.1](../specification/codified-rules.md#21-role-definitions) for role assignment constraints.

```
Create a modal dialog for creating a new `[entity]`.

- Title: "Create [Entity]"
- Form fields:
  1. `title` — text input, required, max 200 chars.
  2. `description` — textarea, optional, max 2000 chars.
  3. `[category_field]` — Select dropdown populated from `[enum or lookup table]`.
  4. `[owner_field]` — Select dropdown populated from `profiles` table (show `full_name`).
- Validation: zod schema, inline error messages below each field.
- Actions: "Cancel" (secondary, closes modal) and "Create [Entity]" (primary).
- On submit: insert to `[table_name]` via Supabase, set `created_by` to `auth.uid()`.
- Loading: disable submit button, show "Creating…" text.
- Success: close modal, invalidate `['[entity-plural]']` query, toast "[Entity] created."
- Error: keep modal open, show inline error banner at top.
```

---

## 6. AI-Powered Features

### 6.1 AI Analysis with Recommendations

**When to use:** Adding AI-assisted analysis to any governance record — control gap analysis, risk treatment recommendations, policy alignment checks.

**Preconditions:** AI gateway is available. Edge function pattern established. Assessment and recommendation tables exist.

**Why the error handling matters:** AI gateway calls fail in ways that generic error handling misses. A `429` means rate-limited (the prompt should retry with backoff). A `402` means credits exhausted (the build itself is at risk — this requires human intervention). Handling these explicitly prevents silent failures and budget surprises.

```
Add an AI-powered "[Analysis Name]" feature to the `[Entity]` detail page.

**Edge Function:** `ai-[entity]-[action]`
- Accepts `{ [entity]Id, [entity]Content }` in the request body.
- Fetches related data from the database (e.g. all `[related_table]` rows).
- Calls the AI gateway (`[model]`) with a structured prompt.
- Parses the JSON response and returns typed recommendations.
- Handles errors: check `aiResponse.ok` before parsing, handle 429/402 status codes gracefully.
- Optionally persists recommendations to `[assessments_table]` and `[recommendations_table]`.

**Frontend Tab/Section:**
- "Generate Recommendations" button with loading spinner.
- Results rendered as a scrollable list of collapsible cards.
- Each card: icon by type, title, priority badge (high=red, medium=amber, low=blue), expandable description and suggested content.
- Checkbox selection with "Select All" / "Deselect All" toggle.
- "Apply Selected" button that links/copies the chosen recommendations.
- Assessment history: load past analyses from the database with a toggle.
```

---

## 7. Phase-Gated Workflows

### 7.1 Multi-Phase Stepper with Validation Gates

**When to use:** Any entity with a multi-phase lifecycle — the Risk 7-phase lifecycle is the reference implementation. Also applies to control lifecycle management and policy approval workflows.

**Preconditions:** Entity has a `phase` integer column. Edge function for phase advancement exists or will be created.

**Why server-side validation is non-negotiable:** Frontend-only gate checks can be bypassed. A user who knows the API can advance a risk from Phase 2 to Phase 5 without satisfying any preconditions if the gate logic only exists in the UI. The edge function is the enforcement point. The UI reflects gate state; it does not enforce it. This maps directly to the invariant design principle in [Invariants Catalogue](../specification/invariants-catalogue.md).

```
Implement a [N]-phase lifecycle stepper for `[entity]`.

**Phases:**
1. [Phase 1 Name] — [description, required fields]
2. [Phase 2 Name] — [description, required fields]
3. …
N. [Phase N Name] — [description, final state]

**Stepper UI:**
- Horizontal stepper at the top of the detail page.
- States: completed (checkmark, green), current (highlighted, blue), locked (padlock icon, gray), future (gray outline).
- Clicking a completed phase navigates back (read-only view). Clicking a locked phase shows a tooltip explaining prerequisites.

**Phase Content:**
- Each phase renders a dedicated component: `Phase[Name].tsx`.
- Current phase shows editable form fields. Previous phases show read-only summaries.
- "Advance to [Next Phase]" button at the bottom of the current phase.

**Validation (Edge Function):**
- `advance-[entity]-phase` accepts `{ [entity]Id, targetPhase }`.
- Validates all preconditions for the target phase (e.g. required fields populated, linked items exist, gate checkboxes confirmed).
- On success: updates `phase` column, inserts a `[entity]_phase_history` row, returns success.
- On failure: returns `{ error, missing_requirements: [...] }` with a 400 status.

**Frontend Validation Feedback:**
- On advance failure, highlight missing fields and show a toast listing what's needed.
```

---

## 8. Linking and Relationship Management

### 8.1 Linked Items Tab with Add/Remove

**When to use:** Any tab showing items connected via a junction table — linked controls on a risk, linked risks on a control, linked standards on a policy.

**Preconditions:** Junction table exists. Both entities have detail pages.

**Governance note:** The "exclude already-linked items" filter in the search dialog is not a UX nicety — it prevents duplicate junction rows that corrupt scoring (e.g. a control counted twice in CE calculation). This constraint should also exist as a UNIQUE constraint on the junction table itself (see §1.2).

```
Create a "[Linked Entity Plural]" tab on the `[Parent Entity]` detail page.

- Data source: `[junction_table]` filtered by `[parent_id] = :id`, joined with `[linked_table]` to get title and metadata.
- Table columns: `[linked_human_id]`, `[linked_title]`, `[linked_status badge]`, `linked_at` (formatted date), unlink button.
- Unlink action: confirmation dialog → delete junction row → invalidate query → toast.
- "Link [Entity]" button opens a search dialog:
  - Search input filters `[linked_table]` by title.
  - Results shown as a selectable list (exclude already-linked items).
  - "Link Selected" button inserts junction rows.
  - Success: close dialog, refresh tab, toast "[N] [entities] linked."
- Empty state: "[No linked entities yet]" with guidance text and "Link [Entity]" CTA.
```

---

## 9. Dashboard Widgets

### 9.1 KPI Summary Cards

**When to use:** Executive dashboard, module-level summary headers. Maps to the P0/P1/P2 KPI hierarchy in [Codified Rules §7.1](../specification/codified-rules.md#71-executive-kpis).

**Preconditions:** Data available via aggregate queries or pre-computed views.

```
Add a KPI summary row to the dashboard with [N] cards:

1. **[Metric Name]** — Count of `[table]` where `[condition]`. Icon: `[LucideIcon]`. Color accent: `[semantic token]`.
2. **[Metric Name]** — …
3. …

Layout: responsive grid, 4 columns on desktop, 2 on tablet, 1 on mobile.
Each card: icon top-left, large number, label below, subtle trend indicator if applicable.
Loading: skeleton pulse for each card.
Data fetched with React Query key `['dashboard-kpis']`, staleTime 30 seconds.
```

---

### 9.2 Chart Widget

**When to use:** Risk distribution by rating, control effectiveness breakdown, treatment status over time, SLA compliance trends.

**Preconditions:** Charting library installed. Data fetched via React Query.

```
Add a "[Chart Title]" chart widget to the dashboard.

- Chart type: [Bar | Line | Pie | Area].
- Data source: query `[table]` grouped by `[dimension]`, counting/summing `[metric]`.
- X-axis: `[dimension label]`. Y-axis: `[metric label]`.
- Colors: use design system tokens mapped to HSL values.
- Responsive container, 400px min height.
- Tooltip on hover showing exact values.
- Loading: skeleton rectangle. Empty: "No data available" centered text.
```

---

## 10. Edge Functions

### 10.1 Secure Edge Function Template

**When to use:** Any server-side operation that requires auth validation, external API calls, or business logic that must not be bypassable from the client — phase gate advancement, AI analysis, webhook receivers, SLA calculations.

**Preconditions:** Supabase client available via `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` env vars.

**Why this structure matters:** The auth check at the top of every edge function is what makes the RBAC model real. Without it, anyone with the function URL can execute operations regardless of their role. The pattern `extract JWT → verify → reject if invalid` must be present in every function that touches governance data.

```
Create an edge function at `supabase/functions/[function-name]/index.ts`.

- CORS: handle OPTIONS preflight and allow `Authorization` header.
- Auth: extract JWT from `Authorization` header, verify with Supabase client, reject if invalid (401).
- Input: parse JSON body, validate required fields `[field_1, field_2]`. Return 400 if missing.
- Logic: [describe the business logic — e.g. "fetch all controls, compare with policy content, generate recommendations"].
- Response: return JSON `{ [result_fields] }` with 200.
- Errors: catch all exceptions, return `{ error: message }` with 500. Log to console.
- If calling an AI gateway: check `aiResponse.ok` before parsing JSON. Handle 429 (rate limit) and 402 (credits exhausted) with descriptive error messages.
```

---

## 11. Auth and RBAC

### 11.1 Role-Gated Page or Section

**When to use:** Any page or UI section restricted to specific roles — admin settings, score editing, phase advancement controls, approval workflows.

**Preconditions:** `useAuth()` hook provides `userRoles` array. `ProtectedRoute` component exists.

**Critical:** The frontend gate is for UX. The RLS policy is for security. Both must exist. Removing the RLS policy because the route is protected in the frontend is the most common RBAC failure pattern in agentic SaaS builds — the agent generates the UI gate and the developer assumes it's sufficient. It is not.

```
Gate the `[Page/Section Name]` so it is only accessible to users with the `[role_1]` or `[role_2]` role.

- Wrap the route in `<ProtectedRoute requiredRoles={['[role_1]', '[role_2]']}>`.
- If the user lacks the role, show a "You don't have permission to view this page" message with a "Go to Dashboard" link. Never show a 404.
- For inline sections: conditionally render using `hasRole('[role]')`. Show a lock icon with tooltip "Requires [Role Name] access" for unauthorized users.
- Never rely on frontend checks alone — ensure corresponding RLS policies exist on the backend.
```

---

## 12. Naming Conventions

Consistent naming across the codebase reduces cognitive overhead for the agent and prevents name collision failures across sessions.

| Concept | Convention | Example |
|---|---|---|
| React Query key | `['entity-plural']` or `['entity', id]` | `['risks']`, `['policy', policyId]` |
| Page file | `src/pages/EntityList.tsx`, `src/pages/EntityDetail.tsx` | `RiskRegister.tsx`, `PolicyDetail.tsx` |
| Component file | `src/components/[module]/ComponentName.tsx` | `src/components/risk/PhaseIntake.tsx` |
| Edge function | `supabase/functions/[verb]-[entity]/index.ts` | `advance-risk-phase/index.ts` |
| Junction table | `[parent]_[child]_links` or `[parent]_[child]s` | `risk_policy_links`, `policy_controls` |
| Human ID column | `[entity]_id` (text, unique) | `risk_id`, `policy_id`, `treatment_id` |
| Audit log key | `entity_type = '[entity]'` | `entity_type = 'risk'` |

---

*This prompt library is derived from a production GRC platform build and released under CC BY 4.0. Adapt freely with attribution. For the architectural guidance that contextualises these patterns, see [Prompt Cycle](./prompt-cycle.md) and [Context Management](./context-management.md).*
