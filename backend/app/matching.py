from __future__ import annotations

import re
import unicodedata

from app.schemas import DRAFT_TEXT_FIELDS, ExperienceCandidate, ExperienceMatch


HAN_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
WORD = re.compile(r"[a-z0-9]+")


def normalize_search_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def matching_tokens(value: str) -> list[str]:
    normalized = normalize_search_text(value)
    tokens: list[str] = []
    tokens.extend(word for word in WORD.findall(normalized) if len(word) >= 2)
    for run in HAN_RUN.findall(normalized):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return list(dict.fromkeys(tokens))


def _candidate_text(candidate: ExperienceCandidate) -> str:
    return " ".join(
        value
        for field in DRAFT_TEXT_FIELDS
        if isinstance((value := getattr(candidate, field)), str) and value.strip()
    )


def rank_experiences_locally(
    concern: str, candidates: list[ExperienceCandidate]
) -> ExperienceMatch | None:
    concern_tokens = matching_tokens(concern)
    if not concern_tokens:
        return None

    best_candidate: ExperienceCandidate | None = None
    best_overlap: list[str] = []
    for candidate in candidates:
        candidate_tokens = set(matching_tokens(_candidate_text(candidate)))
        overlap = [token for token in concern_tokens if token in candidate_tokens]
        if len(overlap) > len(best_overlap):
            best_candidate = candidate
            best_overlap = overlap

    if best_candidate is None or not best_overlap:
        return None
    displayed = "、".join(f"“{token}”" for token in best_overlap[:3])
    return ExperienceMatch(
        experience_id=best_candidate.id,
        why_similar=f"困扰和这条个人经验都提到了{displayed}等现场要素。",
    )
