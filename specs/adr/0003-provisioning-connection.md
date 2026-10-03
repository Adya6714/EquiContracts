# ADR 0003 — Separate provisioning connection

- **Status:** Accepted
- **Decision:** D-003

Pre-tenant organisation creation uses a separate admin credential. Application routers
must not import the provisioning session, and the app role never receives `BYPASSRLS`.
