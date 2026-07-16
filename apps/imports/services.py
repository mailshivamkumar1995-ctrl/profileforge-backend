import logging
import os
import uuid
from django.db import transaction
from django.utils import timezone
from apps.imports.models import ImportJob, ImportStatus, ImportFileType
from apps.imports.parsers import get_parser
from apps.imports.extractors import ProfileExtractor

logger = logging.getLogger(__name__)

# Maximum allowed upload size: 10 MB
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

ALLOWED_CONTENT_TYPES = {
    "txt": "text/plain",
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
}


class ImportService:

    # ── Upload ────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def upload(user, uploaded_file) -> ImportJob:
        """Save uploaded file to storage, create ImportJob, enqueue processing task."""
        # Validate file type
        original_name: str = uploaded_file.name
        ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""

        if ext not in {e.value for e in ImportFileType}:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({
                "file": f"Unsupported file type '.{ext}'. Allowed: txt, md, docx, pdf."
            })

        file_content: bytes = uploaded_file.read()
        if len(file_content) > MAX_FILE_SIZE_BYTES:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({
                "file": f"File too large. Maximum size is {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB."
            })

        # FINDING-002: validate file magic bytes (not just extension)
        from apps.imports.file_validator import validate_file_signature
        is_valid_signature, sig_error = validate_file_signature(file_content, ext)
        if not is_valid_signature:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"file": sig_error})

        # Upload to object storage
        storage_path = f"uploads/{user.id}/imports/{uuid.uuid4()}.{ext}"
        try:
            from storage import storage as get_storage
            store = get_storage()
            store.upload(storage_path, file_content, content_type=ALLOWED_CONTENT_TYPES.get(ext, "application/octet-stream"))
        except Exception as e:
            logger.warning("Storage upload failed, falling back to temp file: %s", e)
            # Fallback: write to temp dir so processing can continue
            import tempfile
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}")
            tmp.write(file_content)
            tmp.flush()
            storage_path = tmp.name

        job = ImportJob.objects.create(
            user=user,
            original_filename=original_name,
            file_type=ext,
            file_path=storage_path,
            file_size=len(file_content),
            status=ImportStatus.PENDING,
        )

        # Enqueue async processing
        try:
            from celery_app.tasks.import_tasks import process_import_job
            process_import_job.delay(str(job.id))
        except Exception:
            logger.warning("Celery unavailable — processing import synchronously")
            ImportService.process(job)

        return job

    # ── Processing (called by Celery task) ───────────────────────────────────

    @staticmethod
    def process(job: ImportJob) -> None:
        """Parse the uploaded file, extract profile data, save for review."""
        job.status = ImportStatus.PROCESSING
        job.save(update_fields=["status"])

        # Resolve file content: try storage backend first, then treat path as local
        file_content = ImportService._read_file(job.file_path)

        # Write to a temp file so parsers can use file path
        import tempfile
        ext = job.file_type
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{ext}") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            # Parse
            parser = get_parser(ext)
            raw_text = parser.parse(tmp_path)

            # Extract
            extracted, confidence = ProfileExtractor.extract(raw_text)
            mapping_review = ProfileExtractor.build_mapping_review(extracted, confidence)

            job.parsed_data = extracted
            job.confidence_scores = confidence
            job.mapping_review = mapping_review
            job.status = ImportStatus.REVIEW_REQUIRED
            job.save(update_fields=["parsed_data", "confidence_scores", "mapping_review", "status", "updated_at"])

        except Exception as exc:
            job.status = ImportStatus.FAILED
            job.error_message = str(exc)[:1000]
            job.save(update_fields=["status", "error_message", "updated_at"])
            raise
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    @staticmethod
    def _read_file(file_path: str) -> bytes:
        """Read file content from storage backend or local filesystem."""
        try:
            from storage import storage as get_storage
            store = get_storage()
            return store.download(file_path)
        except Exception:
            # Fallback: treat as local path
            with open(file_path, "rb") as f:
                return f.read()

    # ── Apply mapping (user-approved) ────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def apply_mapping(job: ImportJob, approved: dict) -> ImportJob:
        """
        Apply user-approved field mappings to the canonical UserProfile.
        approved: dict with same shape as mapping_review, filtered to approved items.
        """
        from apps.profiles.models import (
            UserProfile, WorkExperience, Education, Skill,
            Project, Certification, Achievement,
        )

        profile = UserProfile.objects.get(user=job.user)

        # Personal fields
        personal = approved.get("personal") or {}
        updates: dict = {}
        if "full_name" in personal:
            # full_name maps to User model
            name_parts = personal["full_name"].rsplit(" ", 1)
            job.user.first_name = name_parts[0]
            job.user.last_name = name_parts[1] if len(name_parts) > 1 else ""
            job.user.save(update_fields=["first_name", "last_name"])
        for field in ("phone", "headline", "website_url", "linkedin_url", "github_url", "twitter_url"):
            if field in personal:
                updates[field] = personal[field]
        if "location" in personal:
            updates["location"] = personal["location"]
        if updates:
            for attr, val in updates.items():
                setattr(profile, attr, val)
            profile.save()

        # Summary
        if approved.get("summary"):
            profile.professional_summary = approved["summary"]
            profile.save(update_fields=["professional_summary", "updated_at"])

        # Work experiences — deduplicate on (job_title, company_name, start_date)
        for exp in (approved.get("work_experiences") or []):
            exp = dict(exp)
            start_date = exp.pop("start_date", None) or "2020-01-01"
            end_date = exp.pop("end_date", None) or None
            exp.pop("employment_type", None)
            job_title = exp.get("job_title", "")
            company_name = exp.get("company_name", "")
            if WorkExperience.objects.filter(
                profile=profile, job_title=job_title,
                company_name=company_name, start_date=start_date,
            ).exists():
                continue
            WorkExperience.objects.create(
                profile=profile,
                start_date=start_date,
                end_date=end_date,
                employment_type="full_time",
                **{k: v for k, v in exp.items() if k in (
                    "company_name", "job_title", "location",
                    "is_current", "description", "achievements", "technologies",
                )},
            )

        # Educations — deduplicate on (institution, degree, start_date)
        for edu in (approved.get("educations") or []):
            edu = dict(edu)
            start_date = edu.pop("start_date", None) or "2018-01-01"
            end_date = edu.pop("end_date", None) or None
            gpa = edu.pop("gpa", None)
            institution = edu.get("institution", "")
            degree = edu.get("degree", "")
            if Education.objects.filter(
                profile=profile, institution=institution,
                degree=degree, start_date=start_date,
            ).exists():
                continue
            Education.objects.create(
                profile=profile,
                start_date=start_date,
                end_date=end_date,
                gpa=gpa,
                **{k: v for k, v in edu.items() if k in (
                    "institution", "degree", "field_of_study",
                    "description", "achievements",
                )},
            )

        # Skills
        for skill in (approved.get("skills") or []):
            Skill.objects.get_or_create(
                profile=profile,
                name=skill.get("name", "")[:100],
                defaults={
                    "category": skill.get("category", "other"),
                    "proficiency_level": skill.get("proficiency_level", "intermediate"),
                },
            )

        # Projects — deduplicate on title
        for proj in (approved.get("projects") or []):
            if Project.objects.filter(profile=profile, title=proj.get("title", "")).exists():
                continue
            Project.objects.create(
                profile=profile,
                **{k: v for k, v in proj.items() if k in (
                    "title", "description", "role", "technologies",
                    "live_url", "repo_url", "highlights",
                )},
            )

        # Certifications — deduplicate on (name, issuing_organization)
        for cert in (approved.get("certifications") or []):
            if Certification.objects.filter(
                profile=profile, name=cert.get("name", ""),
                issuing_organization=cert.get("issuing_organization", ""),
            ).exists():
                continue
            issue_date = cert.get("issue_date") or "2020-01-01"
            Certification.objects.create(
                profile=profile,
                issue_date=issue_date,
                **{k: v for k, v in cert.items() if k in (
                    "name", "issuing_organization", "credential_id", "credential_url",
                )},
            )

        # Achievements — deduplicate on title
        for ach in (approved.get("achievements") or []):
            if Achievement.objects.filter(profile=profile, title=ach.get("title", "")[:200]).exists():
                continue
            Achievement.objects.create(
                profile=profile,
                **{k: v for k, v in ach.items() if k in (
                    "title", "description", "date", "issuer",
                )},
            )

        job.status = ImportStatus.APPLIED
        job.applied_at = timezone.now()
        job.save(update_fields=["status", "applied_at", "updated_at"])
        return job

    # ── Query ─────────────────────────────────────────────────────────────────

    @staticmethod
    def list_for_user(user) -> list:
        return ImportJob.objects.filter(user=user).order_by("-created_at")

    @staticmethod
    def get_for_user(job_id: str, user) -> ImportJob:
        return ImportJob.objects.get(id=job_id, user=user)

    @staticmethod
    def delete(job: ImportJob) -> None:
        """Delete the import job and remove the stored file."""
        try:
            from storage import storage as get_storage
            get_storage().delete(job.file_path)
        except Exception:
            pass
        job.delete()

    @staticmethod
    def cancel(job: ImportJob) -> ImportJob:
        """Cancel a pending or processing job."""
        if job.status in (ImportStatus.PENDING, ImportStatus.PROCESSING, ImportStatus.REVIEW_REQUIRED):
            job.status = ImportStatus.FAILED
            job.error_message = "Cancelled by user."
            job.save(update_fields=["status", "error_message", "updated_at"])
        return job
