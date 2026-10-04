# Services

## What goes here

- Business logic for one domain area
- Orchestration: call repositories (and later ports) in the right order
- Domain-oriented return values (dataclasses / plain data) for routers to map to HTTP

## What never goes here

- Raw SQL (that belongs in repositories)
- Opening admin/system sessions unless this path already required provisioning
- HTTP concerns: status codes, `HTTPException`, request/response models
- Reading `org_id` from a client-supplied body (use the authenticated principal)
