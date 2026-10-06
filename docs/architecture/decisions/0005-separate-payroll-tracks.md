# 0005 — Separate payroll tracks for ouvriers and ingénieurs/staff

**Status**: Accepted

## Context

Construction-site workers (ouvriers) and engineers/administrative staff are paid under
fundamentally different arrangements: an ouvrier is paid progressively, tied to a
specific chantier, often capped by a per-assignment negotiated rate
(`SiteAssignment.convention_amount`); an ingénieur or staff member draws a fixed monthly
salary unrelated to any one site. Modeling both under one generic "payroll" entity would
either force site-scoping onto a salary that has none, or lose the per-site cap logic
that ouvrier payroll depends on.

## Decision

Keep two parallel, independently-modeled payroll tracks, both following the same
brouillon → soumise → payée workflow and both disbursing from a `Caisse`, but with
different scoping and separate models:

- **`PayrollList` / `PayrollListItem`** — scoped to a `Site` (and optionally a
  `ProjectPhase`), for ouvriers. Booked to the "Main d'œuvre Ouvriers" caisse category.
- **`SalaryPaymentList` / `SalaryPaymentItem`** — scoped to a `Cabinet` (not a site), for
  `PersonnelPayrollType.INGENIEUR` (which covers both engineers and
  `AgentCategory.ADMINISTRATION` office staff, whether or not they're also assigned to a
  site). Booked to the "Salaire Ingénieurs" caisse category.

`Personnel.payroll_type` (`OUVRIER` / `INGENIEUR`) determines which track a given
person's payments flow through; the UI presents them as separate tabs under
"Liste de paie" rather than one combined list.

## Consequences

- A `Personnel` record's `payroll_type` must be set correctly at creation — there is no
  automatic inference from `personnel_type` (Employé/Tâcheron/Prestataire) or
  `agent_category` (Terrain/Administration), since the two concepts answer different
  questions (employment relationship vs. pay structure).
- Reports that need a cross-track total (e.g. total labor cost for a site) must query
  both models and combine them — there's no single `PayrollEntry` table to sum.
- Adding a third payroll arrangement in the future (e.g. piecework) should extend this
  pattern (its own model, its own tab) rather than trying to generalize the existing two
  into one polymorphic model, given how differently they're scoped and reported on.
