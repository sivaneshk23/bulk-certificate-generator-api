from datetime import date, datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, TypeAdapter, field_validator

from app.db.models.certificate import CertificateStatus
from app.db.models.generation_job import JobStatus


class CertificateInfo(BaseModel):
    title: Annotated[str, Field(min_length=2, max_length=200)]
    course_name: Annotated[str, Field(min_length=2, max_length=200)]
    completion_date: date
    issuer_name: Annotated[str, Field(min_length=2, max_length=200)]
    issuer_designation: Annotated[str | None, Field(default=None, max_length=200)]

    @field_validator("title", "course_name", "issuer_name", "issuer_designation", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        cleaned = " ".join(value.split())
        return cleaned or None


class RecipientInput(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=200)]
    email: EmailStr | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        cleaned = " ".join(value.split())
        return cleaned or None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        return cleaned or None


RECIPIENT_ADAPTER = TypeAdapter(RecipientInput)


class GenerationJobCreate(BaseModel):
    certificate: CertificateInfo
    # Per-recipient validation is deliberate: one malformed recipient must not destroy
    # all valid recipients in the same bulk request.
    recipients: Annotated[list[Any], Field(min_length=1, max_length=50000)]
    idempotency_key: Annotated[str | None, Field(default=None, min_length=8, max_length=128)] = None

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def normalize_idempotency_key(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        return cleaned or None


class CertificateResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recipient_name: str
    recipient_email: str | None
    status: CertificateStatus
    error_message: str | None
    download_url: str | None = None
    created_at: datetime
    completed_at: datetime | None


class GenerationJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    total: int
    completed: int
    failed: int
    processing: int
    pending: int
    progress_percent: float
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_summary: str | None


class CertificateListResponse(BaseModel):
    job_id: str
    items: list[CertificateResult]
    total: int
    page: int
    page_size: int
