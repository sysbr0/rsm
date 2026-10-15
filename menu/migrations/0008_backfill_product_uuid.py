
import uuid

from django.db import migrations
from django.db.models import Q


def populate_product_uuids(apps, schema_editor):
    Product = apps.get_model("menu", "Product")
    db_alias = schema_editor.connection.alias

    queryset = Product.objects.using(db_alias)

    used = set(
        queryset.exclude(uuid__isnull=True)
        .exclude(uuid="")
        .values_list("uuid", flat=True)
    )

    for product in queryset.filter(
        Q(uuid__isnull=True) | Q(uuid="")
    ).iterator():
        value = str(uuid.uuid4()).lower()

        while value in used:
            value = str(uuid.uuid4()).lower()

        used.add(value)

        queryset.filter(pk=product.pk).update(uuid=value)


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0007_add_product_uuid_field"),
    ]

    operations = [
        migrations.RunPython(
            populate_product_uuids,
            migrations.RunPython.noop,
        ),
    ]
