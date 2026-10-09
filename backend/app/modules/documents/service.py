"""Business logic for documents. Every query is scoped to the owning user.

A document that belongs to someone else, or was soft-deleted, is reported as
"not found". Dates are compared against "today" in the user's own timezone.
"""
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.dates import today_for
from app.common.enums import DocumentStatus, DocumentType
from app.modules.auth.models import User
from app.modules.documents.models import Document, RenewalHistory
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
    RenewRequest,
)
from app.modules.vehicles.models import Vehicle

# A document counts as "expiring soon" when this many days (or fewer) remain.
EXPIRING_SOON_DAYS = 30


# class for "no such document for this user"
class DocumentNotFound(Exception):
    """Raised when the document is missing, deleted, or belongs to another user."""


# class for data that breaks a business rule
class DocumentInvalid(Exception):
    """Raised when the data breaks a rule; the message is shown to the client."""


# func to turn days left into a status
def compute_status(days_left: int) -> DocumentStatus:
    """Map days until expiry to a status (0 days = expires today = expiring soon)."""
    if days_left < 0:
        return DocumentStatus.EXPIRED
    if days_left <= EXPIRING_SOON_DAYS:
        return DocumentStatus.EXPIRING_SOON
    return DocumentStatus.VALID


# func to build the API view of a document with its derived fields
def to_read(document: Document, today: date) -> DocumentRead:
    """Return the document as a DocumentRead with `days_left` and `status` filled in."""
    read = DocumentRead.model_validate(document)
    read.days_left = document.days_until_expiry(today)
    read.status = compute_status(read.days_left)
    return read


# func to check a vehicle id belongs to the user
def _check_vehicle(db: Session, user: User, vehicle_id: uuid.UUID | None) -> None:
    """Raise DocumentInvalid unless `vehicle_id` is None or one of the user's vehicles."""
    if vehicle_id is None:
        return
    owned = db.scalar(
        select(Vehicle.id).where(Vehicle.id == vehicle_id, Vehicle.user_id == user.id)
    )
    if owned is None:
        raise DocumentInvalid("Vehicle not found")


# func to enforce the rules that span several fields
def _check_rules(document: Document) -> None:
    """Validate cross-field rules; mirrors the database CHECK constraints.

    Also clears a stale custom label when the type is not 'custom'.
    """
    if document.type != DocumentType.CUSTOM:
        document.custom_type_label = None
    elif not document.custom_type_label:
        raise DocumentInvalid("custom_type_label is required when type is 'custom'")
    if document.issue_date and document.expiry_date < document.issue_date:
        raise DocumentInvalid("expiry_date cannot be before issue_date")


# func to list the user's documents with optional filters
def list_documents(
    db: Session,
    user: User,
    *,
    vehicle_id: uuid.UUID | None = None,
    doc_type: DocumentType | None = None,
    status: DocumentStatus | None = None,
) -> list[DocumentRead]:
    """Return the user's live documents, soonest expiry first.

    `status` is filtered in SQL against the user's "today" so it always agrees
    with the status shown on each document.
    """
    today = today_for(user)
    query = select(Document).where(
        Document.user_id == user.id, Document.deleted_at.is_(None)
    )
    if vehicle_id:
        query = query.where(Document.vehicle_id == vehicle_id)
    if doc_type:
        query = query.where(Document.type == doc_type)
    soon_limit = today + timedelta(days=EXPIRING_SOON_DAYS)
    if status == DocumentStatus.EXPIRED:
        query = query.where(Document.expiry_date < today)
    elif status == DocumentStatus.EXPIRING_SOON:
        query = query.where(Document.expiry_date.between(today, soon_limit))
    elif status == DocumentStatus.VALID:
        query = query.where(Document.expiry_date > soon_limit)
    documents = db.scalars(query.order_by(Document.expiry_date, Document.id))
    return [to_read(doc, today) for doc in documents]


# func to fetch one live document owned by the user
def _get_document(
    db: Session, user: User, document_id: uuid.UUID, *, lock: bool = False
) -> Document:
    """Return the ORM document or raise DocumentNotFound. `lock` takes a row lock."""
    query = select(Document).where(
        Document.id == document_id,
        Document.user_id == user.id,
        Document.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    document = db.scalar(query)
    if document is None:
        raise DocumentNotFound
    return document


# func to fetch one document for the API
def get_document(db: Session, user: User, document_id: uuid.UUID) -> DocumentRead:
    """Return one document with its derived status."""
    return to_read(_get_document(db, user, document_id), today_for(user))


# func to create a document
def create_document(db: Session, user: User, data: DocumentCreate) -> DocumentRead:
    """Create a document for the user. Raises DocumentInvalid on a rule violation."""
    _check_vehicle(db, user, data.vehicle_id)
    # exclude_none lets the model's default offsets apply when none were sent.
    document = Document(user_id=user.id, **data.model_dump(exclude_none=True))
    _check_rules(document)
    db.add(document)
    db.commit()
    return to_read(document, today_for(user))


# func to apply a partial update to a document
def update_document(
    db: Session, user: User, document_id: uuid.UUID, data: DocumentUpdate
) -> DocumentRead:
    """Change only the fields the client sent, then re-check the rules.

    Raises DocumentNotFound or DocumentInvalid.
    """
    document = _get_document(db, user, document_id)
    changes = data.model_dump(exclude_unset=True)
    if "vehicle_id" in changes:
        _check_vehicle(db, user, changes["vehicle_id"])
    for field, value in changes.items():
        setattr(document, field, value)
    try:
        _check_rules(document)
    except DocumentInvalid:
        db.rollback()
        raise
    db.commit()
    return to_read(document, today_for(user))


# func to soft-delete a document
def delete_document(db: Session, user: User, document_id: uuid.UUID) -> None:
    """Soft delete: stamp `deleted_at` so the row is kept but hidden everywhere."""
    document = _get_document(db, user, document_id)
    document.deleted_at = datetime.now(UTC)
    db.commit()


# func to mark a document as renewed
def renew_document(
    db: Session, user: User, document_id: uuid.UUID, data: RenewRequest
) -> DocumentRead:
    """Move the expiry date forward and record the renewal in the history.

    The row is locked so two simultaneous renewals cannot both start from the
    same previous expiry. Raises DocumentNotFound, or DocumentInvalid if the
    new expiry is not later than the current one.
    """
    document = _get_document(db, user, document_id, lock=True)
    if data.new_expiry <= document.expiry_date:
        db.rollback()
        raise DocumentInvalid("new_expiry must be later than the current expiry date")
    today = today_for(user)
    db.add(
        RenewalHistory(
            document_id=document.id,
            previous_expiry=document.expiry_date,
            new_expiry=data.new_expiry,
            renewed_on=today,
            cost=data.cost,
            notes=data.notes,
        )
    )
    document.expiry_date = data.new_expiry
    db.commit()
    return to_read(document, today)


# func to list a document's renewal history
def list_renewals(
    db: Session, user: User, document_id: uuid.UUID
) -> list[RenewalHistory]:
    """Return the renewal history, newest first. Raises DocumentNotFound."""
    document = _get_document(db, user, document_id)
    return list(
        db.scalars(
            select(RenewalHistory)
            .where(RenewalHistory.document_id == document.id)
            .order_by(RenewalHistory.new_expiry.desc())
        )
    )
