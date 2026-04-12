from django.db import migrations, models
import django.db.models.deletion


def backfill_conversation_user(apps, schema_editor):
    AgentMessage = apps.get_model('agent', 'AgentMessage')

    messages = list(AgentMessage.objects.select_related('user').order_by('timestamp', 'id'))
    last_human_user_id = None

    for message in messages:
        sender_username = getattr(message.user, 'username', '')
        if sender_username != 'Tlamatini':
            last_human_user_id = message.user_id
            owner_user_id = message.user_id
        else:
            owner_user_id = last_human_user_id

        if owner_user_id is not None:
            message.conversation_user_id = owner_user_id
            message.save(update_fields=['conversation_user'])


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0042_add_mouser'),
    ]

    operations = [
        migrations.AddField(
            model_name='agentmessage',
            name='conversation_user',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='agent_messages',
                to='auth.user',
            ),
        ),
        migrations.RunPython(backfill_conversation_user, migrations.RunPython.noop),
    ]
