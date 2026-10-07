from datetime import date


def test_missing_tamil_font_does_not_crash_basic_pdf_generation(tmp_path, monkeypatch):
    from app.certificates import generator

    monkeypatch.setattr(generator.settings, "font_regular_path", None)
    monkeypatch.setattr(generator.settings, "font_bold_path", None)
    monkeypatch.setattr(generator.settings, "font_tamil_path", str(tmp_path / "missing.ttf"))
    monkeypatch.setattr(generator, "_discover_font", lambda filename: None)
    monkeypatch.setattr(generator, "_FONTS", None)

    output = tmp_path / "fallback.pdf"
    generator.generate_certificate_pdf(
        output_path=output,
        certificate_id="CERT-FALLBACK",
        recipient_name="சிவனேஷ் குமார்",
        title="Certificate of Completion",
        course_name="Font Fallback Verification",
        completion_date=date(2026, 10, 7),
        issuer_name="Example Institute",
        issuer_designation="Director",
    )
    assert output.read_bytes().startswith(b"%PDF")

    monkeypatch.setattr(generator, "_FONTS", None)
