
import menu.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0008_backfill_product_uuid"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="uuid",
            field=models.CharField(
                max_length=36,
                default=menu.models.generate_uuid_str,
                editable=False,
                unique=True,
            ),
        ),
    ]
