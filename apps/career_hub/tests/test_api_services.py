import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from rest_framework.exceptions import NotFound, ValidationError

from apps.career_hub.models import Job, UserJob, JobRecommendation, ResumeMatchScore, JobSource
from apps.career_hub.services.api_services import (
    get_job_by_id,
    save_user_job,
    unsave_user_job,
    get_saved_jobs_for_user,
    get_user_recommendations,
    get_recommendation_by_id,
    dismiss_recommendation,
    get_match_scores_for_user,
    get_match_score_by_id,
    get_match_score_for_job,
)


@pytest.fixture
def default_source(db):
    return JobSource.objects.create(name="Default Source", slug="default")


@pytest.fixture
def active_job(db, default_source):
    return Job.objects.create(
        source=default_source,
        external_id="ext-1",
        apply_url="https://example.com/apply/1",
        title="Test Job",
        company="Acme Corp",
        description="A great job.",
        is_active=True,
        is_private=False,
    )


@pytest.fixture
def inactive_job(db, default_source):
    return Job.objects.create(
        source=default_source,
        external_id="ext-2",
        apply_url="https://example.com/apply/2",
        title="Inactive Job",
        company="Acme Corp",
        description="Inactive.",
        is_active=False,
        is_private=False,
    )


@pytest.mark.django_db
class TestJobServices:
    def test_get_job_by_id_success(self, active_job):
        job = get_job_by_id(str(active_job.id))
        assert job == active_job

    def test_get_job_by_id_not_found_when_inactive(self, inactive_job):
        with pytest.raises(NotFound):
            get_job_by_id(str(inactive_job.id))

    def test_get_job_by_id_does_not_exist(self):
        with pytest.raises(NotFound):
            get_job_by_id("00000000-0000-0000-0000-000000000000")


@pytest.mark.django_db
class TestUserJobServices:
    def test_save_user_job(self, user, active_job):
        user_job, created = save_user_job(user, str(active_job.id))
        assert created is True
        assert user_job.user == user
        assert user_job.job == active_job
        assert user_job.status == UserJob.Status.SAVED

        # Saving again should return created=False
        user_job2, created2 = save_user_job(user, str(active_job.id))
        assert created2 is False
        assert user_job2 == user_job

    def test_unsave_user_job(self, user, active_job):
        save_user_job(user, str(active_job.id))
        unsave_user_job(user, str(active_job.id))
        assert not UserJob.objects.filter(user=user, job=active_job).exists()

    def test_unsave_user_job_not_found(self, user, active_job):
        with pytest.raises(NotFound):
            unsave_user_job(user, str(active_job.id))

    def test_get_saved_jobs_for_user(self, user, active_job):
        save_user_job(user, str(active_job.id))
        jobs = get_saved_jobs_for_user(user)
        assert len(jobs) == 1
        assert jobs[0].job == active_job


@pytest.mark.django_db
class TestRecommendationServices:
    @pytest.fixture
    def active_rec(self, user, active_job):
        return JobRecommendation.objects.create(
            user=user,
            job=active_job,
            score=Decimal("0.850"),
            is_dismissed=False,
            expires_at=timezone.now() + timedelta(days=1),
        )

    @pytest.fixture
    def dismissed_rec(self, user, default_source):
        from apps.career_hub.models import Job
        job = Job.objects.create(
            source=default_source, external_id="dismissed-job",
            title="Dismissed Job", company="Acme", apply_url="https://example.com"
        )
        return JobRecommendation.objects.create(
            user=user,
            job=job,
            score=Decimal("0.900"),
            is_dismissed=True,
            expires_at=timezone.now() + timedelta(days=1),
        )

    @pytest.fixture
    def expired_rec(self, user, default_source):
        from apps.career_hub.models import Job
        job = Job.objects.create(
            source=default_source, external_id="expired-job",
            title="Expired Job", company="Acme", apply_url="https://example.com"
        )
        return JobRecommendation.objects.create(
            user=user,
            job=job,
            score=Decimal("0.800"),
            is_dismissed=False,
            expires_at=timezone.now() - timedelta(days=1),
        )

    def test_get_user_recommendations(self, user, active_rec, dismissed_rec, expired_rec):
        recs = list(get_user_recommendations(user, show_dismissed=False))
        assert len(recs) == 1
        assert recs[0] == active_rec

    def test_get_user_recommendations_with_dismissed(self, user, active_rec, dismissed_rec, expired_rec):
        recs = list(get_user_recommendations(user, show_dismissed=True))
        assert len(recs) == 2
        assert active_rec in recs
        assert dismissed_rec in recs

    def test_get_recommendation_by_id(self, user, active_rec):
        rec = get_recommendation_by_id(user, str(active_rec.id))
        assert rec == active_rec

    def test_get_recommendation_by_id_not_found(self, user):
        with pytest.raises(NotFound):
            get_recommendation_by_id(user, "00000000-0000-0000-0000-000000000000")

    def test_dismiss_recommendation(self, user, active_rec):
        rec = dismiss_recommendation(user, str(active_rec.id))
        assert rec.is_dismissed is True
        # Verify DB update
        active_rec.refresh_from_db()
        assert active_rec.is_dismissed is True

    def test_dismiss_recommendation_not_found(self, user):
        with pytest.raises(NotFound):
            dismiss_recommendation(user, "00000000-0000-0000-0000-000000000000")


@pytest.mark.django_db
class TestMatchScoreServices:
    @pytest.fixture
    def high_score(self, user, active_job):
        return ResumeMatchScore.objects.create(
            user=user,
            job=active_job,
            overall_score=Decimal("0.955"),
            skill_score=Decimal("0.9000"),
            experience_score=Decimal("0.9500"),
            keyword_score=Decimal("0.9000"),
            title_score=Decimal("0.9000"),
            education_score=Decimal("0.9000"),
            certification_score=Decimal("0.9000"),
            location_score=Decimal("0.9000"),
            salary_score=Decimal("0.9000"),
        )

    @pytest.fixture
    def low_score(self, user, inactive_job):
        return ResumeMatchScore.objects.create(
            user=user,
            job=inactive_job,
            overall_score=Decimal("0.600"),
            skill_score=Decimal("0.5000"),
            experience_score=Decimal("0.7000"),
            keyword_score=Decimal("0.5000"),
            title_score=Decimal("0.5000"),
            education_score=Decimal("0.5000"),
            certification_score=Decimal("0.5000"),
            location_score=Decimal("0.5000"),
            salary_score=Decimal("0.5000"),
        )

    def test_get_match_scores_for_user(self, user, high_score, low_score):
        scores = list(get_match_scores_for_user(user))
        assert len(scores) == 2
        assert scores[0] == high_score  # High score first (order_by -overall_score)
        assert scores[1] == low_score

    def test_get_match_scores_for_user_with_min_score(self, user, high_score, low_score):
        scores = list(get_match_scores_for_user(user, min_score="0.800"))
        assert len(scores) == 1
        assert scores[0] == high_score

    def test_get_match_scores_for_user_invalid_min_score(self, user):
        with pytest.raises(ValidationError):
            get_match_scores_for_user(user, min_score="invalid")

    def test_get_match_score_by_id(self, user, high_score):
        score = get_match_score_by_id(user, str(high_score.id))
        assert score == high_score

    def test_get_match_score_by_id_not_found(self, user):
        with pytest.raises(NotFound):
            get_match_score_by_id(user, "00000000-0000-0000-0000-000000000000")

    def test_get_match_score_for_job(self, user, active_job, high_score):
        score = get_match_score_for_job(user, str(active_job.id))
        assert score == high_score

    def test_get_match_score_for_job_not_found(self, user, inactive_job):
        with pytest.raises(NotFound):
            get_match_score_for_job(user, "00000000-0000-0000-0000-000000000000")
