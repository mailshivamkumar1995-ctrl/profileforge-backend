# P6-2A: add score_breakdown to JobRecommendation — 2026-06-23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("career_hub", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobrecommendation",
            name="score_breakdown",
            field=models.JSONField(null=True, blank=True),
        ),
    ]
