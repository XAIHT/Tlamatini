# Tlamatini — Created by Angela López Mendoza · @angelahack1
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("agent", "0224_remote_controller")]
    operations = [migrations.AddField(
        model_name="agentmessage", name="response_files",
        field=models.JSONField(blank=True, default=list),
    )]
