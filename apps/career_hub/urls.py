from django.urls import path

from apps.career_hub.views import (
    JobDetailView,
    JobListView,
    JobMatchScoreView,
    JobSkillGapView,
    MatchScoreBulkGenerateView,
    MatchScoreDetailView,
    MatchScoreGenerateView,
    MatchScoreListView,
    RecommendationDetailView,
    RecommendationDismissView,
    RecommendationListView,
    SavedJobListView,
    SaveJobView,
    SkillGapRecommendationsView,
    SkillGapSummaryView,
)

urlpatterns = [
    path("jobs/", JobListView.as_view(), name="career-hub-job-list"),
    path("jobs/<uuid:pk>/", JobDetailView.as_view(), name="career-hub-job-detail"),
    path("jobs/<uuid:pk>/save/", SaveJobView.as_view(), name="career-hub-save-job"),
    path("jobs/<uuid:pk>/match-score/", JobMatchScoreView.as_view(), name="career-hub-job-match-score"),
    path("saved-jobs/", SavedJobListView.as_view(), name="career-hub-saved-jobs"),
    path("recommendations/", RecommendationListView.as_view(), name="career-hub-recommendations"),
    path("recommendations/<uuid:pk>/", RecommendationDetailView.as_view(), name="career-hub-recommendation-detail"),
    path("recommendations/<uuid:pk>/dismiss/", RecommendationDismissView.as_view(), name="career-hub-recommendation-dismiss"),
    path("match-scores/", MatchScoreListView.as_view(), name="career-hub-match-score-list"),
    path("match-scores/generate/", MatchScoreGenerateView.as_view(), name="career-hub-match-score-generate"),
    path("match-scores/bulk-generate/", MatchScoreBulkGenerateView.as_view(), name="career-hub-match-score-bulk-generate"),
    path("match-scores/<uuid:pk>/", MatchScoreDetailView.as_view(), name="career-hub-match-score-detail"),
    path("skill-gap-analysis/summary/", SkillGapSummaryView.as_view(), name="career-hub-skill-gap-summary"),
    path("skill-gap-analysis/recommendations/", SkillGapRecommendationsView.as_view(), name="career-hub-skill-gap-recommendations"),
    path("skill-gap-analysis/jobs/<uuid:job_id>/", JobSkillGapView.as_view(), name="career-hub-job-skill-gap"),
]
