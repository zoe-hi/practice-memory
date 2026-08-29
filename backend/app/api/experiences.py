from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.experience_services import (
    get_experience_detail,
    get_experience_list,
    search_experiences,
)
from app.schemas import (
    ExperienceResponse,
    ExperienceSearchRequest,
    ExperienceSearchResponse,
)
from app.services import delete_experience


router = APIRouter(prefix="/experiences", tags=["experiences"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[ExperienceResponse])
def list_experiences_endpoint(
    db: DbSession,
    activity_name: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ExperienceResponse]:
    return get_experience_list(db, activity_name=activity_name, limit=limit)


@router.post("/search", response_model=ExperienceSearchResponse)
def search_experiences_endpoint(
    body: ExperienceSearchRequest,
    request: Request,
    db: DbSession,
) -> ExperienceSearchResponse:
    return search_experiences(db, request.app.state.ai_provider, body)


@router.get("/{experience_id}", response_model=ExperienceResponse)
def get_experience_endpoint(
    experience_id: str, db: DbSession
) -> ExperienceResponse:
    return get_experience_detail(db, experience_id)


@router.delete("/{experience_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experience_endpoint(
    experience_id: str, request: Request, db: DbSession
) -> Response:
    delete_experience(db, request.app.state.audio_storage, experience_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
