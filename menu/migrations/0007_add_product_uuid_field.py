
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0006_finalize_category_uuid"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="uuid",
            field=models.CharField(
                max_length=36,
                null=True,
                blank=True,
                editable=False,
            ),
        ),
    ]
