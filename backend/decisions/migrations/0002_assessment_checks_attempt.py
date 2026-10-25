from django.db import migrations, models


def backfill_attempt(apps, schema_editor):
    Assessment = apps.get_model("decisions", "Assessment")
    Check = apps.get_model("checks", "CheckResult")
    alias = schema_editor.connection.alias
    for assessment in Assessment.objects.using(alias).all().iterator():
        attempt = (
            Check.objects.using(alias)
            .filter(revision_id=assessment.revision_id, checked_at__lte=assessment.created_at)
            .aggregate(value=models.Max("attempt"))["value"]
        )
        Assessment.objects.using(alias).filter(pk=assessment.pk).update(checks_attempt=attempt or 1)


class Migration(migrations.Migration):
    dependencies = [("decisions", "0001_initial"), ("checks", "0001_initial")]
    operations = [
        migrations.AddField(
            model_name="assessment",
            name="checks_attempt",
            field=models.PositiveIntegerField(
                null=True, verbose_name="Использованная попытка проверок"
            ),
        ),
        migrations.RunPython(backfill_attempt, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="assessment",
            name="checks_attempt",
            field=models.PositiveIntegerField(
                default=1, verbose_name="Использованная попытка проверок"
            ),
        ),
        migrations.AddConstraint(
            model_name="assessment",
            constraint=models.CheckConstraint(
                condition=models.Q(checks_attempt__gte=1), name="assessment_attempt_positive"
            ),
        ),
    ]
