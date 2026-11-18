# Layer 4 Security Audit

## Baseline

The existing test suite passes with 45 tests. This is a functional baseline,
not a production security certification.

## Findings

### High

1. `app/auth.py` uses a development fallback signing secret when
   `APP_SECRET_KEY` is absent. Production configuration must fail closed instead
   of accepting a known default.
2. Access tokens are signed and checked for expiry, but there is no refresh
   token lifecycle, revocation store, token-family reuse detection, or logout
   session invalidation.
3. `app/main.py` still contains legacy dataset, pipeline, preview, and profile
   routes that need endpoint-by-endpoint tenant authorization verification.
4. `Base.metadata.create_all()` executes during application import, which is an
   unsafe production deployment pattern and prevents reviewed migration
   controls.

### Medium

1. Password hashing uses PBKDF2-SHA256 with a hard-coded work factor rather than
   a centrally configured policy and does not provide hash-upgrade handling.
2. There is no password-reset workflow with hashed, expiring, single-use
   tokens.
3. There is no persistent audit trail for authentication, membership, role, or
   dataset operations.
4. The database connection module prints the database target during import.
   Even without credentials, connection details should go through controlled
   logging and must never include secrets.
5. Sensitive endpoints have no configurable rate-limiting layer.
6. Request IDs, security response headers, and structured security events are
   not yet standardized.

### Low

1. CORS and environment-specific security configuration are not centralized.
2. There is no documented key rotation procedure.
3. Backup, restore, and recovery verification are not implemented as
   operational procedures.

## Security invariants for Layer 4

- Never trust client-supplied tenant or role identifiers without a server-side
  authorization check.
- Return resource-hiding `404` responses where the project convention requires
  them, rather than leaking cross-tenant existence.
- Do not log passwords, access tokens, refresh tokens, reset tokens, or database
  credentials.
- Keep critical business changes and their audit records transactionally
  consistent.
- Preserve existing data and API behavior while migrating.

## Verification plan

Layer 4 security verification must include:

- Expired, malformed, wrongly signed, and revoked token tests.
- Refresh rotation and reuse detection tests.
- Password-reset expiration and single-use tests.
- Cross-workspace and cross-project access tests for every critical route.
- Permission-denied audit-event tests.
- Rate-limit response tests.
- Migration upgrade/downgrade and existing-data preservation tests.
