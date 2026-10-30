from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api import DB, Limit, Offset, P
from app.models import Incident, IncidentNote, identifier
from app.schemas import Input
from app.services import audit, emit, scoped

router = APIRouter(prefix="/api/v1/vader")


class NoteInput(Input):
    body: Annotated[str, Field(min_length=1, max_length=4000)]
    reference: Annotated[str | None, Field(min_length=1, max_length=200)] = None


class NoteOutput(BaseModel):
    model_config = {"from_attributes": True}
    id: str
    incident_id: str
    author_id: str
    body: str
    reference: str | None
    created_at: datetime


@router.post("/incidents/{incident_id}/notes", response_model=NoteOutput, status_code=201)
def note_create(incident_id: UUID, data: NoteInput, db: DB, p: P):
    p.require("security.read")
    incident = scoped(db, Incident, p, str(incident_id))
    record = IncidentNote(
        id=identifier(),
        organization_id=p.organization_id,
        incident_id=incident.id,
        author_id=p.user_id,
        **data.model_dump(),
    )
    db.add(record)
    emit(db, p, "security.incident.note_added", incident.id)
    return record


@router.get("/incidents/{incident_id}/notes", response_model=list[NoteOutput])
def notes(incident_id: UUID, db: DB, p: P, limit: Limit = 50, offset: Offset = 0):
    p.require("security.read")
    incident = scoped(db, Incident, p, str(incident_id))
    audit(db, p, "security.incident.notes_read", incident.id)
    return db.scalars(
        select(IncidentNote)
        .where(
            IncidentNote.organization_id == p.organization_id,
            IncidentNote.incident_id == incident.id,
        )
        .order_by(IncidentNote.created_at, IncidentNote.id)
        .limit(limit)
        .offset(offset)
    ).all()
