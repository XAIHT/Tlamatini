# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0223_create_superuser_console_handoff"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="RemoteControllerProfile",
            fields=[
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    primary_key=True, serialize=False, to=settings.AUTH_USER_MODEL,
                )),
                ("account", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("adapter", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("enabled", models.BooleanField(default=False)),
                ("binding_id", models.CharField(max_length=32, blank=True, default="")),
            ],
        ),
        migrations.CreateModel(
            name="RemoteControllerRevocation",
            fields=[
                ("binding_id", models.CharField(primary_key=True, max_length=32, serialize=False)),
                ("account", models.UUIDField(editable=False)),
                ("adapter", models.UUIDField(editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
