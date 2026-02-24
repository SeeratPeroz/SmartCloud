from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ("SmileHealth", "0005_profile_description_profile_gender_activitylog"),
    ]

    operations = [
        migrations.CreateModel(
            name="CaseGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("visibility", models.CharField(choices=[("PRIVATE", "Privat"), ("SHARED", "Geteilt")], db_index=True, default="PRIVATE", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="case_groups", to=settings.AUTH_USER_MODEL)),
                ("shared_with", models.ManyToManyField(blank=True, related_name="shared_case_groups", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddField(
            model_name="patient",
            name="group",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="patients", to="SmileHealth.casegroup"),
        ),
    ]
