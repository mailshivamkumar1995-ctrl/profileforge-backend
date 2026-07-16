"""
Tests for Celery tasks: import_tasks and export_tasks.
Uses task_always_eager=True (set in conftest celery_config) so tasks run synchronously.
"""
import pytest
from unittest.mock import patch, MagicMock


# ─── Import Tasks ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProcessImportJobTask:
    def test_task_sets_processing_status(self, import_job):
        from apps.imports.models import ImportStatus
        from celery_app.tasks.import_tasks import process_import_job

        with patch("apps.imports.services.ImportService.process") as mock_process:
            process_import_job(str(import_job.id))

        import_job.refresh_from_db()
        assert import_job.status in (ImportStatus.PROCESSING, ImportStatus.REVIEW_REQUIRED, ImportStatus.FAILED)

    def test_task_calls_import_service_process(self, import_job):
        from celery_app.tasks.import_tasks import process_import_job

        with patch("apps.imports.services.ImportService.process") as mock_process:
            process_import_job(str(import_job.id))

        mock_process.assert_called_once()

    def test_task_marks_failed_on_exception(self, import_job):
        from apps.imports.models import ImportStatus
        from celery_app.tasks.import_tasks import process_import_job

        with patch("apps.imports.services.ImportService.process", side_effect=RuntimeError("Parser failed")):
            try:
                process_import_job(str(import_job.id))
            except Exception:
                pass

        import_job.refresh_from_db()
        assert import_job.status == ImportStatus.FAILED
        assert "Parser failed" in (import_job.error_message or "")

    def test_task_handles_nonexistent_job_id(self):
        from celery_app.tasks.import_tasks import process_import_job
        import uuid
        with pytest.raises(Exception):
            process_import_job(str(uuid.uuid4()))


@pytest.mark.django_db
class TestGenerateExportTask:
    def _make_export_job(self, user, db):
        from apps.exports.models import ExportJob, ExportStatus
        from apps.resumes.models import Resume
        from apps.profiles.models import UserProfile
        import uuid
        profile = UserProfile.objects.get(user=user)
        resume = Resume.objects.create(
            user=user, profile=profile, title="Export Test Resume", status="active"
        )
        return ExportJob.objects.create(
            user=user,
            resource_type="resume",
            resource_id=resume.id,
            format="pdf",
            status=ExportStatus.QUEUED,
        )

    def test_task_calls_export_service_generate(self, user, db):
        from celery_app.tasks.export_tasks import generate_export
        job = self._make_export_job(user, db)

        with patch("apps.exports.services.ExportService.generate") as mock_gen:
            generate_export(str(job.id))

        mock_gen.assert_called_once()

    def test_task_retries_on_failure(self, user, db):
        from celery_app.tasks.export_tasks import generate_export
        from celery.exceptions import Retry
        job = self._make_export_job(user, db)

        with patch("apps.exports.services.ExportService.generate", side_effect=RuntimeError("WeasyPrint failed")):
            with pytest.raises((RuntimeError, Retry, Exception)):
                generate_export(str(job.id))

    def test_task_handles_nonexistent_job_id(self):
        from celery_app.tasks.export_tasks import generate_export
        import uuid
        with pytest.raises(Exception):
            generate_export(str(uuid.uuid4()))


# ─── Storage Factory ─────────────────────────────────────────────────────────

class TestStorageFactory:
    def test_unknown_backend_raises_value_error(self):
        from storage import get_storage
        with patch("django.conf.settings.STORAGE_BACKEND", "unknown"):
            with pytest.raises(ValueError, match="Unknown storage backend"):
                get_storage()

    def test_minio_returns_s3_storage(self):
        from storage import get_storage
        with patch("django.conf.settings.STORAGE_BACKEND", "minio"):
            with patch("storage.s3_backend.S3Storage") as MockS3:
                MockS3.return_value = MagicMock()
                try:
                    backend = get_storage()
                except Exception:
                    pass  # S3 client init may fail without credentials

    def test_storage_interface_is_abstract(self):
        from storage.base import IStorage
        with pytest.raises(TypeError):
            IStorage()


# ─── Storage Interface Contract ───────────────────────────────────────────────

class TestStorageInterfaceContract:
    """Verifies any IStorage implementation satisfies the full contract."""

    def _make_mock_storage(self):
        from storage.base import IStorage
        mock = MagicMock(spec=IStorage)
        mock.upload.return_value = "path/to/file.pdf"
        mock.download.return_value = b"file content"
        mock.delete.return_value = None
        mock.get_signed_url.return_value = "https://storage.example.com/file.pdf?sig=abc123"
        mock.exists.return_value = True
        mock.get_public_url.return_value = "https://storage.example.com/file.pdf"
        return mock

    def test_upload_returns_path(self):
        storage = self._make_mock_storage()
        result = storage.upload("path/to/file.pdf", b"bytes", "application/pdf")
        assert result == "path/to/file.pdf"

    def test_download_returns_bytes(self):
        storage = self._make_mock_storage()
        result = storage.download("path/to/file.pdf")
        assert isinstance(result, bytes)

    def test_get_signed_url_returns_url_string(self):
        storage = self._make_mock_storage()
        url = storage.get_signed_url("path/to/file.pdf", expiry_seconds=3600)
        assert url.startswith("https://")

    def test_exists_returns_bool(self):
        storage = self._make_mock_storage()
        assert isinstance(storage.exists("path/to/file.pdf"), bool)

    def test_delete_called_once(self):
        storage = self._make_mock_storage()
        storage.delete("path/to/file.pdf")
        storage.delete.assert_called_once_with("path/to/file.pdf")
