"""
Tests for Celery recommendation tasks.

generate_recommendations_task — thin wrapper around RecommendationService.
fan_out_recommendations_task   — fan-out scheduler; one child task per eligible user.

CELERY_TASK_ALWAYS_EAGER=True in test settings means tasks execute synchronously.
Service and ORM calls are mocked. Because the tasks use lazy imports (same pattern
as sync_jobs_task), patches must target the module where the import lives, not the
task module itself: apps.career_hub.services.recommendations.RecommendationService
and apps.profiles.models.UserProfile.
"""
import dataclasses
import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from apps.career_hub.services.recommendations import RecommendationResult
from celery_app.tasks.career_hub_tasks import (
    fan_out_recommendations_task,
    generate_recommendations_task,
)


# ─── generate_recommendations_task ────────────────────────────────────────────

class TestGenerateRecommendationsTask:
    def test_calls_service_with_user_id(self):
        uid = _make_user_id()
        result = _make_success_result(uid)
        with patch(
            "apps.career_hub.services.recommendations.RecommendationService.generate_for_user",
            return_value=result,
        ) as mock_gen:
            generate_recommendations_task(uid)
            mock_gen.assert_called_once_with(uid)

    def test_returns_dict_representation_of_result(self):
        uid = _make_user_id()
        result = _make_success_result(uid)
        with patch(
            "apps.career_hub.services.recommendations.RecommendationService.generate_for_user",
            return_value=result,
        ):
            output = generate_recommendations_task(uid)

        assert isinstance(output, dict)
        assert output["user_id"] == uid
        assert output["skipped"] is False
        assert output["jobs_scored"] == 10
        assert output["recommendations_persisted"] == 5

    def test_skipped_result_is_returned_as_dict(self):
        uid = _make_user_id()
        result = RecommendationResult(
            user_id=uid, skipped=True, skip_reason="no_profile"
        )
        with patch(
            "apps.career_hub.services.recommendations.RecommendationService.generate_for_user",
            return_value=result,
        ):
            output = generate_recommendations_task(uid)

        assert output["skipped"] is True
        assert output["skip_reason"] == "no_profile"

    def test_returned_dict_matches_dataclass_fields(self):
        uid = _make_user_id()
        result = _make_success_result(uid)
        with patch(
            "apps.career_hub.services.recommendations.RecommendationService.generate_for_user",
            return_value=result,
        ):
            output = generate_recommendations_task(uid)

        assert set(output.keys()) == set(dataclasses.asdict(result).keys())

    def test_task_name_is_registered(self):
        assert generate_recommendations_task.name == "career_hub.generate_recommendations"

    def test_task_queue_is_career_hub(self):
        assert generate_recommendations_task.queue == "career_hub"


# ─── fan_out_recommendations_task ─────────────────────────────────────────────

class TestFanOutRecommendationsTask:
    def test_enqueues_one_task_per_eligible_user(self):
        user_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

        with (
            patch("apps.profiles.models.UserProfile.objects") as mock_objs,
            patch(
                "celery_app.tasks.career_hub_tasks.generate_recommendations_task"
            ) as mock_gen_task,
        ):
            mock_objs.filter.return_value.values_list.return_value.order_by.return_value = user_ids
            output = fan_out_recommendations_task()

        assert mock_gen_task.delay.call_count == 3
        assert output["enqueued"] == 3

    def test_passes_string_user_ids_to_child_tasks(self):
        uid = uuid.uuid4()

        with (
            patch("apps.profiles.models.UserProfile.objects") as mock_objs,
            patch(
                "celery_app.tasks.career_hub_tasks.generate_recommendations_task"
            ) as mock_gen_task,
        ):
            mock_objs.filter.return_value.values_list.return_value.order_by.return_value = [uid]
            fan_out_recommendations_task()

        mock_gen_task.delay.assert_called_once_with(str(uid))

    def test_empty_user_list_enqueues_nothing(self):
        with (
            patch("apps.profiles.models.UserProfile.objects") as mock_objs,
            patch(
                "celery_app.tasks.career_hub_tasks.generate_recommendations_task"
            ) as mock_gen_task,
        ):
            mock_objs.filter.return_value.values_list.return_value.order_by.return_value = []
            output = fan_out_recommendations_task()

        mock_gen_task.delay.assert_not_called()
        assert output["enqueued"] == 0

    def test_filters_only_onboarding_complete_users(self):
        with (
            patch("apps.profiles.models.UserProfile.objects") as mock_objs,
            patch("celery_app.tasks.career_hub_tasks.generate_recommendations_task"),
        ):
            mock_objs.filter.return_value.values_list.return_value.order_by.return_value = []
            fan_out_recommendations_task()

        mock_objs.filter.assert_called_once_with(onboarding_complete=True)

    def test_task_name_is_registered(self):
        assert fan_out_recommendations_task.name == "career_hub.fan_out_recommendations"

    def test_task_queue_is_career_hub(self):
        assert fan_out_recommendations_task.queue == "career_hub"


# ─── Security — user isolation ────────────────────────────────────────────────

class TestUserIsolation:
    """Verify that generate_for_user is always called with the task's own user_id.

    This prevents cross-user recommendation leakage at the task boundary.
    """

    def test_task_passes_exact_user_id_to_service(self):
        uid_a = _make_user_id()
        uid_b = _make_user_id()
        assert uid_a != uid_b

        result_a = RecommendationResult(user_id=uid_a)
        result_b = RecommendationResult(user_id=uid_b)

        with patch(
            "apps.career_hub.services.recommendations.RecommendationService.generate_for_user",
            side_effect=[result_a, result_b],
        ) as mock_gen:
            generate_recommendations_task(uid_a)
            generate_recommendations_task(uid_b)

        calls = mock_gen.call_args_list
        assert calls[0] == call(uid_a)
        assert calls[1] == call(uid_b)

    def test_fan_out_does_not_cross_users(self):
        uid_a = uuid.uuid4()
        uid_b = uuid.uuid4()

        with (
            patch("apps.profiles.models.UserProfile.objects") as mock_objs,
            patch(
                "celery_app.tasks.career_hub_tasks.generate_recommendations_task"
            ) as mock_gen_task,
        ):
            mock_objs.filter.return_value.values_list.return_value.order_by.return_value = [
                uid_a, uid_b
            ]
            fan_out_recommendations_task()

        delay_calls = [c.args[0] for c in mock_gen_task.delay.call_args_list]
        assert str(uid_a) in delay_calls
        assert str(uid_b) in delay_calls
        assert len(delay_calls) == 2


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user_id() -> str:
    return str(uuid.uuid4())


def _make_success_result(user_id: str) -> RecommendationResult:
    return RecommendationResult(
        user_id=user_id,
        skipped=False,
        skip_reason="",
        jobs_scored=10,
        recommendations_persisted=5,
        stale_removed=2,
        elapsed_ms=123.4,
    )
