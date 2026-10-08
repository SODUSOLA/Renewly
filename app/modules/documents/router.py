"""HTTP endpoints for managing the current user's documents."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.common.enums import DocumentStatus, DocumentType
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.documents import service
from app.modules.documents.models import RenewalHistory
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentRead,
    DocumentUpdate,
    RenewalRead,
    RenewRequest,
)

# Every route here requires a logged-in user.
router = APIRouter(
    prefix="/documents", tags=["documents"], dependencies=[Depends(get_current_user)]
)

_NOT_FOUND = HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


# func to turn a DocumentInvalid error into a 422 response
def _invalid(error: service.DocumentInvalid) -> HTTPException:
    """Build the 422 response carrying the rule that was broken."""
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


# func to list documents
@router.get("", response_model=list[DocumentRead])
def list_documents(
    vehicle_id: uuid.UUID | None = None,
    type: DocumentType | None = None,
    status: DocumentStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DocumentRead]:
    """List the user's documents, soonest expiry first. Optional filters:
    vehicle_id, type and status (valid / expiring_soon / expired)."""
    return service.list_documents(
        db, user, vehicle_id=vehicle_id, doc_type=type, status=status
    )


# func to create a document
@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def create_document(
    body: DocumentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentRead:
    """Create a document. Returns 422 if a rule is broken (e.g. unknown vehicle)."""
    try:
        return service.create_document(db, user, body)
    except service.DocumentInvalid as error:
        raise _invalid(error)


# func to fetch one document
@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentRead:
    """Get one document. Returns 404 if missing, deleted, or someone else's."""
    try:
        return service.get_document(db, user, document_id)
    except service.DocumentNotFound:
        raise _NOT_FOUND


# func to partially update a document
@router.patch("/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentRead:
    """Update the fields sent. Returns 404 if not found, 422 on a broken rule."""
    try:
        return service.update_document(db, user, document_id, body)
    except service.DocumentNotFound:
        raise _NOT_FOUND
    except service.DocumentInvalid as error:
        raise _invalid(error)


# func to soft-delete a document
@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """Soft delete a document (it disappears from the API but the row is kept)."""
    try:
        service.delete_document(db, user, document_id)
    except service.DocumentNotFound:
        raise _NOT_FOUND
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# func to mark a document as renewed
@router.post("/{document_id}/renew", response_model=DocumentRead)
def renew_document(
    document_id: uuid.UUID,
    body: RenewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DocumentRead:
    """Renew: set a later expiry date and log it in the renewal history."""
    try:
        return service.renew_document(db, user, document_id, body)
    except service.DocumentNotFound:
        raise _NOT_FOUND
    except service.DocumentInvalid as error:
        raise _invalid(error)


# func to list a document's renewal history
@router.get("/{document_id}/renewals", response_model=list[RenewalRead])
def list_renewals(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RenewalHistory]:
    """Return the document's renewal history, newest first."""
    try:
        return service.list_renewals(db, user, document_id)
    except service.DocumentNotFound:
        raise _NOT_FOUND
