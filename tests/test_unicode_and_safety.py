from datetime import date

from app.certificates.generator import generate_certificate_pdf


def test_certificate_generation_supports_tamil_chinese_and_literal_markup(tmp_path):
    for name, course in [
        ("சிவனேஷ் குமார்", "Python நிரலாக்கம்"),
        ("张伟", "人工智能与数据科学"),
        ("Sivanesh 张伟 சிவனேஷ்", "Maths <b>Advanced & Safe"),
    ]:
        output = tmp_path / f"{abs(hash(name))}.pdf"
        generate_certificate_pdf(
            output_path=output,
            certificate_id="CERT-UNICODE",
            recipient_name=name,
            title="Certificate of Completion",
            course_name=course,
            completion_date=date(2026, 10, 7),
            issuer_name="Example Institute",
            issuer_designation="Director",
        )
        assert output.read_bytes().startswith(b"%PDF")
        assert output.stat().st_size > 1000
