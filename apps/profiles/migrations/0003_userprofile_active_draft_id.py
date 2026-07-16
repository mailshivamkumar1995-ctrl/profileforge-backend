# P1-2: ADR-001 — active_draft_id as UUIDField (no FK, no cross-app migration dependency)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0002_userprofile_onboarding_complete'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofile',
            name='active_draft_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]
