# Layer 4 Operations

## Local container stack

The development stack contains:

- PostgreSQL 16
- FastAPI served by Uvicorn
- A persistent Docker volume for PostgreSQL data
- Container health checks

Start it with:

```powershell
docker compose up --build
```

The compose file intentionally uses `AUTO_CREATE_SCHEMA=true` for local
development. Production deployments must use a reviewed Alembic migration
workflow and a secret supplied outside the image.

## CI

`.github/workflows/ci.yml` runs:

- Dependency installation
- Python compilation
- The automated test suite
- Docker image build validation

The workflow uses a disposable PostgreSQL service and does not depend on a
developer's local database.

## Production migration rule

Do not run schema creation in every API replica. Run the reviewed migration
step once during deployment, then start the application with:

```env
APP_ENV=production
AUTO_CREATE_SCHEMA=false
```

The initial baseline migration is still required before this production rule
can be enabled for a fresh database.
