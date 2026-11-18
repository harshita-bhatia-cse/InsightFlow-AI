# Layer 4 Architecture Audit

## Scope and baseline

This audit records the repository state before Layer 4 implementation. The
baseline test suite passes with 45 tests and 2 dependency deprecation warnings.

## Current architecture

InsightFlow is a layered modular monolith:

- FastAPI routes are defined in `app/main.py` and feature routers under
  `app/workspaces`, `app/projects`, `app/datasets`, and `app/permissions`.
- SQLAlchemy models and sessions are defined under `app/database`.
- Analytics services are grouped under `app/analytics`.
- Upload processing, file storage, profiling, and orchestration are currently
  coordinated from `app/main.py` and supporting services.
- Streamlit provides the dashboard in `dashboard/app.py`.
- PostgreSQL is the intended production database.

## Persistence model

The current SQLAlchemy metadata includes:

- `users`
- `workspaces`
- `projects`
- `project_members`
- `datasets`
- `pipeline_runs`
- `dataset_versions`
- `dataset_profiles`
- `quality_monitoring_snapshots`
- `dataset_analytics`
- `dataset_insights`
- `dataset_recommendations`

Foreign keys provide the principal ownership chain:

```text
users -> workspaces -> projects -> datasets
                         |
                         -> project_members
```

## API surfaces

The application exposes:

- System and health endpoints.
- Registration, login, current-user, and admin-user endpoints.
- CSV upload, downloads, pipeline history, dataset preview, and version
  endpoints.
- Profiling and analytics endpoints.
- Ownership-aware workspace, project, dataset, and project-permission routers.

## Current strengths

- Existing behavior is covered by a passing automated suite.
- Project and dataset access checks are present on the newer `/api` routers.
- Analytics behavior is split into focused services.
- Uploads have UUID run tracking and separate processed/quarantine outputs.
- Database sessions are generally closed in route/service boundaries.

## Findings

### High

1. Production schema creation is performed with
   `Base.metadata.create_all(bind=engine)` during application import. This
   bypasses controlled schema versioning and can conceal drift.
2. The upload workflow remains large and coupled to `app/main.py`, making
   transaction, storage, and partial-failure behavior difficult to isolate.
3. Authorization is split between route handlers and services. Legacy routes
   require a complete tenant-isolation audit before production exposure.

### Medium

1. Database models do not yet include audit events, refresh sessions,
   password-reset records, workspace memberships, or invitations.
2. There is no migration directory or migration version table.
3. Health reporting is not separated into liveness and dependency readiness.
4. Observability is primarily application logging; request correlation and
   structured metrics are not yet established.

### Low

1. Router imports and database dependency helpers are repeated.
2. The dashboard is a single large module.
3. Production deployment and recovery procedures are not represented in the
   repository.

## Layer 4 architectural direction

Layer 4 should preserve the current API contracts and introduce:

1. Centralized configuration and migrations.
2. Explicit authorization dependencies for workspace, project, and dataset
   access.
3. Dedicated authentication/session persistence.
4. Transactionally consistent audit logging.
5. A service/repository/storage split for uploads.
6. Operational infrastructure only where justified by the existing workload.
