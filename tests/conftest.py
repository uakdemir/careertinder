from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobhunter.db.models import Base


@pytest.fixture
def db_session():
    """In-memory SQLite database with all tables created.
    Fresh for each test (no state leakage between tests).
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sample_config_dict():
    """Valid config dict with all fields populated."""
    return {
        "scraping": {
            "remote_io": {
                "enabled": True, "base_url": "https://remote.io/remote-jobs",
                "max_pages": 5, "delay_seconds": 1,
            },
            "remote_rocketship": {"enabled": False},
            "wellfound": {"enabled": True},
            "linkedin": {"enabled": True},
        },
        "filtering": {
            "salary_min_usd": 90000,
            "location_keywords": {
                "include": ["remote"],
                "exclude": ["us only"],
            },
            "title_whitelist": ["architect"],
            "title_blacklist": ["intern"],
            "company_blacklist": [],
        },
        "ai_models": {
            "tier2": {
                "provider": "anthropic", "model": "claude-3-5-haiku-latest",
                "max_tokens": 300, "temperature": 0.1,
            },
            "tier3": {
                "provider": "anthropic", "model": "claude-sonnet-4-20250514",
                "max_tokens": 2000, "temperature": 0.3,
            },
            "content_gen": {"provider": "openai", "model": "gpt-4o", "max_tokens": 2000, "temperature": 0.5},
        },
        "database": {"path": "data/test.db", "echo_sql": False},
        "dashboard": {"port": 8501, "page_size": 25},
        "scheduling": {"run_interval_hours": 12, "retry_failed_scrapers": True, "max_retries": 2},
        "notifications": {"enabled": False, "method": "email", "min_score_to_notify": 80},
    }


@pytest.fixture
def sample_config_yaml(tmp_path, sample_config_dict):
    """Write a valid config.yaml to a temp directory and return its path."""
    import yaml

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(sample_config_dict), encoding="utf-8")
    return config_path


@pytest.fixture
def sample_resume_pdf(tmp_path):
    """Create a minimal PDF with extractable text for testing.
    Uses pdfplumber-compatible format via a simple PDF structure.
    """
    try:
        from pdfplumber.utils.pdfinternals import resolve_and_decode  # noqa: F401
    except ImportError:
        pass

    # Create a minimal valid PDF with text
    # Using fpdf2 if available, otherwise create a minimal raw PDF
    pdf_path = tmp_path / "resume_test.pdf"
    _create_minimal_pdf(pdf_path, "John Doe\nSoftware Architect\nPython, AWS, Kubernetes\n10 years experience")
    return pdf_path


def _create_minimal_pdf(path: Path, text: str) -> None:
    """Create a minimal PDF file with the given text content."""
    # Build a minimal valid PDF manually
    lines = text.split("\n")
    stream_content = ""
    y = 750
    for line in lines:
        # Escape special PDF characters
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_content += f"BT /F1 12 Tf {72} {y} Td ({escaped}) Tj ET\n"
        y -= 20

    stream_bytes = stream_content.encode("latin-1")
    stream_length = len(stream_bytes)

    pdf_bytes = b"%PDF-1.4\n"

    # Object 1: Catalog
    obj1_offset = len(pdf_bytes)
    pdf_bytes += b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"

    # Object 2: Pages
    obj2_offset = len(pdf_bytes)
    pdf_bytes += b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"

    # Object 3: Page
    obj3_offset = len(pdf_bytes)
    pdf_bytes += (
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )

    # Object 4: Content stream
    obj4_offset = len(pdf_bytes)
    pdf_bytes += f"4 0 obj\n<< /Length {stream_length} >>\nstream\n".encode("latin-1")
    pdf_bytes += stream_bytes
    pdf_bytes += b"\nendstream\nendobj\n"

    # Object 5: Font
    obj5_offset = len(pdf_bytes)
    pdf_bytes += b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"

    # Cross-reference table
    xref_offset = len(pdf_bytes)
    pdf_bytes += b"xref\n0 6\n"
    pdf_bytes += b"0000000000 65535 f \n"
    pdf_bytes += f"{obj1_offset:010d} 00000 n \n".encode()
    pdf_bytes += f"{obj2_offset:010d} 00000 n \n".encode()
    pdf_bytes += f"{obj3_offset:010d} 00000 n \n".encode()
    pdf_bytes += f"{obj4_offset:010d} 00000 n \n".encode()
    pdf_bytes += f"{obj5_offset:010d} 00000 n \n".encode()

    # Trailer
    pdf_bytes += b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
    pdf_bytes += f"startxref\n{xref_offset}\n%%EOF\n".encode()

    path.write_bytes(pdf_bytes)
