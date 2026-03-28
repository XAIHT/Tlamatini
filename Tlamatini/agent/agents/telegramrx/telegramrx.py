import os
import sys
import time
import yaml
import logging
import tempfile

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Logging Setup
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

PID_FILE = "agent.pid"


# -----------------------------------------------------------------
# Config / PID helpers
# -----------------------------------------------------------------

def load_config(path: str = "config.yaml") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Error loading config: {e}")
        return {}


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")


def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception:
            return


# -----------------------------------------------------------------
# Main
# -----------------------------------------------------------------

def main():
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        import whisper
        from telethon import TelegramClient, events
    except Exception as e:
        logging.error(f"Failed to import dependencies: {e}")
        remove_pid_file()
        return

    config = load_config()

    telegram_cfg = config.get('telegram', {})
    api_id = telegram_cfg.get('api_id')
    api_hash = telegram_cfg.get('api_hash')
    listen_chat = telegram_cfg.get('listen_chat', 'me')

    if not api_id or not api_hash:
        logging.error("Telegram api_id or api_hash missing in config.yaml")
        remove_pid_file()
        return

    source_agents = config.get('source_agents', [])
    if isinstance(source_agents, str):
        source_agents = [s.strip() for s in source_agents.split(',') if s.strip()]

    logging.info("TELEGRAMXR AGENT STARTED (Dark-Blue to Black)")
    logging.info(f"Listening on chat: {listen_chat}")
    logging.info(f"Source agents: {source_agents}")
    logging.info("=" * 60)

    # Load local Whisper model for audio transcription
    whisper_model_name = config.get('whisper', {}).get('model', 'base')
    logging.info(f"Loading local Whisper model '{whisper_model_name}' for audio transcription...")
    audio_model = whisper.load_model(whisper_model_name)
    logging.info("Whisper model loaded successfully.")

    # Session file stored next to script
    session_name = os.path.join(script_dir, 'telegramrx_session')
    client = TelegramClient(session_name, api_id, api_hash)

    @client.on(events.NewMessage(chats=listen_chat))
    async def handler(event):
        # Ignore our own acknowledgment messages
        if event.raw_text and event.raw_text.startswith("Message received by Telegramrx"):
            return

        message_text = ""

        # Handle voice messages: download, transcribe with Whisper, then clean up
        if event.message.voice:
            logging.info("Voice message received. Downloading...")
            temp_dir = tempfile.gettempdir()
            file_path = await event.message.download_media(file=temp_dir)

            logging.info("Transcribing audio with Whisper...")
            result = audio_model.transcribe(file_path)
            message_text = result['text']
            logging.info(f"Transcription complete: {message_text}")

            # Clean up the temporary audio file
            try:
                os.remove(file_path)
            except Exception:
                pass

        # Handle text messages
        elif event.raw_text:
            message_text = event.raw_text

        if not message_text.strip():
            return

        # Replace newlines with a single space so the log line stays on one line
        single_line_content = message_text.replace('\n', ' ').replace('\r', ' ')

        # Log the received message in one line
        logging.info(f"===MESAGE RECEIVED: {single_line_content} END OF MESSAGE===")

        # Send acknowledgment
        try:
            await event.reply("Message received by Telegramrx")
            logging.info("Acknowledgment message sent successfully.")
        except Exception as e:
            logging.error(f"Failed to send acknowledgment: {e}")

    # Start client and run until disconnected
    logging.info("Connecting to Telegram...")
    client.start()
    logging.info("Connected. Listening for messages. Press Ctrl+C to stop.")

    try:
        client.run_until_disconnected()
    except KeyboardInterrupt:
        logging.info("Telegramrx agent stopped by user.")
    except Exception as e:
        logging.error(f"Critical Error: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()
        logging.info("Telegramrx Stopped.")


if __name__ == "__main__":
    main()
