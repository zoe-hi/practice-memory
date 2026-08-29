from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai import AIProvider
from app.core.errors import AppError
from app.matching import rank_experiences_locally
from app.models import Experience
from app.repositories import (
    find_experience_candidates,
    get_experience,
    list_experiences,
)
from app.schemas import (
    DRAFT_TEXT_FIELDS,
    ExperienceCandidate,
    ExperienceMatch,
    ExperienceResponse,
    ExperienceSearchMatch,
    ExperienceSearchRequest,
    ExperienceSearchResponse,
)
from app.services import experience_to_response


def _candidate(experience: Experience) -> ExperienceCandidate:
    return ExperienceCandidate(
        id=experience.id,
        activity_name=experience.activity_name,
        **{field: getattr(experience, field) for field in DRAFT_TEXT_FIELDS},
    )


def get_experience_list(
    db: Session, *, activity_name: str | None, limit: int
) -> list[ExperienceResponse]:
    clean_activity = activity_name.strip() if activity_name is not None else None
    experiences = list_experiences(
        db, activity_name=clean_activity or None, limit=limit
    )
    return [experience_to_response(experience) for experience in experiences]


def get_experience_detail(db: Session, experience_id: str) -> ExperienceResponse:
    experience = get_experience(db, experience_id)
    if experience is None:
        raise AppError(404, "EXPERIENCE_NOT_FOUND", "经验不存在。")
    return experience_to_response(experience)


def search_experiences(
    db: Session,
    provider: AIProvider,
    request: ExperienceSearchRequest,
) -> ExperienceSearchResponse:
    stored_candidates = find_experience_candidates(
        db, activity_name=request.activity_name, limit=20
    )
    candidates = [_candidate(experience) for experience in stored_candidates]
    if not candidates:
        return ExperienceSearchResponse(match=None)

    try:
        provider_match = provider.rank_experiences(request.concern, candidates)
        match = (
            ExperienceMatch.model_validate(provider_match)
            if provider_match is not None
            else None
        )
        if match is not None and match.experience_id not in {
            candidate.id for candidate in candidates
        }:
            raise ValueError("provider selected an experience outside candidates")
    except Exception:
        match = rank_experiences_locally(request.concern, candidates)

    if match is None:
        return ExperienceSearchResponse(match=None)
    experience_by_id = {
        experience.id: experience for experience in stored_candidates
    }
    selected = experience_by_id.get(match.experience_id)
    if selected is None:
        fallback = rank_experiences_locally(request.concern, candidates)
        if fallback is None:
            return ExperienceSearchResponse(match=None)
        match = fallback
        selected = experience_by_id[match.experience_id]
    return ExperienceSearchResponse(
        match=ExperienceSearchMatch(
            experience=experience_to_response(selected),
            why_similar=match.why_similar,
        )
    )
