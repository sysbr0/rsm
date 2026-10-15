
import uuid

from django.db import migrations
from django.db.models import Q


def populate_category_uuids(apps, schema_editor):
    Category = apps.get_model("menu", "Category")
    db_alias = schema_editor.connection.alias

    queryset = Category.objects.using(db_alias)

    used = set(
        queryset.exclude(uuid__isnull=True)
        .exclude(uuid="")
        .values_list("uuid", flat=True)
    )

    for category in queryset.filter(
        Q(uuid__isnull=True) | Q(uuid="")
    ).iterator():
        value = str(uuid.uuid4()).lower()

        while value in used:
            value = str(uuid.uuid4()).lower()

        used.add(value)

        queryset.filter(pk=category.pk).update(uuid=value)


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0004_add_category_uuid_field"),
    ]

    operations = [
        migrations.RunPython(
            populate_category_uuids,
            migrations.RunPython.noop,
        ),
    ]
