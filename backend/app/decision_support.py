from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai import AIProvider
from app.experience_services import find_experience_match
from app.schemas import (
    DRAFT_TEXT_FIELDS,
    DecisionConsideration,
    DecisionConsiderationDraft,
    DecisionSupportAIResult,
    DecisionSupportResponse,
    ExperienceCandidate,
    ExperienceSearchMatch,
)


DEFAULT_DECISION_QUESTION = "你的现场与这条经验有哪些不同？"


def _candidate(match: ExperienceSearchMatch) -> ExperienceCandidate:
    experience = match.experience
    return ExperienceCandidate(
        id=experience.id,
        activity_name=experience.activity_name,
        **{field: getattr(experience, field) for field in DRAFT_TEXT_FIELDS},
    )


def _validate_sources(
    result: DecisionSupportAIResult,
    experience: ExperienceCandidate,
) -> DecisionSupportAIResult:
    validated = DecisionSupportAIResult.model_validate(result)
    for consideration in validated.considerations:
        for field in consideration.basis_fields:
            value = getattr(experience, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("decision support referenced an empty experience field")
    return validated


def build_deterministic_fallback(
    concern: str,
    experience: ExperienceCandidate,
) -> DecisionSupportAIResult:
    direction = experience.action_and_reason or experience.things_to_note
    direction_field = (
        "action_and_reason"
        if experience.action_and_reason
        else "things_to_note"
        if experience.things_to_note
        else None
    )
    tradeoff = experience.shortcomings or experience.observed_result
    tradeoff_field = (
        "shortcomings"
        if experience.shortcomings
        else "observed_result"
        if experience.observed_result
        else None
    )
    considerations: list[DecisionConsiderationDraft] = []
    if direction is not None and direction_field is not None:
        basis_fields = [direction_field]
        if tradeoff_field is not None:
            basis_fields.append(tradeoff_field)
        considerations.append(
            DecisionConsiderationDraft(
                direction=direction,
                tradeoff=tradeoff,
                basis_fields=basis_fields,
            )
        )
    return DecisionSupportAIResult(
        understanding=concern,
        considerations=considerations,
        question_to_consider=experience.open_question or DEFAULT_DECISION_QUESTION,
    )


def _public_response(
    *,
    activity_name: str,
    concern: str,
    match: ExperienceSearchMatch | None,
    result: DecisionSupportAIResult,
) -> DecisionSupportResponse:
    basis_id = match.experience.id if match is not None else None
    return DecisionSupportResponse(
        activity_name=activity_name,
        concern_transcript=concern,
        understanding=result.understanding,
        match=match,
        considerations=[
            DecisionConsideration(
                direction=item.direction,
                tradeoff=item.tradeoff,
                basis_experience_id=basis_id,
            )
            for item in result.considerations
        ],
        question_to_consider=result.question_to_consider,
    )


def create_decision_support(
    db: Session,
    provider: AIProvider,
    *,
    organization_context: str,
    activity_name: str,
    concern: str,
) -> DecisionSupportResponse:
    clean_activity_name = activity_name.strip()
    clean_concern = concern.strip()
    match = find_experience_match(
        db,
        provider,
        activity_name=clean_activity_name,
        concern=clean_concern,
    )
    if match is None:
        return _public_response(
            activity_name=clean_activity_name,
            concern=clean_concern,
            match=None,
            result=DecisionSupportAIResult(
                understanding=clean_concern,
                considerations=[],
                question_to_consider=None,
            ),
        )

    candidate = _candidate(match)
    try:
        result = provider.support_decision(
            organization_context,
            clean_concern,
            candidate,
        )
        result = _validate_sources(result, candidate)
    except Exception:
        result = build_deterministic_fallback(clean_concern, candidate)
    return _public_response(
        activity_name=clean_activity_name,
        concern=clean_concern,
        match=match,
        result=result,
    )
