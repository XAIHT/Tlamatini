# Tlamatini Author Banner — Angela López Mendoza
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0212_compact_state_self_modify"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="UsageDaily",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField()),
                ("model", models.CharField(max_length=255)),
                ("calls", models.PositiveBigIntegerField(default=0)),
                ("input_tokens", models.PositiveBigIntegerField(default=0)),
                ("output_tokens", models.PositiveBigIntegerField(default=0)),
                ("missing_output_calls", models.PositiveBigIntegerField(default=0)),
                ("first_seen", models.DateTimeField()),
                ("last_seen", models.DateTimeField(null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("user", "day", "model"), name="usage_user_day_model")]},
        ),
    ]
