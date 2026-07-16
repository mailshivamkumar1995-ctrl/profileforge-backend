"""
Phase 8 — Export System Tests
Coverage target: 80%+
"""
import uuid
import pytest
import zipfile
from io import BytesIO
from unittest.mock import patch, MagicMock
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
def export_job_queued(user, resume, db):
    from apps.exports.models import ExportJob, ExportStatus, ExportResourceType, ExportFormat
    return ExportJob.objects.create(
        user=user,
        resource_type=ExportResourceType.RESUME,
        resource_id=resume.id,
        format=ExportFormat.PDF,
        status=ExportStatus.QUEUED,
    )


@pytest.fixture
def export_job_completed(user, resume, db):
    from apps.exports.models import ExportJob, ExportStatus, ExportResourceType, ExportFormat
    from django.utils import timezone
    from datetime import timedelta
    return ExportJob.objects.create(
        user=user,
        resource_type=ExportResourceType.RESUME,
        resource_id=resume.id,
        format=ExportFormat.PDF,
        status=ExportStatus.COMPLETED,
        file_path=f"exports/{user.id}/test.pdf",
        file_size=12345,
        download_url="https://storage.example.com/exports/test.pdf",
        url_expires_at=timezone.now() + timedelta(hours=1),
        completed_at=timezone.now(),
    )


# ── Generator Tests ───────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestGeneratorRegistry:
    def test_get_generator_pdf(self):
        import apps.exports.generators.registry  # ensure registration
        from apps.exports.generators import get_generator, supported_formats
        gen = get_generator("pdf")
        assert gen is not None
        fmts = supported_formats()
        assert "pdf" in fmts
        assert "docx" in fmts

    def test_get_generator_docx(self):
        import apps.exports.generators.registry
        from apps.exports.generators import get_generator
        gen = get_generator("docx")
        assert gen is not None

    def test_get_generator_raises_unknown(self):
        from apps.exports.generators import get_generator
        with pytest.raises(ValueError, match="No generator registered"):
            get_generator("xlsx")


@pytest.mark.django_db
class TestPdfGenerator:
    def test_raises_without_weasyprint(self):
        import apps.exports.generators.registry
        from apps.exports.generators import get_generator
        gen = get_generator("pdf")
        with patch.dict("sys.modules", {"weasyprint": None}):
            with pytest.raises(RuntimeError, match="WeasyPrint"):
                gen.generate("<html><body>Test</body></html>")

    def test_generates_pdf_bytes_with_mock(self):
        import apps.exports.generators.registry
        from apps.exports.generators import get_generator
        gen = get_generator("pdf")
        mock_pdf_bytes = b"%PDF-1.4 fake pdf content"

        mock_html_instance = MagicMock()
        mock_html_instance.write_pdf.return_value = mock_pdf_bytes

        mock_css_instance = MagicMock()

        with patch.dict("sys.modules", {
            "weasyprint": MagicMock(
                HTML=MagicMock(return_value=mock_html_instance),
                CSS=MagicMock(return_value=mock_css_instance),
            ),
            "weasyprint.text": MagicMock(),
            "weasyprint.text.fonts": MagicMock(FontConfiguration=MagicMock()),
        }):
            result = gen.generate("<html><body><h1>Resume</h1></body></html>")
        assert result == mock_pdf_bytes


@pytest.mark.django_db
class TestDocxGenerator:
    PROFILE_DATA = {
        "full_name": "John Doe",
        "headline": "Senior Software Engineer",
        "email": "john@example.com",
        "phone": "555-123-4567",
        "location": {"city": "San Francisco", "country": "CA"},
        "professional_summary": "Experienced engineer.",
        "work_experiences": [
            {
                "job_title": "Software Engineer",
                "company_name": "Acme",
                "is_current": True,
                "start_date": "2022-01-01",
                "end_date": "",
                "description": "Built things",
                "achievements": ["Reduced latency by 40%"],
            }
        ],
        "educations": [
            {
                "institution": "State University",
                "degree": "Bachelor of Science",
                "field_of_study": "Computer Science",
                "end_date": "2022-05-01",
                "gpa": 3.8,
            }
        ],
        "skills": [{"name": "Python", "category": "programming", "proficiency_level": "expert"}],
        "projects": [],
        "certifications": [],
        "achievements": [],
        "publications": [],
    }

    def test_raises_without_python_docx(self):
        import apps.exports.generators.registry
        from apps.exports.generators import get_generator
        gen = get_generator("docx")
        with patch.dict("sys.modules", {"docx": None}):
            with pytest.raises(RuntimeError, match="python-docx"):
                gen.generate("", profile_data=self.PROFILE_DATA)

    def test_raises_without_profile_data(self):
        import apps.exports.generators.registry
        from apps.exports.generators import get_generator
        gen = get_generator("docx")
        with pytest.raises(ValueError, match="profile_data"):
            gen.generate("<html></html>", profile_data=None)

    def test_generates_docx_bytes_with_mock(self):
        import apps.exports.generators.registry
        from apps.exports.generators import get_generator
        gen = get_generator("docx")

        fake_bytes = b"PK\x03\x04"  # Minimal DOCX magic bytes

        with patch.object(gen, "generate", return_value=fake_bytes):
            result = gen.generate("<html></html>", profile_data=self.PROFILE_DATA)

        assert result == fake_bytes


# ── ExportService Tests ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestExportService:
    def test_list_for_user_returns_user_jobs(self, user, export_job_queued):
        from apps.exports.services import ExportService
        jobs = list(ExportService.list_for_user(user))
        assert len(jobs) >= 1
        assert all(j.user == user for j in jobs)

    def test_list_filters_by_resource_type(self, user, export_job_queued):
        from apps.exports.services import ExportService
        from apps.exports.models import ExportResourceType
        jobs = list(ExportService.list_for_user(user, resource_type=ExportResourceType.RESUME))
        assert len(jobs) >= 1
        jobs_cl = list(ExportService.list_for_user(user, resource_type=ExportResourceType.COVER_LETTER))
        assert all(j.resource_type == ExportResourceType.COVER_LETTER for j in jobs_cl)

    def test_get_for_user_returns_job(self, user, export_job_queued):
        from apps.exports.services import ExportService
        job = ExportService.get_for_user(str(export_job_queued.id), user)
        assert job.id == export_job_queued.id

    def test_get_for_user_raises_on_wrong_user(self, second_user, export_job_queued, db):
        from apps.exports.models import ExportJob
        from apps.exports.services import ExportService
        with pytest.raises(ExportJob.DoesNotExist):
            ExportService.get_for_user(str(export_job_queued.id), second_user)

    def test_get_download_url_for_completed_job(self, user, export_job_completed):
        from apps.exports.services import ExportService
        url = ExportService.get_download_url(export_job_completed)
        assert url == export_job_completed.download_url

    def test_get_download_url_raises_for_non_completed(self, user, export_job_queued):
        from apps.exports.services import ExportService
        with pytest.raises(ValueError, match="not ready"):
            ExportService.get_download_url(export_job_queued)

    def test_request_creates_job_and_enqueues(self, user, resume):
        from apps.exports.services import ExportService
        from apps.exports.models import ExportJob, ExportStatus, ExportFormat, ExportResourceType

        with patch("celery_app.tasks.export_tasks.generate_export.delay") as mock_delay:
            job = ExportService.request(
                user=user,
                resource_type=ExportResourceType.RESUME,
                resource_id=str(resume.id),
                fmt=ExportFormat.PDF,
            )
        assert isinstance(job, ExportJob)
        assert job.status == ExportStatus.QUEUED
        mock_delay.assert_called_once_with(str(job.id))

    def test_cover_letter_render_matches_preview_data_shape(self, user, cover_letter):
        from apps.exports.models import ExportJob, ExportResourceType, ExportFormat
        from apps.exports.services import ExportService
        from apps.profiles.profile_utils import ProfileSerializer

        cover_letter.hiring_manager_name = "David Jacob"
        cover_letter.hiring_manager_title = "Operations Manager"
        cover_letter.body_content = "I am excited to apply.\n\nMy experience aligns closely."
        cover_letter.save()

        job = ExportJob.objects.create(
            user=user,
            resource_type=ExportResourceType.COVER_LETTER,
            resource_id=cover_letter.id,
            format=ExportFormat.PDF,
        )
        html = ExportService._render_cover_letter(job, ProfileSerializer.to_dict(user.profile))

        assert "David Jacob" in html
        assert "Operations Manager" in html
        assert "Dear David Jacob" in html
        assert "I am excited to apply" in html

    def test_cover_letter_docx_uses_letter_content_not_resume_layout(self, user, cover_letter):
        from apps.exports.models import ExportJob, ExportResourceType, ExportFormat
        from apps.exports.services import ExportService
        from apps.profiles.profile_utils import ProfileSerializer

        cover_letter.title = "Program 2 Cover Letter Validation - Local DB"
        cover_letter.company_name = "ProfileForge Validation Labs"
        cover_letter.job_title = "DevOps Engineer"
        cover_letter.hiring_manager_name = "David Jacob"
        cover_letter.hiring_manager_title = "Operations Manager"
        cover_letter.body_content = (
            "I am excited to apply for the DevOps Engineer role at ProfileForge Validation Labs.\n\n"
            "My experience across Kubernetes, Docker, CI/CD, monitoring, and cloud infrastructure aligns closely."
        )
        cover_letter.save()

        job = ExportJob.objects.create(
            user=user,
            resource_type=ExportResourceType.COVER_LETTER,
            resource_id=cover_letter.id,
            format=ExportFormat.DOCX,
        )
        file_bytes = ExportService._generate_cover_letter_docx(
            job, ProfileSerializer.to_dict(user.profile)
        )

        with zipfile.ZipFile(BytesIO(file_bytes)) as docx:
            document_xml = docx.read("word/document.xml").decode("utf-8")

        assert "David Jacob" in document_xml
        assert "ProfileForge Validation Labs" in document_xml
        assert "I am excited to apply" in document_xml
        assert "PROFESSIONAL SUMMARY" not in document_xml

    def test_cover_letter_download_filename_uses_letter_title(self, user, cover_letter):
        from apps.exports.models import ExportJob, ExportResourceType, ExportFormat
        from apps.exports.services import ExportService

        cover_letter.title = "Program 2 Cover Letter Validation - Local DB"
        cover_letter.save()
        job = ExportJob.objects.create(
            user=user,
            resource_type=ExportResourceType.COVER_LETTER,
            resource_id=cover_letter.id,
            format=ExportFormat.PDF,
        )

        assert ExportService.get_download_filename(job) == (
            "Program 2 Cover Letter Validation - Local DB.pdf"
        )


# ── Export API Tests ──────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestExportListAPI:
    def test_list_requires_auth(self):
        client = APIClient()
        response = client.get("/api/v1/exports/")
        assert response.status_code == 401

    def test_list_returns_user_jobs(self, auth_client, export_job_queued):
        response = auth_client.get("/api/v1/exports/")
        assert response.status_code == 200
        assert response.data["success"] is True
        ids = [item["id"] for item in response.data["data"]]
        assert str(export_job_queued.id) in ids

    def test_list_isolation(self, auth_client, second_user, resume, db):
        from apps.exports.models import ExportJob, ExportResourceType, ExportFormat
        from apps.profiles.models import UserProfile
        from apps.portfolios.models import Portfolio
        other_job = ExportJob.objects.create(
            user=second_user,
            resource_type=ExportResourceType.RESUME,
            resource_id=resume.id,
            format=ExportFormat.PDF,
        )
        response = auth_client.get("/api/v1/exports/")
        ids = [item["id"] for item in response.data["data"]]
        assert str(other_job.id) not in ids

    def test_list_filter_by_resource_type(self, auth_client, export_job_queued):
        response = auth_client.get("/api/v1/exports/?resource_type=resume")
        assert response.status_code == 200
        for item in response.data["data"]:
            assert item["resource_type"] == "resume"


@pytest.mark.django_db
class TestExportRetrieveAPI:
    def test_retrieve_own_job(self, auth_client, export_job_queued):
        response = auth_client.get(f"/api/v1/exports/{export_job_queued.id}/")
        assert response.status_code == 200
        assert response.data["data"]["id"] == str(export_job_queued.id)

    def test_retrieve_other_user_job_returns_404(self, auth_client, second_user, resume, db):
        from apps.exports.models import ExportJob, ExportResourceType, ExportFormat
        other_job = ExportJob.objects.create(
            user=second_user,
            resource_type=ExportResourceType.RESUME,
            resource_id=resume.id,
            format=ExportFormat.PDF,
        )
        response = auth_client.get(f"/api/v1/exports/{other_job.id}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestExportRequestAPI:
    def test_request_export_pdf(self, auth_client, resume):
        with patch("apps.exports.services.ExportService.request") as mock_req:
            from apps.exports.models import ExportJob, ExportStatus, ExportResourceType, ExportFormat
            mock_job = MagicMock(spec=ExportJob)
            mock_job.id = uuid.uuid4()
            mock_job.resource_type = ExportResourceType.RESUME
            mock_job.resource_id = resume.id
            mock_job.format = ExportFormat.PDF
            mock_job.status = ExportStatus.QUEUED
            mock_job.file_size = None
            mock_job.template = None
            mock_job.created_at = None
            mock_job.completed_at = None
            mock_job.file_path = None
            mock_job.download_url = ""
            mock_job.url_expires_at = None
            mock_job.error_message = ""
            mock_req.return_value = mock_job

            response = auth_client.post(
                "/api/v1/exports/request/",
                {
                    "resource_type": "resume",
                    "resource_id": str(resume.id),
                    "format": "pdf",
                },
                format="json",
            )
        assert response.status_code in (200, 202)

    def test_request_export_invalid_format(self, auth_client, resume):
        response = auth_client.post(
            "/api/v1/exports/request/",
            {
                "resource_type": "resume",
                "resource_id": str(resume.id),
                "format": "xlsx",
            },
            format="json",
        )
        assert response.status_code == 400

    def test_request_export_invalid_resource_type(self, auth_client, resume):
        response = auth_client.post(
            "/api/v1/exports/request/",
            {
                "resource_type": "blog_post",
                "resource_id": str(resume.id),
                "format": "pdf",
            },
            format="json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestExportDownloadAPI:
    def test_download_completed_job(self, auth_client, export_job_completed):
        response = auth_client.get(f"/api/v1/exports/{export_job_completed.id}/download/")
        assert response.status_code == 200
        assert "download_url" in response.data["data"]
        assert response.data["data"]["filename"] == "Test Resume.pdf"

    def test_download_not_completed_job(self, auth_client, export_job_queued):
        response = auth_client.get(f"/api/v1/exports/{export_job_queued.id}/download/")
        assert response.status_code == 400


@pytest.mark.django_db
class TestExportRegenerateAPI:
    def test_regenerate_creates_new_job(self, auth_client, export_job_completed, resume):
        with patch("apps.exports.services.ExportService.request") as mock_req:
            from apps.exports.models import ExportJob, ExportStatus, ExportResourceType, ExportFormat
            new_job = MagicMock(spec=ExportJob)
            new_job.id = uuid.uuid4()
            new_job.resource_type = ExportResourceType.RESUME
            new_job.resource_id = resume.id
            new_job.format = ExportFormat.PDF
            new_job.status = ExportStatus.QUEUED
            new_job.file_size = None
            new_job.template = None
            new_job.created_at = None
            new_job.completed_at = None
            new_job.file_path = None
            new_job.download_url = ""
            new_job.url_expires_at = None
            new_job.error_message = ""
            mock_req.return_value = new_job

            response = auth_client.post(f"/api/v1/exports/{export_job_completed.id}/regenerate/")
        assert response.status_code in (200, 202)


@pytest.mark.django_db
class TestExportDeleteAPI:
    def test_delete_own_job(self, auth_client, export_job_queued):
        with patch("apps.exports.services.ExportService.delete") as mock_delete:
            mock_delete.return_value = None
            response = auth_client.delete(f"/api/v1/exports/{export_job_queued.id}/")
        assert response.status_code == 200

    def test_delete_other_user_job(self, auth_client, second_user, resume, db):
        from apps.exports.models import ExportJob, ExportResourceType, ExportFormat
        other_job = ExportJob.objects.create(
            user=second_user,
            resource_type=ExportResourceType.RESUME,
            resource_id=resume.id,
            format=ExportFormat.PDF,
        )
        response = auth_client.delete(f"/api/v1/exports/{other_job.id}/")
        assert response.status_code == 404


# ── Export URL Expiry Tests ────────────────────────────────────────────────────

@pytest.mark.django_db
class TestExportUrlExpiry:
    def test_get_download_url_regenerates_on_expiry(self, user, export_job_completed):
        from apps.exports.services import ExportService
        from django.utils import timezone
        from datetime import timedelta

        # Set URL to expired
        export_job_completed.url_expires_at = timezone.now() - timedelta(hours=1)
        export_job_completed.save()

        new_url = "https://storage.example.com/exports/refreshed.pdf"
        with patch("storage.storage") as mock_storage:
            mock_store = MagicMock()
            mock_store.get_signed_url.return_value = new_url
            mock_storage.return_value = mock_store

            url = ExportService.get_download_url(export_job_completed)

        assert url == new_url
        export_job_completed.refresh_from_db()
        assert export_job_completed.download_url == new_url
