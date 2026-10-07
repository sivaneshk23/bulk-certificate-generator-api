from tests.test_create_job import payload


def test_processing_certificate_is_recovered_after_worker_loss(client, db):
    from app.db.models.certificate import Certificate, CertificateStatus
    from app.db.models.generation_job import GenerationJob, JobStatus
    from app.services import job_service

    job = job_service.create_job(db, job_service.GenerationJobCreate.model_validate(payload()))
    certificate = db.query(Certificate).filter(Certificate.job_id == job.id).first()
    assert certificate is not None

    certificate.status = CertificateStatus.PROCESSING
    job.pending_count = 1
    job.processing_count = 1
    job.status = JobStatus.PROCESSING
    db.commit()

    job_service.process_job(job.id)

    db.expire_all()
    refreshed = db.get(GenerationJob, job.id)
    assert refreshed is not None
    assert refreshed.completed_count == 2
    assert refreshed.failed_count == 0
    assert refreshed.processing_count == 0
    assert refreshed.pending_count == 0
    assert refreshed.status == JobStatus.COMPLETED
