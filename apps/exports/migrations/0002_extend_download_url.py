from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("exports", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exportjob",
            name="download_url",
            field=models.TextField(blank=True),
        ),
    ]
