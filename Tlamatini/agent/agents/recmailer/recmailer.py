import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import imaplib
import email
from email.header import decode_header
from typing import TypedDict, Literal, List, Any
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START

# --- Logging Setup ---
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()

class FlushingFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
file_handler = FlushingFileHandler(LOG_FILE_PATH, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# --- Configuration ---
def load_config(path="config.yaml"):
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error("❌ Error: config.yaml not found.")
        sys.exit(1)

CONFIG = load_config()

# --- State Definition ---
class RecmailerState(TypedDict):
    messages: List[Any]
    loop_count: int
    emails_processed: int

# --- Email Functions ---
def connect_imap():
    """Connect to IMAP server."""
    imap_config = CONFIG.get('imap', {})
    host = imap_config.get('host', 'imap.gmail.com')
    port = imap_config.get('port', 993)
    user = imap_config.get('username')
    password = imap_config.get('password')
    
    if not user or not password:
        logging.error("❌ IMAP credentials missing in config.")
        return None

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(user, password)
        return mail
    except Exception as e:
        logging.error(f"❌ IMAP Connection failed: {e}")
        return None

def fetch_latest_email(mail):
    """Fetch the latest unread email."""
    try:
        mail.select(CONFIG['imap'].get('folder', 'INBOX'))
        # Search for UNSEEN emails
        status, messages = mail.search(None, 'UNSEEN')
        
        if status != 'OK':
            return None
            
        email_ids = messages[0].split()
        if not email_ids:
            return None
            
        # Get the latest one
        latest_id = email_ids[-1]
        status, msg_data = mail.fetch(latest_id, '(RFC822)')
        
        if status != 'OK':
            return None
            
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                
                # Decode Subject
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                
                # Extract Body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        content_disposition = str(part.get("Content-Disposition"))
                        try:
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode()
                                break # Prioritize plain text
                        except Exception:
                            pass
                else:
                    body = msg.get_payload(decode=True).decode()
                
                return {
                    "subject": subject,
                    "body": body,
                    "sender": msg.get("From")
                }
        return None

    except Exception as e:
        logging.error(f"⚠️ Error fetching email: {e}")
        return None

# --- Graph Nodes ---

def check_email_node(state: RecmailerState):
    """Check for new emails."""
    logging.info("\n--- 📧 CHECKING FOR EMAILS ---")
    
    mail = connect_imap()
    if not mail:
        logging.warning("⚠️ Could not connect to IMAP. Retrying later.")
        time.sleep(5)
        return {"messages": [], "loop_count": state['loop_count'] + 1}
        
    email_data = fetch_latest_email(mail)
    try:
        mail.logout()
    except Exception:
        pass
        
    if not email_data:
        logging.info("📭 No new emails found.")
        interval = CONFIG.get('poll_interval', 10)
        time.sleep(interval)
        return {"messages": [], "loop_count": state['loop_count'] + 1}
        
    logging.info(f"📨 New Email Found:\nSubject: {email_data['subject']}\nSender: {email_data['sender']}")
    
    # Store email content in message for LLM
    content = f"Subject: {email_data['subject']}\nBody: {email_data['body']}\nSender: {email_data['sender']}"
    return {
        "messages": [HumanMessage(content=content)],
        "loop_count": state['loop_count'] + 1
    }

def analyze_email_node(state: RecmailerState):
    """Analyze email content using LLM."""
    messages = state.get('messages', [])
    if not messages:
        return {} # Should not happen if routed correctly
        
    logging.info("\n--- 🤖 ANALYZING EMAIL ---")
    
    try:
        llm = ChatOllama(
            base_url=CONFIG['llm']['base_url'],
            model=CONFIG['llm']['model'],
            temperature=CONFIG['llm']['temperature']
        )
        
        system_prompt = CONFIG.get('system_prompt', "Analyze this email.")
        
        # Prepare dynamic values for prompt
        keywords_list = CONFIG.get('keywords_or_phrases', [])
        # If it's a list, join it; otherwise use as string
        if isinstance(keywords_list, list):
            keywords_str = ", ".join(keywords_list)
        else:
            keywords_str = str(keywords_list)
            
        outcome_word = CONFIG.get('outcome_word', 'PROCESSED')
        
        # Prepare context
        email_content = messages[-1].content
        formatted_prompt = system_prompt.format(
            subject=messages[-1].content.split('\n')[0], # Rough extraction for prompt config
            body=messages[-1].content,
            keywords_or_phrases=keywords_str,
            outcome_word=outcome_word
        )
        
        response = llm.invoke([
            SystemMessage(content=formatted_prompt),
            HumanMessage(content=email_content)
        ])
        
        logging.info(f"\n[LLM ANALYSIS]:\n{response.content}")
        
        return {
            "messages": [], # Clear messages to save memory? Or keep history?
            "emails_processed": state.get('emails_processed', 0) + 1
        }
        
    except Exception as e:
        logging.error(f"❌ LLM Error: {e}")
        return {}

def router(state: RecmailerState) -> Literal["analyze", "loop"]:
    """Decide whether to analyze or loop back."""
    messages = state.get('messages', [])
    if messages and isinstance(messages[-1], HumanMessage):
        return "analyze"
    return "loop"

# --- Workflow Setup ---
workflow = StateGraph(RecmailerState)

workflow.add_node("check_email", check_email_node)
workflow.add_node("analyze_email", analyze_email_node)

workflow.add_edge(START, "check_email")

workflow.add_conditional_edges(
    "check_email",
    router,
    {
        "analyze": "analyze_email",
        "loop": "check_email"
    }
)

workflow.add_edge("analyze_email", "check_email") # Loop back after analysis

app = workflow.compile()

# --- PID & Main ---
PID_FILE = "agent.pid"

def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")

def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"❌ Failed to remove PID file: {e}")
            return

if __name__ == "__main__":
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)
    try:
        logging.info("🚀 RECMAILER AGENT STARTED")
        logging.info(f"📧 Monitoring: {CONFIG.get('imap', {}).get('username', 'Not Configured')}")
        
        initial_state = {
            "messages": [],
            "loop_count": 0,
            "emails_processed": 0
        }
        
        # Run indefinitely
        app.invoke(initial_state, config={"recursion_limit": 100000}) 
        
    except KeyboardInterrupt:
        logging.info("\n⛔ Recmailer agent stopped by user.")
    except Exception as e:
        logging.error(f"\n❌ PROGRAM STOPPED: {e}")
    finally:
        remove_pid_file()
