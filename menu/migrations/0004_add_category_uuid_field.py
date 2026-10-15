
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0003_category_icon"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="uuid",
            field=models.CharField(
                max_length=36,
                null=True,
                blank=True,
                editable=False,
            ),
        ),
    ]
