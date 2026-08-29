# Repository instructions

## Project

This is a greenfield hackathon MVP for capturing short frontline memory markers during an activity, guiding the contributor through a post-activity reflection, and turning only their confirmed personal experience into a searchable record.

Preserve these product principles:

- A quick voice note is a memory marker, not a finished experience and not a `context` field by itself.
- Build an experience from the complete reflection conversation.
- AI may transcribe, clarify, structure, and retrieve. It must not invent missing facts, replace the contributor's judgment, or turn one person's experience into an organizational rule.
- Only an experience explicitly confirmed by the contributor enters the experience library.

## Source of truth

- Before backend work, read `docs/backend-development-spec.md` in full.
- That specification owns the backend architecture, data model, API contract, AI contract, state machine, test cases, implementation order, and acceptance criteria.
- If code, tests, and the specification disagree, do not silently choose one. Report the conflict and preserve the documented product semantics unless the task explicitly changes them.
- When a task deliberately changes a contract or product decision, update the specification and affected tests in the same change.
- Keep this file concise. Put detailed architecture and API decisions in `docs/backend-development-spec.md`, not here.

## Repository layout

- `backend/`: FastAPI application, database code, AI providers, and backend tests.
- `docs/backend-development-spec.md`: complete backend implementation specification.
- `frontend/`: React/TypeScript/Vite client when frontend development begins.
- `README.md`: setup, environment variables, run commands, and Demo instructions.

Do not place generated databases, uploaded audio, virtual environments, secrets, or build artifacts in version control.

## Technical defaults

- Backend: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.x, and SQLite.
- Testing: `pytest` with FastAPI `TestClient`; use a temporary SQLite database and temporary audio directory.
- AI integration: keep provider-specific code behind the provider interface. Implement and test the deterministic `FakeAIProvider` before depending on a real provider.
- Runtime: keep the MVP deployable as one FastAPI process with persistent SQLite storage.
- Do not add a parallel framework, database, migration system, queue, or production dependency unless the task requires it and the specification is updated.

## Product invariants

- Store capture/reflection data in `capture_sessions` and confirmed personal experience in `experiences`.
- One capture session contains the initial marker plus all later questions and answers in `conversation_json`.
- A session may generate at most one confirmed experience; confirmation must be idempotent.
- Do not add `capture_session_id` to `experiences`.
- Derive `context`, `action_and_reason`, and `observed_result` from the whole conversation, not from one recording.
- Preserve the reflection fields `went_well`, `shortcomings`, `things_to_note`, and optional `open_question`.
- Target at most two AI follow-up questions and enforce the specification's hard upper limit of three.
- Leave unsupported or unknown fields as `null`; never fabricate content to complete a schema.
- Never expose server audio paths, API keys, or provider secrets to the frontend.

## Working method

1. Inspect the repository and relevant specification sections before editing.
2. For multi-step or contract-changing work, state a short plan before implementation.
3. Implement the smallest complete vertical slice that advances the documented Golden Path.
4. Add or update tests with behavior changes. Prefer deterministic, offline tests using `FakeAIProvider`.
5. Run relevant checks and review the resulting diff. Do not claim a command passed unless it was actually run.
6. Preserve unrelated user changes and avoid broad refactors that are not needed for the task.

## Commands

From the repository root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

After backend changes:

```bash
cd backend
pytest -q
```

If the project later adopts `pyproject.toml`, a different package manager, linting, formatting, or type checking, update these commands to match the actual repository before treating the new commands as required.

## Security and data handling

- Never commit `.env`, API keys, SQLite data files, uploaded audio, or logs containing full transcripts or model responses.
- Keep `.env.example` free of real credentials.
- Validate upload size and type; generate server-side filenames and never trust client paths.
- Tests must not call real AI services or require network access by default.
- If real AI credentials are unavailable, keep the Golden Path runnable through `FakeAIProvider` and text fallback.

## Code review rules

Flag changes that:

- bypass or break the capture-session state machine;
- allow duplicate experiences from repeated confirmation;
- treat a single recording as the completed factual account;
- let AI fill facts unsupported by the contributor's conversation;
- expose secrets, internal file paths, or unconfirmed memory markers;
- change an API or stored field without updating the specification and tests.

## Definition of done

A task is complete only when:

- the requested behavior is implemented and consistent with the specification;
- relevant tests pass, or any unrun/failed checks are reported with the reason;
- the application remains runnable through the documented commands;
- no secret or runtime data is added to version control; and
- the final report lists changed files, verification commands and results, AI provider status, and remaining limitations.
