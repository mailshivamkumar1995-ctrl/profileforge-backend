# P1-2: Career Hub initial schema — 2026-06-22

import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


def _apply_fts_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE OR REPLACE FUNCTION career_hub_update_job_tsv()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.description_tsv := to_tsvector('english',
                coalesce(NEW.title, '') || ' ' ||
                coalesce(NEW.company, '') || ' ' ||
                coalesce(NEW.description, '')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    schema_editor.execute("""
        CREATE TRIGGER career_hub_job_tsv_trigger
            BEFORE INSERT OR UPDATE OF title, company, description
            ON career_hub_job
            FOR EACH ROW EXECUTE FUNCTION career_hub_update_job_tsv();
    """)


def _revert_fts_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS career_hub_job_tsv_trigger ON career_hub_job;")
    schema_editor.execute("DROP FUNCTION IF EXISTS career_hub_update_job_tsv();")


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── JobSource ─────────────────────────────────────────────────────────

        migrations.CreateModel(
            name='JobSource',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('slug', models.SlugField(max_length=50, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'career_hub_job_source',
            },
        ),

        # ── Job ───────────────────────────────────────────────────────────────

        migrations.CreateModel(
            name='Job',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('external_id', models.CharField(max_length=200)),
                ('title', models.CharField(max_length=200)),
                ('company', models.CharField(max_length=200)),
                ('description', models.CharField(max_length=500)),
                ('description_tsv', django.contrib.postgres.search.SearchVectorField(null=True)),
                ('apply_url', models.URLField(max_length=500)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('work_type', models.CharField(
                    choices=[('remote', 'Remote'), ('hybrid', 'Hybrid'), ('onsite', 'Onsite')],
                    default='hybrid',
                    max_length=20,
                )),
                ('salary_min', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('salary_max', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('salary_currency', models.CharField(default='INR', max_length=3)),
                ('posted_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('is_private', models.BooleanField(default=False)),
                ('fetched_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('source', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='jobs',
                    to='career_hub.jobsource',
                )),
            ],
            options={
                'db_table': 'career_hub_job',
            },
        ),

        # ── UserJob ───────────────────────────────────────────────────────────

        migrations.CreateModel(
            name='UserJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(
                    choices=[('saved', 'Saved'), ('applied', 'Applied'), ('rejected', 'Rejected'), ('interview', 'Interview'), ('offer', 'Offer')],
                    default='saved',
                    max_length=20,
                )),
                ('notes', models.TextField(blank=True)),
                ('applied_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('job', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='user_jobs',
                    to='career_hub.job',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='saved_jobs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'career_hub_user_job',
            },
        ),

        # ── Draft ─────────────────────────────────────────────────────────────

        migrations.CreateModel(
            name='Draft',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('draft_type', models.CharField(
                    choices=[('resume', 'Resume'), ('cover_letter', 'Cover Letter'), ('general', 'General')],
                    default='resume',
                    max_length=20,
                )),
                ('content', models.JSONField(blank=True, default=dict)),
                ('profile_snapshot_hash', models.CharField(blank=True, max_length=64)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('target_job', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='targeted_drafts',
                    to='career_hub.job',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='drafts',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'career_hub_draft',
            },
        ),

        # ── JobRecommendation ─────────────────────────────────────────────────

        migrations.CreateModel(
            name='JobRecommendation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('score', models.DecimalField(decimal_places=3, max_digits=4)),
                ('algorithm_version', models.CharField(max_length=20)),
                ('generated_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('is_dismissed', models.BooleanField(default=False)),
                ('job', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='recommendations',
                    to='career_hub.job',
                )),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='job_recommendations',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'career_hub_job_recommendation',
            },
        ),

        # ── Constraints ───────────────────────────────────────────────────────

        migrations.AddConstraint(
            model_name='job',
            constraint=models.UniqueConstraint(
                fields=['source', 'external_id'],
                name='uq_job_source_external',
            ),
        ),
        migrations.AddConstraint(
            model_name='userjob',
            constraint=models.UniqueConstraint(
                fields=['user', 'job'],
                name='uq_user_job',
            ),
        ),
        migrations.AddConstraint(
            model_name='jobrecommendation',
            constraint=models.UniqueConstraint(
                fields=['user', 'job'],
                name='uq_recommendation_user_job',
            ),
        ),
        migrations.AddConstraint(
            model_name='jobrecommendation',
            constraint=models.CheckConstraint(
                check=models.Q(score__gte=0) & models.Q(score__lte=1),
                name='chk_recommendation_score_range',
            ),
        ),

        # ── Indexes ───────────────────────────────────────────────────────────

        migrations.AddIndex(
            model_name='job',
            index=django.contrib.postgres.indexes.GinIndex(
                fields=['description_tsv'],
                name='ch_job_tsv_gin_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='job',
            index=models.Index(
                fields=['city', 'work_type', 'is_active'],
                name='ch_job_city_wt_active_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='job',
            index=models.Index(
                fields=['posted_at', 'is_active'],
                name='ch_job_posted_active_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='userjob',
            index=models.Index(
                fields=['user', 'status'],
                name='ch_userjob_status_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='userjob',
            index=models.Index(
                fields=['user', 'created_at'],
                name='ch_userjob_created_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='draft',
            index=models.Index(
                fields=['user', 'deleted_at'],
                name='ch_draft_user_del_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='draft',
            index=models.Index(
                fields=['user', 'draft_type', 'deleted_at'],
                name='ch_draft_user_type_del_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='jobrecommendation',
            index=models.Index(
                fields=['user', 'is_dismissed', 'generated_at'],
                name='ch_rec_dismissed_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='jobrecommendation',
            index=models.Index(
                fields=['expires_at'],
                name='career_hub_rec_expires_idx',
            ),
        ),

        # ── FTS trigger ───────────────────────────────────────────────────────
        # Maintains description_tsv as a weighted tsvector over title + company + description.
        # Fires BEFORE INSERT OR UPDATE so description_tsv is always current at write time.
        # Skipped on SQLite (test DB) — plpgsql is PostgreSQL-only.

        migrations.RunPython(
            code=_apply_fts_trigger,
            reverse_code=_revert_fts_trigger,
        ),
    ]
