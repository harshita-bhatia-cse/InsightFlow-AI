# Layer 4 Implementation Roadmap

Layer 4 is being implemented incrementally. Each phase must preserve the
existing Layer 1-3 contracts and pass the relevant tests before the next phase
begins.

## Phase 0: Audit and baseline

- [x] Run the existing test suite.
- [x] Map the application architecture and persistence model.
- [x] Record security and authorization risks.
- [x] Publish this audit and roadmap.

## Phase 1: Database migration foundation

- [x] Add and configure Alembic.
- [x] Import all model metadata into migration configuration.
- [x] Inspect the actual PostgreSQL schema before choosing a baseline strategy.
- [ ] Create a reviewed, reversible migration path.
- [ ] Remove production reliance on import-time `create_all()`.
- [ ] Add migration verification tests.

## Phase 2: Configuration and authentication hardening

- [x] Add centralized environment-aware settings.
- [x] Add `.env.example` without secrets.
- [x] Require a strong production signing secret.
- [x] Make token settings configurable.
- [x] Add refresh-token rotation and revocation.
- [ ] Add password-reset records and workflow.
- [ ] Add authentication security tests.

## Phase 3: Authorization and auditability

- [ ] Complete the audit of every route, including legacy routes.
- [x] Preserve centralized workspace, project, dataset, and role checks.
- [x] Add explicit final-owner protection for project-member roles.
- [x] Add durable authentication audit events and request correlation IDs.
- [x] Add cross-tenant and audit-event tests for the implemented paths.

## Phase 4: Collaboration and upload boundaries

- [ ] Add workspace memberships and roles.
- [ ] Add secure invitation lifecycle and configurable email adapter.
- [ ] Extract upload service, repository, validators, and storage.
- [ ] Preserve synchronous upload behavior unless workload evidence justifies
  background jobs.

## Phase 5: Operations and delivery

- [x] Add liveness/readiness checks and request correlation.
- [ ] Add structured logs, metrics, and reliability
  controls.
- [ ] Add rate limiting and security headers.
- [x] Add Docker and compose deployment infrastructure.
- [x] Add CI checks for tests and image builds.
- [ ] Add migration, linting, typing, and dependency checks.
- [ ] Document backup, restore, RPO, and RTO procedures and verify a restore.

## Definition of done

Layer 4 is complete only when the required phases have implementation,
automated verification, operational documentation, and a clean migration and
deployment path. Passing the existing unit suite alone is not sufficient.
