import logging
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response

from apps.career_hub.models import Job, JobRecommendation, ResumeMatchScore, UserJob
from apps.career_hub.services.api_services import (
    dismiss_recommendation,
    get_job_by_id,
    get_match_score_by_id,
    get_match_score_for_job,
    get_match_scores_for_user,
    get_recommendation_by_id,
    get_saved_jobs_for_user,
    get_user_recommendations,
    save_user_job,
    unsave_user_job,
)
from apps.career_hub.serializers import (
    JobDetailSerializer,
    JobListSerializer,
    JobRecommendationDetailSerializer,
    JobRecommendationSerializer,
    JobSearchQuerySerializer,
    JobSkillGapSerializer,
    MatchScoreBulkGenerateSerializer,
    MatchScoreGenerateSerializer,
    RecommendationFilterSerializer,
    ResumeMatchScoreSerializer,
    SkillGapRecommendationSerializer,
    SkillGapSummarySerializer,
    SkillGapTierFilterSerializer,
    UserJobSerializer,
)
from apps.career_hub.services.match_service import (
    bulk_generate_match_scores,
    generate_match_score,
)
from apps.career_hub.services.skill_gap_service import (
    get_job_skill_gap,
    get_skill_gap_recommendations,
    get_skill_gap_summary,
)
from apps.career_hub.services.search import JobSearchService
from apps.profiles.models import UserProfile
from core.mixins import SuccessResponseMixin
from core.pagination import StandardResultsSetPagination
from core.throttles import CareerHubSearchThrottle

logger = logging.getLogger(__name__)


class JobListView(SuccessResponseMixin, generics.GenericAPIView):
    serializer_class = JobListSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [CareerHubSearchThrottle]

    def get(self, request):
        query_ser = JobSearchQuerySerializer(data=request.query_params)
        query_ser.is_valid(raise_exception=True)
        p = query_ser.validated_data

        qs = JobSearchService().search(
            q=p.get("q", ""),
            city=p.get("city", ""),
            work_type=p.get("work_type"),
            source=p.get("source"),
            salary_min=p.get("salary_min"),
            salary_max=p.get("salary_max"),
            sort=p.get("sort", "newest"),
        )

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            self.paginator.meta_extras = {"is_syncing": getattr(qs, "_is_syncing", False)}
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(qs, many=True)
        # For non-paginated, add meta via the mixin if supported, otherwise it just returns data
        return self.success_response(serializer.data)


class JobDetailView(SuccessResponseMixin, generics.GenericAPIView):
    serializer_class = JobDetailSerializer

    def get(self, request, pk):
        job = get_job_by_id(pk)
        serializer = self.get_serializer(job)
        return self.success_response(serializer.data)


class SaveJobView(SuccessResponseMixin, generics.GenericAPIView):
    serializer_class = UserJobSerializer

    def post(self, request, pk):
        user_job, created = save_user_job(request.user, pk)
        serializer = self.get_serializer(user_job)
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return self.success_response(serializer.data, status_code=http_status)

    def delete(self, request, pk):
        unsave_user_job(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SavedJobListView(SuccessResponseMixin, generics.GenericAPIView):
    serializer_class = UserJobSerializer
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        qs = get_saved_jobs_for_user(request.user)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return self.success_response(serializer.data)


class RecommendationListView(SuccessResponseMixin, generics.GenericAPIView):
    serializer_class = JobRecommendationSerializer
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        filter_ser = RecommendationFilterSerializer(data=request.query_params)
        filter_ser.is_valid(raise_exception=True)
        show_dismissed = filter_ser.validated_data["dismissed"]
        qs = get_user_recommendations(request.user, show_dismissed)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return self.success_response(serializer.data)


class RecommendationDetailView(SuccessResponseMixin, generics.GenericAPIView):
    serializer_class = JobRecommendationDetailSerializer

    def get(self, request, pk):
        rec = get_recommendation_by_id(request.user, pk)
        serializer = self.get_serializer(rec)
        return self.success_response(serializer.data)


class RecommendationDismissView(SuccessResponseMixin, generics.GenericAPIView):

    def patch(self, request, pk):
        rec = dismiss_recommendation(request.user, pk)
        return self.success_response({"id": str(rec.id), "is_dismissed": rec.is_dismissed})


class MatchScoreListView(SuccessResponseMixin, generics.GenericAPIView):
    serializer_class = ResumeMatchScoreSerializer
    pagination_class = StandardResultsSetPagination

    def get(self, request):
        min_score = request.query_params.get("min_score")
        qs = get_match_scores_for_user(request.user, min_score)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return self.success_response(serializer.data)


class MatchScoreDetailView(SuccessResponseMixin, generics.GenericAPIView):
    serializer_class = ResumeMatchScoreSerializer

    def get(self, request, pk):
        score = get_match_score_by_id(request.user, pk)
        serializer = self.get_serializer(score)
        return self.success_response(serializer.data)


class MatchScoreGenerateView(SuccessResponseMixin, generics.GenericAPIView):

    def post(self, request):
        input_ser = MatchScoreGenerateSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)

        job = get_job_by_id(input_ser.validated_data["job_id"])

        try:
            score = generate_match_score(request.user, job)
        except UserProfile.DoesNotExist:
            raise ValidationError(
                {"detail": "Profile not found. Please complete your profile first."}
            )

        output_ser = ResumeMatchScoreSerializer(score)
        return self.success_response(output_ser.data, status_code=status.HTTP_201_CREATED)


class MatchScoreBulkGenerateView(SuccessResponseMixin, generics.GenericAPIView):

    def post(self, request):
        input_ser = MatchScoreBulkGenerateSerializer(data=request.data)
        input_ser.is_valid(raise_exception=True)

        try:
            scores = bulk_generate_match_scores(
                request.user,
                input_ser.validated_data["job_ids"],
            )
        except UserProfile.DoesNotExist:
            raise ValidationError(
                {"detail": "Profile not found. Please complete your profile first."}
            )

        output_ser = ResumeMatchScoreSerializer(scores, many=True)
        return self.success_response(
            {"generated": len(scores), "scores": output_ser.data}
        )


class JobMatchScoreView(SuccessResponseMixin, generics.GenericAPIView):
    serializer_class = ResumeMatchScoreSerializer

    def get(self, request, pk):
        score = get_match_score_for_job(request.user, pk)
        serializer = self.get_serializer(score)
        return self.success_response(serializer.data)


class SkillGapSummaryView(SuccessResponseMixin, generics.GenericAPIView):
    def get(self, request):
        summary = get_skill_gap_summary(request.user)
        serializer = SkillGapSummarySerializer(summary)
        return self.success_response(serializer.data)


class SkillGapRecommendationsView(SuccessResponseMixin, generics.GenericAPIView):
    def get(self, request):
        filter_ser = SkillGapTierFilterSerializer(data=request.query_params)
        filter_ser.is_valid(raise_exception=True)
        tier = filter_ser.validated_data["tier"]
        recommendations = get_skill_gap_recommendations(request.user, tier=tier)
        serializer = SkillGapRecommendationSerializer(recommendations, many=True)
        return self.success_response(serializer.data)


class JobSkillGapView(SuccessResponseMixin, generics.GenericAPIView):
    def get(self, request, job_id):
        try:
            job_gap = get_job_skill_gap(request.user, job_id)
        except ResumeMatchScore.DoesNotExist:
            raise NotFound("No match score found for this job.")
        serializer = JobSkillGapSerializer(job_gap)
        return self.success_response(serializer.data)
