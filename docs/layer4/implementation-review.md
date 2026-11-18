# InsightFlow AI Layer 4 Implementation Review

Review date: 2026-11-18

## Executive conclusion

Layer 4 is **partially implemented and not production-ready**.

The reported 49-test result is reproducible, and the application compiles.
Several useful foundations exist, but the highest-risk authorization boundaries
are still open and the migration system is not operational because there are no
revision files.

The current state is:

```text
Layer 1: Functional regression suite passes
Layer 2: Functional regression suite passes
Layer 3: Core ownership and permission tests pass, but privilege escalation
         and legacy-route exposure remain
Layer 4: Foundations implemented; production completion not demonstrated
```

## Verification performed

- `python -m pytest -q`: **49 passed, 2 warnings**
- `python -m compileall -q app alembic`: passed
- Alembic configuration loads against PostgreSQL
- Docker Compose configuration parses successfully
- API route inventory inspected from the running FastAPI application
- Existing PostgreSQL schema inspected without dropping or recreating it
- No destructive database operation was run

The endpoint audit also performed read-only requests against legacy endpoints.
One registration probe used a disposable audit account to verify the role
escalation behavior; no existing rows were deleted or altered.

## Feature verification

### Centralized configuration — partially verified

Implemented in `app/config/settings.py`.

Verified:

- Environment-based database URL.
- Production minimum secret length.
- Configurable upload size, token expiry, issuer, audience, and schema creation.
- Development fallback generates a random in-process secret when absent.

Gaps:

- `load_dotenv(override=True)` allows a local `.env` file to overwrite
  externally supplied deployment variables. Production configuration should
  prefer the process environment and should not silently override it.
- Configuration values are parsed but not comprehensively range-validated.
- There is no secret-provider integration or key-version rotation mechanism.

### Access tokens — partially verified

Implemented in `app/auth.py`.

Verified:

- HMAC signature validation.
- `exp`, `iat`, `iss`, `aud`, and access-token type claims.
- Current user is loaded from the database rather than trusting token role data.

Gaps:

- Tokens are custom hand-rolled bearer tokens rather than a standard JWT
  library or another reviewed token implementation.
- Logout revokes the refresh session only; an already-issued access token
  remains usable until expiry.
- There is no access-token `jti` or server-side revocation strategy.
- Password policy and password-hash upgrade handling are absent.
- Corrupt stored password hashes can raise parsing errors rather than fail
  cleanly.

### Refresh sessions — implemented with a concurrency gap

Implemented in `app/auth.py` and `RefreshSession` in
`app/database/models.py`.

Verified:

- Only a SHA-256 verifier is stored.
- Refresh tokens are high-entropy random values.
- Rotation marks the old token revoked and links a replacement.
- Reuse of a revoked token revokes active sessions for that user.
- Logout marks a refresh session revoked.
- Tests cover rotation, reuse rejection, and logout.

Gaps:

- Rotation does not lock or atomically claim the database row. Two concurrent
  refresh requests can both read the token as active and both issue a
  replacement.
- There is no explicit token-family identifier; reuse handling revokes all
  active sessions for the user rather than the affected family.
- Refresh and logout events are not written to the audit log.
- Expired-session cleanup is not implemented.

### Authentication audit events — partial implementation

Implemented in `app/audit/service.py` and `AuditEvent` in
`app/database/models.py`.

Verified:

- Registration and successful/failed login events are recorded.
- Request IDs are attached to registration/login events.
- Passwords and tokens are not stored in event metadata.

Gaps:

- Logout, refresh, refresh reuse, permission denial, uploads, downloads,
  membership changes, role changes, project changes, and dataset reassignment
  are not recorded.
- There is no audit-log read API with restricted administrative access.
- There is no retention policy.
- Audit writes are not transactionally coupled to critical membership and
  dataset state changes.
- The model does not explicitly store workspace/project context.

### Request correlation and health checks — implemented but limited

Implemented in `app/main.py`.

Verified:

- Incoming `X-Request-ID` is preserved.
- A request ID is generated when absent.
- The ID is returned in the response.
- `/health/live` exists.
- `/health/ready` checks `SELECT 1`.

Gaps:

- Request IDs are not included in structured application logs.
- Request IDs are not consistently passed to all audit events.
- There are no latency, error-rate, database, or pipeline metrics.
- The readiness endpoint only checks PostgreSQL, not file storage or other
  required dependencies.

### Protected downloads and database health — partially verified

The download endpoint now requires authentication and checks dataset project
access before returning a file. Database health requires authentication and no
longer exposes the database name.

Gaps:

- Download authorization is verified through `DatasetVersion`; orphaned files
  without a matching version are denied, but file cleanup and storage
  integrity are not handled.
- There are no tests covering unauthorized download access.

### Final-owner protection — narrowly implemented

Implemented in `app/permissions/services.py` and
`app/permissions/routes.py`.

The protection applies to a project member with role `owner`.

Gaps:

- Workspace ownership remains represented separately by `Workspace.owner_id`.
- The project-owner/member-owner model is not formally unified.
- There are no tests for the final-owner demotion/removal path.
- An owner can still assign the `owner` member role without an explicit
  ownership-transfer workflow.

### Docker and Compose — development infrastructure only

Implemented in `Dockerfile`, `docker-compose.yml`, and `.dockerignore`.

Verified:

- The application image uses a non-root user.
- PostgreSQL has persistent storage and a health check.
- Compose configuration parses.

Gaps:

- Compose uses development credentials and `AUTO_CREATE_SCHEMA=true`.
- The API container has no container-level health check.
- Processed and quarantine files are not mounted to persistent storage.
- The image does not run migrations.
- There is no production compose/deployment profile.
- Dependency versions are ranges rather than a lock file or fully pinned
  reproducible set.

### GitHub Actions CI — partial

Implemented in `.github/workflows/ci.yml`.

Verified:

- PostgreSQL service is configured.
- Dependencies are installed.
- Python compilation, tests, and Docker build are requested.

Gaps:

- CI does not run Alembic migration validation.
- CI does not run formatting, linting, type checking, or dependency auditing.
- CI does not test a fresh database through migrations.
- There is no deployment workflow or approval strategy.

## Critical findings

### C1 — Public registration allows privileged roles (resolved)

`RegisterRequest.role` is accepted from the unauthenticated client and passed
to `register_user`. The registration service accepts `admin`, `analyst`,
`viewer`, and `uploader`.

Impact: any unauthenticated caller can create an administrator account and
access `/admin/users`.

Evidence: `app/main.py:166-171`, `app/auth.py` registration role validation,
and the existing tests that register an admin directly.

Resolution: public registration now always assigns `viewer`. An authenticated
administrator can explicitly assign a supported role through
`PATCH /admin/users/{user_id}/role`, which writes an audit event.

### C2 — Legacy pipeline history is publicly readable (resolved)

`GET /pipeline-runs` has no authentication dependency and returns pipeline
metadata for all users. A live request returned HTTP 200 without credentials.

Impact: cross-tenant metadata disclosure.

Resolution: the route requires authentication and returns only runs linked to
projects the caller can view.

### C3 — Legacy version and quality history routes are publicly readable (resolved)

`GET /dataset-versions/{filename}` and
`GET /quality-monitoring/{filename}` have no authentication or project access
dependency.

Impact: dataset filenames, version metadata, and quality history can be
enumerated across tenants.

Resolution: both routes require authentication, resolve project ownership or
membership, and return a resource-hiding 404 for inaccessible existing data.

### C4 — No migration revisions exist

Alembic is configured, but `alembic/versions` is missing and `alembic heads`
has no revision. The application still relies on import-time
`Base.metadata.create_all()` when schema auto-creation is enabled.

Impact: production schema changes are not controlled, a fresh production
database cannot be initialized through migrations, and the new
`refresh_sessions` and `audit_events` tables have no reviewed migration.

Evidence: `app/main.py:87`, `alembic/env.py`, and the empty/missing versions
directory.

## High-risk incomplete work

1. Upload processing writes files and dynamic tables before metadata
   transaction completion. Failures can leave orphaned files/tables.
2. Analytics failures are returned inside a successful upload response with
   `"status": "analysis_failed"` rather than surfacing a consistent failure
   state.
3. There is no idempotency key or duplicate-upload protection.
4. There is no rate limiting on login, registration, refresh, upload, or
   invitation operations.
5. There are no password-reset records or workflow.
6. Workspace memberships and invitations are absent.
7. Structured JSON logging, metrics, security headers, CORS policy, backups,
   restore verification, and RPO/RTO procedures are absent.
8. Critical permission and dataset operations do not write audit events.

## Layer 1, 2, and 3 regression assessment

### Layer 1

The 49-test suite passes, including dataset upload, validation, cleaning,
quarantine, ownership, and API behavior tests. This is functional regression
evidence only; failure cleanup and idempotency remain unverified.

### Layer 2

The 49-test suite passes analytics engine, KPI, trend, quality, insight,
recommendation, repository, and API tests. No production-load or failure
recovery test was found.

### Layer 3

Workspace, project, dataset, membership, and role tests pass. The public-admin registration issue and the three public legacy routes are
resolved. The suite now includes anonymous, authenticated-unrelated-user, and
explicit role-assignment coverage for these boundaries.

## Ranked remaining work

| Rank | Work | Risk | Dependency | Production impact |
|---|---|---|---|---|
| 1 | Create reviewed migration baseline and revisions | Critical | Live schema comparison | Enables safe deployment and preserves data |
| 2 | Make refresh rotation atomic and family-aware | High | Refresh model | Prevents concurrent replay and session over-revocation |
| 3 | Refactor upload transaction/storage lifecycle | High | Dataset service boundaries | Prevents orphaned data and inconsistent uploads |
| 4 | Add password reset and rate limits | High | Configuration/session model | Reduces account abuse risk |
| 5 | Expand transactional audit coverage | High | Route/service transaction design | Provides traceability and compliance evidence |
| 6 | Add workspace invitations/memberships | Medium | Authorization model | Enables controlled collaboration |
| 7 | Add metrics, structured logs, backups, and recovery tests | Medium | Deployment environment | Enables operations and incident response |
| 8 | Complete CI quality/security/deployment checks | Medium | Migration and tooling strategy | Prevents regressions before release |

## Exactly one recommended next phase

### Phase: Close critical authorization boundaries (completed)

Do this phase before migrations, invitations, or further operational features.
It has no schema dependency and directly addresses the highest-risk exposed
behavior.

Architecture:

1. Public registration always creates a least-privileged user.
2. Administrative role assignment becomes an authenticated, explicit operation.
3. Every legacy data route resolves the target dataset/project before returning
   any metadata.
4. Shared authorization helpers return resource-hiding `404` responses for
   inaccessible tenant resources.
5. Add route-level security tests that exercise anonymous, unrelated-user,
   viewer, editor, and owner cases.

Affected files:

- `app/main.py`
- `app/auth.py`
- `app/schemas.py`
- `app/datasets/services.py`
- `app/permissions/services.py`
- `tests/test_auth.py`
- `tests/test_datasets.py`
- `tests/test_api.py`

Risks:

- Existing tests currently rely on self-registering `admin` users and must be
  changed to use a controlled test bootstrap helper.
- Dashboard registration behavior may need a compatible response/message.
- Filename-based history routes need a safe project-resolution query without
  leaking whether another tenant owns the filename.

Acceptance tests:

1. Anonymous registration requesting `admin` receives a non-privileged role.
2. An existing administrator can perform an explicitly authorized role
   assignment or bootstrap operation.
3. Anonymous requests to `/pipeline-runs`,
   `/dataset-versions/{filename}`, and
   `/quality-monitoring/{filename}` receive 401.
4. An unrelated authenticated user receives 404 for another tenant's
   pipeline/version/quality data.
5. An authorized project viewer can read permitted history.
6. Existing Layer 1–3 tests continue to pass.
7. No response leaks another tenant's filename, dataset ID, project ID, or
   pipeline metadata.

Implementation status: completed after approval. Public registration is
least-privileged, administrative assignment is explicit and audited, the
legacy history routes enforce tenant authorization, and the full suite passes.
