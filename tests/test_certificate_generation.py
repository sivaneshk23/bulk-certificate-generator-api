from datetime import date

from app.certificates.generator import generate_certificate_pdf


def test_certificate_generation(tmp_path):
    output = tmp_path / "certificate.pdf"
    generate_certificate_pdf(
        output_path=output,
        certificate_id="CERT-123",
        recipient_name="Ada Lovelace",
        title="Certificate of Completion",
        course_name="Advanced Backend Engineering",
        completion_date=date(2026, 10, 7),
        issuer_name="Example Institute",
        issuer_designation="Director",
    )
    assert output.exists()
    assert output.read_bytes().startswith(b"%PDF")
    assert output.stat().st_size > 1000
