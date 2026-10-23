# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0219_user_wizard_graphical_notifications"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.CreateModel(
        name="InteractionSettings",
        fields=[
            ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True,
                                        serialize=False, to=settings.AUTH_USER_MODEL)),
            ("preferences", models.JSONField(default=dict)),
            ("revision", models.PositiveIntegerField(default=0)),
        ],
    )]
