import yaml
import os
import tempfile
import whisper
import ollama
from telethon import TelegramClient, events

# 1. Load Configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

api_id = config['telegram']['api_id']
api_hash = config['telegram']['api_hash']
model_name = config['ollama']['model']

# 2. Initialize Telegram Client
# 'local_bridge' will be the name of the session file created in your folder
client = TelegramClient('local_bridge', api_id, api_hash)

# 3. Load Local Audio Transcription Model
print("Loading local Whisper model for audio transcription... (This may take a moment)")
audio_model = whisper.load_model("base") # 'base' is fast. Use 'small' or 'tiny' if needed.

# 4. Listen for new messages ONLY in "Saved Messages" ('me' in Telethon)
@client.on(events.NewMessage(chats='me'))
async def handler(event):
    message_text = ""
    
    # PREVENT INFINITE LOOPS: 
    # Since we are reading and writing to the same chat, we need to ignore the bot's own replies.
    # We will prefix Ollama's answers with "🤖:" and ignore any message starting with it.
    if event.raw_text and event.raw_text.startswith("🤖:"):
        return

    # Handle Audio Messages
    if event.message.voice:
        print("Voice message received. Downloading...")
        temp_dir = tempfile.gettempdir()
        file_path = await event.message.download_media(file=temp_dir)
        
        print("Transcribing audio...")
        result = audio_model.transcribe(file_path)
        message_text = result['text']
        print(f"Transcription: {message_text}")
        
        # Clean up the audio file
        os.remove(file_path)
        
    # Handle Text Messages
    elif event.raw_text:
        message_text = event.raw_text
        print(f"Text message received: {message_text}")

    # Process with Ollama if we have text
    if message_text.strip():
        print(f"Sending prompt to Ollama model '{model_name}'...")
        try:
            response = ollama.chat(model=model_name, messages=[
                {'role': 'user', 'content': message_text}
            ])
            
            ollama_reply = response['message']['content']
            full_reply = f"🤖:\n{ollama_reply}"
            
            # Telegram's maximum message length is 4096 characters
            max_length = 4096
            
            # If the message is longer than the limit, split it into chunks
            if len(full_reply) > max_length:
                print("Response is too long for a single message. Chunking...")
                for i in range(0, len(full_reply), max_length):
                    chunk = full_reply[i:i+max_length]
                    await client.send_message('me', chunk)
            else:
                # If it's under the limit, send it normally
                await client.send_message('me', full_reply)
                
            print("Reply sent to Saved Messages.")
            
        except Exception as e:
            error_msg = f"🤖: Error communicating with Ollama: {str(e)}"
            # Failsafe in case the error message itself is somehow too long
            await client.send_message('me', error_msg[:4096])
            print(error_msg)

# 5. Start the Script
print("Starting Telegram Receiver...")
client.start()
print("Listening for messages in 'Saved Messages'. Press Ctrl+C to stop.")
client.run_until_disconnected()