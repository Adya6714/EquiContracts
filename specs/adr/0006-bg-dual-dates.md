# ADR 0006 — Separate BG expiry clocks

- **Status:** Accepted
- **Decision:** D-006

Store guarantee expiry and claim expiry independently. The database rejects a claim expiry
earlier than guarantee expiry; alerting must eventually run a separate countdown for each.
