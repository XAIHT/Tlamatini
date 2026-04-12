from typing import Optional
from django.contrib.auth.models import User
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from ..models import ContextCache, AgentMessage

def save_context_blob(query_hash: str, context_blob: str):
    """Save the context blob to the database with the given query hash."""
    ContextCache.objects.update_or_create(
        query_hash=query_hash,
        defaults={'context_blob': context_blob}
    )

def load_context_blob(query_hash: str) -> Optional[str]:
    """Retrieve the context blob from the database by query hash, return None if not found."""
    try:
        cache_entry = ContextCache.objects.get(query_hash=query_hash)
        return cache_entry.context_blob
    except ContextCache.DoesNotExist:
        return None

def show_rephrased_question(rephrased_question, conversation_user_id=None):
    if rephrased_question is None or rephrased_question == "" or rephrased_question.strip() == "":
        print("\n--- Rephrased question is None, empty, or whitespace. Skipping...")
        return False
    try:
        if "referenced rephrase:" not in rephrased_question.lower():
            referencedRephrase = "Referenced Rephrase: " + rephrased_question
        else:
            referencedRephrase = rephrased_question

        bot_user, _ = User.objects.get_or_create(username='Tlamatini')
        result = AgentMessage.objects.create(
            user=bot_user,
            conversation_user_id=conversation_user_id,
            message=referencedRephrase
        )
        print(f"\n--- Rephrased question has been saved to DB: {result}")

        try:
            channel_layer = get_channel_layer()
            if channel_layer is not None:
                async_to_sync(channel_layer.group_send)(
                    'chat_llm_chat',
                    {
                        'type': 'agent_message',
                        'message': referencedRephrase,
                        'username': 'Tlamatini'
                    }
                )
        except Exception as e2:
            print(f"\n--- Failed to broadcast rephrased question via Channels: {e2}")
                
        print("\n--- Rephrased question has been sent to the chat.")
        return True
    except Exception as e:
        print(f"\n--- Failed to save rephrased question: {e}")
        return False
