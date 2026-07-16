from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_engine", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiusagelog",
            name="feature",
            field=models.CharField(
                choices=[
                    ("bullet_enhance", "Bullet Enhancement"),
                    ("summary_generate", "Summary Generation"),
                    ("cover_letter_generate", "Cover Letter Generation"),
                    ("cover_letter_rewrite", "Cover Letter Rewrite"),
                    ("cover_letter_improve_tone", "Cover Letter Tone Improvement"),
                    ("cover_letter_improve_ats", "Cover Letter ATS Improvement"),
                    ("ats_analyze", "ATS Analysis"),
                    ("content_rewrite", "Content Rewrite"),
                    ("job_match", "Job Description Matching"),
                    ("resume_bullet_rewrite", "Resume Bullet Rewrite"),
                    ("resume_summary_optimize", "Resume Summary Optimization"),
                ],
                max_length=30,
            ),
        ),
    ]
