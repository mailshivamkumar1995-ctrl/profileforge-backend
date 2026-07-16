import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("career_hub", "0003_job_description_2000"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ResumeMatchScore",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="match_scores", to=settings.AUTH_USER_MODEL)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="match_scores", to="career_hub.job")),
                ("overall_score", models.DecimalField(decimal_places=3, max_digits=4)),
                ("skill_score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("experience_score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("keyword_score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("title_score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("education_score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("certification_score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("location_score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("salary_score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("skill_gaps", models.JSONField(default=dict)),
                ("scoring_version", models.CharField(max_length=20)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "career_hub_resume_match_score"},
        ),
        migrations.AddConstraint(
            model_name="resumematchscore",
            constraint=models.UniqueConstraint(fields=["user", "job"], name="uq_match_score_user_job"),
        ),
        migrations.AddConstraint(
            model_name="resumematchscore",
            constraint=models.CheckConstraint(
                check=models.Q(overall_score__gte=0) & models.Q(overall_score__lte=1),
                name="chk_match_score_overall_range",
            ),
        ),
        migrations.AddIndex(
            model_name="resumematchscore",
            index=models.Index(fields=["user", "overall_score"], name="ch_match_score_user_score_idx"),
        ),
        migrations.AddIndex(
            model_name="resumematchscore",
            index=models.Index(fields=["job", "overall_score"], name="ch_match_score_job_score_idx"),
        ),
    ]
