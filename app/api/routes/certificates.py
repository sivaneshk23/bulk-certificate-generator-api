from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.certificate import Certificate, CertificateStatus
from app.db.session import get_db
from app.schemas.job import CertificateResult

router = APIRouter(prefix="/certificates", tags=["Certificates"])


def _to_result(cert: Certificate) -> CertificateResult:
    return CertificateResult(
        id=cert.id,
        recipient_name=cert.recipient_name,
        recipient_email=cert.recipient_email,
        status=cert.status,
        error_message=cert.error_message,
        download_url=(
            f"/api/v1/certificates/{cert.id}/download"
            if cert.status == CertificateStatus.COMPLETED
            else None
        ),
        created_at=cert.created_at,
        completed_at=cert.completed_at,
    )


@router.get("/{certificate_id}", response_model=CertificateResult)
def get_certificate(certificate_id: str, db: Session = Depends(get_db)):
    cert = db.scalar(select(Certificate).where(Certificate.id == certificate_id))
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    return _to_result(cert)


@router.get("/{certificate_id}/download", response_class=FileResponse, response_model=None)
def download_certificate(certificate_id: str, db: Session = Depends(get_db)):
    cert = db.scalar(select(Certificate).where(Certificate.id == certificate_id))
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found.")
    if cert.status != CertificateStatus.COMPLETED or not cert.file_path:
        raise HTTPException(
            status_code=409, detail="Certificate is not available for download yet."
        )

    storage_root = Path(settings.storage_dir).resolve()
    file_path = Path(cert.file_path).resolve()
    try:
        file_path.relative_to(storage_root)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Certificate storage path is invalid.") from exc

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Generated certificate file is missing.")
    return FileResponse(path=file_path, media_type="application/pdf", filename=file_path.name)
