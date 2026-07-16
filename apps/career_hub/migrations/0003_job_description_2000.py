# P7-1 C-01: raise Job.description cap from 500 → 2000 chars — 2026-06-23
#
# PostgreSQL deployment fix (LL-060): The career_hub_job_tsv_trigger references
# the description column in its UPDATE OF clause. PostgreSQL blocks ALTER COLUMN
# TYPE on any column listed explicitly in a trigger definition.
# Fix: drop the trigger, alter the column, recreate the trigger atomically.
# The trigger function body is unchanged; only the DDL ordering is affected.

from django.db import migrations, models


def _drop_fts_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS career_hub_job_tsv_trigger ON career_hub_job;")


def _recreate_fts_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE TRIGGER career_hub_job_tsv_trigger
            BEFORE INSERT OR UPDATE OF title, company, description
            ON career_hub_job
            FOR EACH ROW EXECUTE FUNCTION career_hub_update_job_tsv();
    """)


def _revert_alter(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP TRIGGER IF EXISTS career_hub_job_tsv_trigger ON career_hub_job;")


class Migration(migrations.Migration):

    dependencies = [
        ("career_hub", "0002_jobrecommendation_score_breakdown"),
    ]

    operations = [
        migrations.RunPython(_drop_fts_trigger, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="job",
            name="description",
            field=models.CharField(max_length=2000),
        ),
        migrations.RunPython(_recreate_fts_trigger, _revert_alter),
    ]
