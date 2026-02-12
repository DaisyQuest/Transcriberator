# Dashboard_API_Spec.md

## Scope
Node-based API for authentication, project management, upload orchestration, job lifecycle operations, revision operations, and artifact download links.

## Responsibilities
- Expose REST endpoints defined in FS-031.
- Mediate access control and signed URL generation.
- Persist/read project and job state.
- Provide observable logs/metrics/traces for all requests.

## Key Interfaces
- `/projects`
- `/projects/:id/uploads`
- `/projects/:id/jobs`
- `/jobs/:id`
- `/jobs/:id/retry`
- `/projects/:id/revisions`
- `/artifacts/:id/download`

## Quality Gates
- API contract tests required.
- Error responses must be typed and actionable.
- Trace IDs included in request logs.
