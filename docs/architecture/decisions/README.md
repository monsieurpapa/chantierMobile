# Architecture Decision Records

Short records of decisions that aren't obvious from reading the code alone — what we
chose, why, and what it costs. New ADRs are numbered sequentially and never renumbered
or deleted once merged; a reversed decision gets a new ADR marking the old one
superseded, rather than rewriting history.

| # | Decision |
|---|---|
| [0001](0001-cabinet-multi-tenancy.md) | Cabinet as the multi-tenancy boundary |
| [0002](0002-soft-delete-base-model.md) | Soft delete and audit fields via a shared BaseModel |
| [0003](0003-state-machines-in-model-clean.md) | Status transitions validated in `model.clean()`, not just in views |
| [0004](0004-session-idle-timeout.md) | 15-minute session idle timeout via middleware |
| [0005](0005-separate-payroll-tracks.md) | Separate payroll tracks for ouvriers and ingénieurs/staff |

## Template for a new ADR

```markdown
# NNNN — Short title

**Status**: Proposed | Accepted | Superseded by NNNN

## Context
What problem or constraint forced a decision?

## Decision
What was decided, concretely.

## Consequences
What this makes easier, harder, or costs — including any trade-off knowingly accepted.
```
