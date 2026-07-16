﻿"""
Custom Prometheus metrics for ProfileForge AI.
Complements django-prometheus auto-instrumentation.
"""
from prometheus_client import Counter, Histogram, Gauge, Summary

# ----------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------
auth_login_success_total = Counter(
    "profileforge_auth_login_success_total",
    "Successful login events",
    ["method"],  # jwt, social
)

auth_login_failures_total = Counter(
    "profileforge_auth_login_failures_total",
    "Failed login attempts",
    ["reason", "ip"],  # invalid_credentials, account_locked, etc.
)

token_blacklist_total = Counter(
    "profileforge_token_blacklist_total",
    "JWT tokens blacklisted",
    ["reason"],  # password_change, logout, admin_revoke
)

# ----------------------------------------------------------------
# Business — Core Events
# ----------------------------------------------------------------
user_registrations_total = Counter(
    "profileforge_user_registrations_total",
    "New user registrations",
    ["plan"],  # free, pro, enterprise
)

resume_generations_total = Counter(
    "profileforge_resume_generations_total",
    "Resume section generations triggered",
    ["section"],  # summary, experience, skills, education
)

portfolio_publishes_total = Counter(
    "profileforge_portfolio_publishes_total",
    "Portfolio publish events",
    ["action"],  # publish, unpublish, update
)

portfolio_views_total = Counter(
    "profileforge_portfolio_views_total",
    "Public portfolio page views",
)

# ----------------------------------------------------------------
# AI Services
# ----------------------------------------------------------------
ai_api_calls_total = Counter(
    "profileforge_ai_api_calls_total",
    "AI API calls made",
    ["provider", "model", "operation"],  # anthropic/claude-3/generate_summary
)

ai_api_errors_total = Counter(
    "profileforge_ai_api_errors_total",
    "AI API call errors",
    ["provider", "error_type"],  # rate_limit, timeout, server_error
)

ai_api_duration_seconds = Histogram(
    "profileforge_ai_api_duration_seconds",
    "AI API call duration in seconds",
    ["provider", "operation"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0],
)

ai_rate_limit_hits_total = Counter(
    "profileforge_ai_rate_limit_hits_total",
    "AI endpoint rate limit hits",
)

ai_tokens_used_total = Counter(
    "profileforge_ai_tokens_used_total",
    "Total AI tokens consumed",
    ["provider", "direction"],  # input, output
)

# ----------------------------------------------------------------
# Export Jobs
# ----------------------------------------------------------------
export_jobs_total = Counter(
    "profileforge_export_jobs_total",
    "Export job completions",
    ["format", "status"],  # pdf/docx/txt × completed/failed/timeout
)

export_duration_seconds = Histogram(
    "profileforge_export_duration_seconds",
    "Export job duration in seconds",
    ["format"],
    buckets=[1.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0],
)

export_file_size_bytes = Histogram(
    "profileforge_export_file_size_bytes",
    "Exported file size in bytes",
    ["format"],
    buckets=[10_000, 50_000, 100_000, 500_000, 1_000_000, 5_000_000],
)

# ----------------------------------------------------------------
# Import Jobs
# ----------------------------------------------------------------
import_jobs_total = Counter(
    "profileforge_import_jobs_total",
    "Import job completions",
    ["file_type", "status"],  # pdf/docx/txt × completed/failed/rejected
)

import_validation_failures_total = Counter(
    "profileforge_upload_validation_failures_total",
    "File upload validation failures (magic byte, size, extension)",
    ["reason"],  # invalid_magic, size_exceeded, unsupported_type
)

import_duration_seconds = Histogram(
    "profileforge_import_duration_seconds",
    "Import job duration in seconds",
    ["file_type"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# ----------------------------------------------------------------
# Cover Letters
# ----------------------------------------------------------------
cover_letter_generations_total = Counter(
    "profileforge_cover_letter_generations_total",
    "Cover letter generation events",
    ["status"],  # completed, failed, rate_limited
)

# ----------------------------------------------------------------
# Active Users (Gauge)
# ----------------------------------------------------------------
active_users_gauge = Gauge(
    "profileforge_active_users",
    "Number of users with an active session in the last 15 minutes",
)

# ----------------------------------------------------------------
# Queue Depth (Gauge — updated by Celery beat task)
# ----------------------------------------------------------------
celery_queue_depth = Gauge(
    "profileforge_celery_queue_depth",
    "Number of pending tasks in Celery queue",
    ["queue"],
)
