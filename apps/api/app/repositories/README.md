# Repositories

## What goes here

- All SQL for one domain area (parameterised `text()` queries only)
- Functions that take an existing SQLAlchemy `Session` plus plain arguments
- Mapping rows to simple dicts / primitives for the service layer

## What never goes here

- Opening or committing database sessions (the router/service supplies the session)
- HTTP / FastAPI types (`Request`, `HTTPException`, response models)
- Business rules (code generation, auth checks, orchestration across tables beyond “persist this”)
- Calling LLMs or other external services
- Reading `org_id` from a request body (callers pass the scoped session already set)
