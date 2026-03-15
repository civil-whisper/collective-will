# Task: OpenTimestamps Cost + Ops Runbook

## Goal
Give operators a practical reference for when to use public calendars versus self-hosting and what trade-offs to expect.

## Default v0 choice
- Use public OpenTimestamps calendars.
- Configure `AUDIT_TIMESTAMP_PROVIDER=opentimestamps`.
- Leave `OPENTIMESTAMPS_BITCOIN_NODE_URL` unset unless you want local verification to produce `verified` instead of `stamped`.

## Cost model

### Public calendars
- Direct cost: effectively free for v0 usage.
- Operational cost: minimal.
- Best for:
  - MVP
  - low daily bundle volume
  - small team with no Bitcoin or calendar infrastructure

### Self-hosted calendar + Bitcoin node
- Direct cost: small VPS plus storage/bandwidth for the node and calendar.
- Operational cost: materially higher than public calendars.
- Best for:
  - policy requirement to avoid third-party calendars
  - higher assurance around availability/control
  - teams already running Bitcoin infrastructure

## Practical guidance
- For v0, public calendars are the correct default.
- Add a Bitcoin node only when you specifically need automated `verified` status in your own environment.
- Do not self-host just to optimize money at MVP scale; the operator burden dominates the infrastructure cost.

## Failure handling
- If OpenTimestamps stamping fails, local root computation and bundle generation must still succeed.
- Manifest/index should record `failed` timestamping status rather than hiding the day's public bundle.
- If a previous `.ots` file matches the current day root, reuse it instead of discarding proof history.
