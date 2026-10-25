import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

import applications.models


def backfill_queue_fields(apps, schema_editor):
    Application = apps.get_model("applications", "Application")
    Event = apps.get_model("applications", "ApplicationEvent")
    alias = schema_editor.connection.alias
    for application in Application.objects.using(alias).all().iterator():
        number = f"AC-{uuid.uuid4().hex[:16].upper()}"
        while Application.objects.using(alias).filter(number=number).exists():
            number = f"AC-{uuid.uuid4().hex[:16].upper()}"
        event = (
            Event.objects.using(alias)
            .filter(application_id=application.pk)
            .exclude(from_status=models.F("to_status"))
            .order_by("-created_at", "-id")
            .first()
        )
        Application.objects.using(alias).filter(pk=application.pk).update(
            number=number, status_changed_at=event.created_at if event else application.created_at
        )


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.AddField(
            model_name="application",
            name="number",
            field=models.CharField(
                editable=False, max_length=19, null=True, unique=True, verbose_name="Номер заявки"
            ),
        ),
        migrations.AddField(
            model_name="application",
            name="status_changed_at",
            field=models.DateTimeField(
                editable=False, null=True, verbose_name="Начало текущего состояния"
            ),
        ),
        migrations.AddField(
            model_name="application",
            name="assigned_to",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="assigned_applications",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="application",
            name="assigned_at",
            field=models.DateTimeField(
                blank=True, editable=False, null=True, verbose_name="Назначена"
            ),
        ),
        migrations.RunPython(backfill_queue_fields, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="application",
            name="number",
            field=models.CharField(
                default=applications.models.application_number,
                editable=False,
                max_length=19,
                unique=True,
                verbose_name="Номер заявки",
            ),
        ),
        migrations.AlterField(
            model_name="application",
            name="status_changed_at",
            field=models.DateTimeField(
                default=django.utils.timezone.now,
                editable=False,
                verbose_name="Начало текущего состояния",
            ),
        ),
        migrations.AddIndex(
            model_name="application",
            index=models.Index(
                fields=["assigned_to", "status", "-created_at"], name="app_assignee_queue_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="application",
            constraint=models.CheckConstraint(
                condition=models.Q(assigned_to__isnull=True, assigned_at__isnull=True)
                | models.Q(assigned_to__isnull=False, assigned_at__isnull=False),
                name="application_assignment_pair",
            ),
        ),
    ]
