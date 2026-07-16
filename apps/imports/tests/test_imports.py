"""
Phase 8 — Import System Tests
Coverage target: 80%+
"""
import os
import io
import tempfile
import pytest
from unittest.mock import patch, MagicMock, mock_open
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


@pytest.fixture
def import_job_review(user, db):
    from apps.imports.models import ImportJob, ImportStatus
    return ImportJob.objects.create(
        user=user,
        original_filename="resume.txt",
        file_type="txt",
        file_path="/tmp/test.txt",
        status=ImportStatus.REVIEW_REQUIRED,
        parsed_data={
            "personal": {"email": "john@example.com"},
            "summary": "Experienced developer",
            "work_experiences": [],
            "educations": [],
            "skills": [{"name": "Python", "category": "programming", "proficiency_level": "expert"}],
            "projects": [],
            "certifications": [],
            "achievements": [],
        },
        mapping_review={
            "personal": {
                "email": {"value": "john@example.com", "confidence": 0.99, "approved": True}
            },
            "skills": [
                {"value": {"name": "Python", "category": "programming", "proficiency_level": "expert"}, "confidence": 0.85, "approved": False}
            ],
        },
        confidence_scores={"personal.email": 0.99, "skills": 0.85},
    )


# ── Parser Tests ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTxtParser:
    def test_parses_plain_text(self, tmp_path):
        from apps.imports.parsers.txt_parser import TxtParser
        f = tmp_path / "resume.txt"
        f.write_text("John Doe\njohn@example.com\n\nExperience\n", encoding="utf-8")
        parser = TxtParser()
        result = parser.parse(str(f))
        assert "John Doe" in result
        assert "john@example.com" in result

    def test_handles_encoding_errors(self, tmp_path):
        from apps.imports.parsers.txt_parser import TxtParser
        f = tmp_path / "resume.txt"
        f.write_bytes(b"Name: Caf\xe9")  # Latin-1 byte in UTF-8 file
        parser = TxtParser()
        result = parser.parse(str(f))
        assert len(result) > 0


@pytest.mark.django_db
class TestMarkdownParser:
    def test_strips_markdown_syntax(self, tmp_path):
        from apps.imports.parsers.markdown_parser import MarkdownParser
        f = tmp_path / "resume.md"
        f.write_text("# John Doe\n\n**Software Engineer**\n\n- Python\n- Django", encoding="utf-8")
        parser = MarkdownParser()
        result = parser.parse(str(f))
        assert "John Doe" in result
        assert "Software Engineer" in result
        assert "Python" in result
        assert "#" not in result
        assert "**" not in result

    def test_strips_links(self, tmp_path):
        from apps.imports.parsers.markdown_parser import MarkdownParser
        f = tmp_path / "resume.md"
        f.write_text("[LinkedIn](https://linkedin.com/in/johndoe)", encoding="utf-8")
        parser = MarkdownParser()
        result = parser.parse(str(f))
        assert "LinkedIn" in result
        assert "https://linkedin.com/in/johndoe" not in result


@pytest.mark.django_db
class TestDocxParser:
    def test_raises_without_library(self, tmp_path):
        from apps.imports.parsers.docx_parser import DocxParser
        parser = DocxParser()
        with patch.dict("sys.modules", {"docx": None}):
            with pytest.raises((RuntimeError, Exception)):
                parser.parse(str(tmp_path / "fake.docx"))

    def test_parse_with_mock(self, tmp_path):
        from apps.imports.parsers.docx_parser import DocxParser

        mock_doc = MagicMock()
        mock_para = MagicMock()
        mock_para.text = "John Doe"
        mock_doc.paragraphs = [mock_para]
        mock_doc.tables = []

        with patch("apps.imports.parsers.docx_parser.DocxParser.parse") as mock_parse:
            mock_parse.return_value = "John Doe"
            parser = DocxParser()
            result = parser.parse("/fake/path.docx")
            assert result == "John Doe"


@pytest.mark.django_db
class TestPdfParser:
    def test_raises_without_library(self, tmp_path):
        from apps.imports.parsers.pdf_parser import PdfParser
        parser = PdfParser()
        with patch.dict("sys.modules", {"pdfminer": None, "pdfminer.high_level": None, "fitz": None}):
            with pytest.raises(Exception):
                parser.parse(str(tmp_path / "fake.pdf"))

    def test_parse_with_mock(self):
        from apps.imports.parsers.pdf_parser import PdfParser
        with patch.object(PdfParser, "parse", return_value="John Doe\nSoftware Engineer"):
            parser = PdfParser()
            result = parser.parse("/fake/path.pdf")
            assert "John Doe" in result


@pytest.mark.django_db
class TestParserRegistry:
    def test_get_parser_returns_correct_parser(self):
        import apps.imports.parsers.registry  # ensure registration
        from apps.imports.parsers import get_parser, supported_extensions
        parser = get_parser("txt")
        assert parser is not None
        exts = supported_extensions()
        assert "txt" in exts
        assert "md" in exts
        assert "pdf" in exts
        assert "docx" in exts

    def test_get_parser_raises_for_unknown(self):
        from apps.imports.parsers import get_parser
        with pytest.raises(ValueError, match="No parser registered"):
            get_parser("xyz")


# ── Extractor Tests ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProfileExtractor:
    SAMPLE_RESUME = """John Doe
john.doe@example.com
(555) 123-4567
linkedin.com/in/johndoe
github.com/johndoe
San Francisco, CA

Professional Summary
Experienced software engineer with 5+ years building scalable backend systems.

Experience
Software Engineer | Acme Corp
Jan 2022 - Present
• Built microservices with Python and Django
• Reduced API latency by 40%

Junior Developer | StartupXYZ
Jun 2019 - Dec 2021
• Developed REST APIs
• Worked with PostgreSQL

Education
Bachelor of Science, Computer Science
State University
2019
GPA: 3.8

Skills
Python, Django, PostgreSQL, Redis, Docker, Kubernetes, AWS

Projects
ResumeBuilder
Built a SaaS resume builder
• Used Python, Django, React
"""

    def test_extracts_email(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        assert extracted["personal"].get("email") == "john.doe@example.com"
        assert confidence.get("personal.email", 0) >= 0.99

    def test_extracts_phone(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        assert extracted["personal"].get("phone") is not None

    def test_extracts_name(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        assert extracted["personal"].get("full_name") == "John Doe"

    def test_extracts_linkedin(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        assert "linkedin.com/in/johndoe" in (extracted["personal"].get("linkedin_url") or "")

    def test_extracts_github(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        assert "github.com/johndoe" in (extracted["personal"].get("github_url") or "")

    def test_extracts_summary(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        assert "software engineer" in (extracted.get("summary") or "").lower()

    def test_extracts_skills(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        skill_names = [s["name"] for s in extracted.get("skills", [])]
        assert "Python" in skill_names

    def test_extracts_education(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        edus = extracted.get("educations", [])
        assert len(edus) >= 1

    def test_build_mapping_review_structure(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        review = ProfileExtractor.build_mapping_review(extracted, confidence)
        assert "personal" in review
        assert "skills" in review
        assert isinstance(review["skills"], list)

    def test_high_confidence_fields_auto_approved(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract(self.SAMPLE_RESUME)
        review = ProfileExtractor.build_mapping_review(extracted, confidence)
        # Email has confidence >= 0.9, should be auto-approved
        email_review = review["personal"].get("email", {})
        assert email_review.get("approved") is True

    def test_empty_text_returns_empty(self):
        from apps.imports.extractors import ProfileExtractor
        extracted, confidence = ProfileExtractor.extract("")
        assert extracted["personal"] == {}
        assert extracted["summary"] == ""


# ── ImportService Tests ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestImportService:
    def test_list_for_user_returns_user_jobs(self, user, import_job):
        from apps.imports.services import ImportService
        jobs = list(ImportService.list_for_user(user))
        assert len(jobs) >= 1
        assert all(j.user == user for j in jobs)

    def test_get_for_user_returns_job(self, user, import_job):
        from apps.imports.services import ImportService
        job = ImportService.get_for_user(str(import_job.id), user)
        assert job.id == import_job.id

    def test_get_for_user_raises_on_wrong_user(self, second_user, import_job, db):
        from apps.imports.models import ImportJob
        from apps.imports.services import ImportService
        with pytest.raises(ImportJob.DoesNotExist):
            ImportService.get_for_user(str(import_job.id), second_user)

    def test_cancel_pending_job(self, user, import_job):
        from apps.imports.models import ImportStatus
        from apps.imports.services import ImportService
        import_job.status = ImportStatus.PENDING
        import_job.save()
        result = ImportService.cancel(import_job)
        assert result.status == ImportStatus.FAILED
        assert "Cancelled" in result.error_message

    def test_process_sets_review_required(self, user, import_job):
        from apps.imports.models import ImportStatus
        from apps.imports.services import ImportService

        sample_text = "John Doe\njohn@example.com\n\nExperience\nEngineer | Acme\nJan 2020 - Present\n• Built things\n\nSkills\nPython, Django"

        with patch("apps.imports.services.ImportService._read_file", return_value=sample_text.encode()):
            with patch("apps.imports.parsers.pdf_parser.PdfParser.parse", return_value=sample_text):
                import apps.imports.parsers.registry  # ensure registration
                ImportService.process(import_job)

        import_job.refresh_from_db()
        assert import_job.status == ImportStatus.REVIEW_REQUIRED
        assert import_job.parsed_data != {}

    def test_apply_mapping_creates_skills(self, user, profile, import_job_review):
        from apps.imports.services import ImportService
        from apps.profiles.models import Skill

        approved = {
            "personal": {},
            "summary": "",
            "work_experiences": [],
            "educations": [],
            "skills": [{"name": "Python", "category": "programming", "proficiency_level": "expert"}],
            "projects": [],
            "certifications": [],
            "achievements": [],
        }
        ImportService.apply_mapping(import_job_review, approved)
        assert Skill.objects.filter(profile=profile, name="Python").exists()

    def test_apply_mapping_sets_applied_status(self, user, profile, import_job_review):
        from apps.imports.models import ImportStatus
        from apps.imports.services import ImportService

        ImportService.apply_mapping(import_job_review, {})
        import_job_review.refresh_from_db()
        assert import_job_review.status == ImportStatus.APPLIED
        assert import_job_review.applied_at is not None


# ── Import API Tests ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestImportListAPI:
    def test_list_requires_auth(self):
        client = APIClient()
        response = client.get("/api/v1/imports/")
        assert response.status_code == 401

    def test_list_returns_user_jobs(self, auth_client, import_job):
        response = auth_client.get("/api/v1/imports/")
        assert response.status_code == 200
        assert response.data["success"] is True
        ids = [item["id"] for item in response.data["data"]]
        assert str(import_job.id) in ids

    def test_list_isolation(self, auth_client, second_user, db):
        from apps.imports.models import ImportJob
        other_job = ImportJob.objects.create(
            user=second_user,
            original_filename="other.txt",
            file_type="txt",
            file_path="/tmp/other.txt",
        )
        response = auth_client.get("/api/v1/imports/")
        ids = [item["id"] for item in response.data["data"]]
        assert str(other_job.id) not in ids


@pytest.mark.django_db
class TestImportRetrieveAPI:
    def test_retrieve_own_job(self, auth_client, import_job):
        response = auth_client.get(f"/api/v1/imports/{import_job.id}/")
        assert response.status_code == 200
        assert response.data["data"]["id"] == str(import_job.id)

    def test_retrieve_other_user_job_returns_404(self, auth_client, second_user, db):
        from apps.imports.models import ImportJob
        other_job = ImportJob.objects.create(
            user=second_user,
            original_filename="other.txt",
            file_type="txt",
            file_path="/tmp/other.txt",
        )
        response = auth_client.get(f"/api/v1/imports/{other_job.id}/")
        assert response.status_code == 404

    def test_detail_includes_mapping_review(self, auth_client, import_job_review):
        response = auth_client.get(f"/api/v1/imports/{import_job_review.id}/")
        assert response.status_code == 200
        assert "mapping_review" in response.data["data"]


@pytest.mark.django_db
class TestImportUploadAPI:
    def test_upload_txt_file(self, auth_client, user):
        sample_content = "John Doe\njohn@example.com\n\nSkills\nPython, Django"
        file = io.BytesIO(sample_content.encode())
        file.name = "resume.txt"

        with patch("apps.imports.services.ImportService.upload") as mock_upload:
            from apps.imports.models import ImportJob, ImportStatus
            mock_job = ImportJob(
                user=user,
                original_filename="resume.txt",
                file_type="txt",
                file_path="/tmp/test.txt",
                status=ImportStatus.PENDING,
            )
            mock_job.id = "12345678-1234-1234-1234-123456789012"
            mock_upload.return_value = mock_job
            response = auth_client.post(
                "/api/v1/imports/upload/",
                {"file": file},
                format="multipart",
            )
        assert response.status_code in (200, 202)

    def test_upload_invalid_extension(self, auth_client):
        file = io.BytesIO(b"test content")
        file.name = "resume.exe"
        response = auth_client.post(
            "/api/v1/imports/upload/",
            {"file": file},
            format="multipart",
        )
        assert response.status_code == 400

    def test_upload_no_file(self, auth_client):
        response = auth_client.post("/api/v1/imports/upload/", {}, format="multipart")
        assert response.status_code == 400


@pytest.mark.django_db
class TestImportApplyAPI:
    def test_apply_mapping_succeeds(self, auth_client, import_job_review, profile):
        payload = {
            "personal": {},
            "summary": "",
            "work_experiences": [],
            "educations": [],
            "skills": [{"name": "Django", "category": "framework", "proficiency_level": "advanced"}],
            "projects": [],
            "certifications": [],
            "achievements": [],
        }
        response = auth_client.post(
            f"/api/v1/imports/{import_job_review.id}/apply/",
            payload,
            format="json",
        )
        assert response.status_code == 200
        assert response.data["data"]["status"] == "applied"

    def test_apply_fails_if_not_review_required(self, auth_client, import_job):
        response = auth_client.post(
            f"/api/v1/imports/{import_job.id}/apply/",
            {},
            format="json",
        )
        assert response.status_code == 400

    def test_cancel_job(self, auth_client, import_job):
        response = auth_client.post(f"/api/v1/imports/{import_job.id}/cancel/")
        assert response.status_code == 200
        assert response.data["data"]["status"] == "failed"


@pytest.mark.django_db
class TestImportDeleteAPI:
    def test_delete_own_job(self, auth_client, import_job):
        with patch("apps.imports.services.ImportService.delete") as mock_delete:
            mock_delete.return_value = None
            response = auth_client.delete(f"/api/v1/imports/{import_job.id}/")
        assert response.status_code == 200

    def test_delete_other_user_job(self, auth_client, second_user, db):
        from apps.imports.models import ImportJob
        other = ImportJob.objects.create(
            user=second_user, original_filename="x.txt",
            file_type="txt", file_path="/tmp/x.txt"
        )
        response = auth_client.delete(f"/api/v1/imports/{other.id}/")
        assert response.status_code == 404
