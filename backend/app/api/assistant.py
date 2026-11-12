"""Assistant du dossier (F-E4) : questions sur le patient ouvert, réponses lues dans les données validées et citées.
Aucun texte généré par un LLM (T36). Chaque question et sa réponse sont conservées (conversation) et auditées."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_patient_for_doctor, require_doctor
from app.core.config import get_settings
from app.db.models import Conversation, Patient, User, utcnow
from app.db.session import get_db
from app.services import search as search_service
from app.services.assistant import answer, load_patient_data
from app.services.audit import audit
from app.services.referential import get_referential

router = APIRouter(tags=["assistant"])


class QuestionIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def _conversation(db: Session, user: User, patient: Patient) -> Conversation:
    c = db.scalar(select(Conversation).where(Conversation.user_id == user.id, Conversation.patient_id == patient.id))
    if c is None:
        c = Conversation(user_id=user.id, patient_id=patient.id, messages=[], cited_sources=[])
        db.add(c)
    return c


@router.get("/patients/{patient_id}/assistant")
def history(patient: Patient = Depends(get_patient_for_doctor), user: User = Depends(require_doctor),
            db: Session = Depends(get_db)) -> list[dict]:
    c = db.scalar(select(Conversation).where(Conversation.user_id == user.id, Conversation.patient_id == patient.id))
    return (c.messages if c else [])[-30:]


@router.post("/patients/{patient_id}/assistant")
def ask(body: QuestionIn, patient: Patient = Depends(get_patient_for_doctor), user: User = Depends(require_doctor),
        db: Session = Depends(get_db)) -> dict:
    data = load_patient_data(db, patient.id)
    if get_settings().assistant_search and search_service.available():
        data.search = lambda q: search_service.search(db, patient.id, q)
    a = answer(get_referential(), data, body.question)
    cited = [{"document_id": d, **{k: data.docs[d][k] for k in ("type", "date", "name")}} for d in a.citations
             if d in data.docs]
    message = jsonable_encoder({"at": utcnow(), "question": body.question, "kind": a.kind, "text": a.text,
                                "citations": cited, "passages": a.passages})
    c = _conversation(db, user, patient)
    c.messages = [*c.messages, message]
    c.cited_sources = sorted({*c.cited_sources, *a.citations})
    db.commit()
    audit(db, user.id, "assistant_question", "patient", patient.id, {"kind": a.kind})
    return message
