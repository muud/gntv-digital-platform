# GNTV DIGITAL Roadmap

## Released — v0.4.0

- Platform foundation and PostgreSQL migration framework
- Authentication, sessions, RBAC, and audit trails
- CMS Module 1 Content Core
- CMS Module 2 Media Library and storage abstraction
- CMS Module 3 Premium Streaming Catalog Engine

## Released — v0.5.0

- CMS Module 4 Editorial Workflow & Publishing backend
- Ten-state workflow, assignments, collaboration, revision history, scheduling, publication lifecycle, notifications, dashboards, audit events, and optimistic locking
- Archived-workflow restore and PostgreSQL-safe Editorial audit/activity serialization
- Validated Editorial OpenAPI contracts and Module 4 release-blocker regression coverage

## Ready next — Module 5

### Distribution and geo-fencing

CMS Module 4 approval clears the project to begin Module 5 as a separate scoped effort. No Module 5 implementation is included in v0.5.0.

- Distribution targets and delivery policy
- Playback restrictions and regional availability rules
- Geo-fencing rule management and enforcement contracts
- Distribution auditability, observability, and failure handling

## Future candidate — separate approval required

### Media processing and streaming delivery

- FFmpeg worker orchestration
- Metadata probing and technical validation
- Adaptive bitrate ladders
- HLS/DASH packaging
- Poster, thumbnail, and preview extraction
- Subtitle/audio track packaging
- Processing retries, observability, and failure recovery
- OSS output publishing and CDN integration

This work is not started and remains a separately governed roadmap candidate.

## Later candidates

- Editorial scheduling and advanced broadcast automation
- Search indexing and semantic discovery
- Recommendation model evolution and experimentation
- Subscription, entitlement, and premium access services
- Analytics, QoE telemetry, and audience insights
- Multi-region production hardening, disaster recovery, and compliance automation

Roadmap items are directional and require architecture review, acceptance criteria, and explicit authorization before implementation.
