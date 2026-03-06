# Emailer Agent - No LLM, deterministic email notification agent
# This agent monitors log files of source agents for a configurable pattern string
# and sends an email notification when the pattern is detected.
#
# Deployment: When deployed via agentic_control_panel, this agent is copied to
# the pool directory with a cardinal suffix (e.g., emailer_1, emailer_2).
# Source agents should be referenced with their cardinal numbers.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Dict, Optional

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file (e.g., emailer_1 -> emailer_1.log)
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

REANIM_FILE = "reanim.pos"


def get_application_path() -> str:
    """Get the base application path, handling frozen and non-frozen modes."""
    if getattr(sys, 'frozen', False):
        # Frozen mode (PyInstaller): executable directory
        return os.path.dirname(sys.executable)
    else:
        # Development mode: navigate up to find the agent directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check if we're in pool directory
        if 'pool' in current_dir:
            # We're in agents/pool/emailer_X/ -> go up to agents/
            return os.path.dirname(os.path.dirname(current_dir))
        else:
            # We're in agents/emailer/ -> go up to agents/
            return os.path.dirname(current_dir)


def get_pool_path() -> str:
    """
    Get the pool directory path where deployed agents reside.
    Deployed agents with cardinals (e.g., monitor_log_1, emailer_2) are here.
    """
    if getattr(sys, 'frozen', False):
        # Frozen mode: pool is in <exe_dir>/agents/pools/
        return os.path.join(os.path.dirname(sys.executable), 'agents', 'pools')
    else:
        # Development mode
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check if deployed in session: pools/<session_id>/<agent_dir>
        parent = os.path.dirname(current_dir)
        grandparent = os.path.dirname(parent)
        if os.path.basename(grandparent) == 'pools':
            return parent
            
        # Fallback: agents/<agent_name> -> agents/pools
        return os.path.join(os.path.dirname(current_dir), 'pools')


def get_template_agents_path() -> str:
    """
    Get the template agents directory path (non-deployed agents).
    Template agents without cardinals (e.g., monitor_log, emailer) are here.
    """
    if getattr(sys, 'frozen', False):
        # Frozen mode: templates are in <exe_dir>/agents/
        return os.path.join(os.path.dirname(sys.executable), 'agents')
    else:
        # Development mode
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check if deployed in session: pools/<session_id>/<agent_dir>
        parent = os.path.dirname(current_dir)
        grandparent = os.path.dirname(parent)
        if os.path.basename(grandparent) == 'pools':
            # pools/<session>/<agent> -> pools -> agents
            return os.path.dirname(grandparent)
            
        # Fallback: agents/<agent_name> -> agents
        return os.path.dirname(current_dir)


def is_deployed_agent(agent_name: str) -> bool:
    """
    Check if an agent name has a cardinal suffix (is a deployed instance).
    Examples: monitor_log_1 -> True, monitor_log -> False
    """
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2:
        try:
            int(parts[1])  # Check if last part is a number
            return True
        except ValueError:
            return False
    return False


def get_agent_directory(agent_name: str) -> str:
    """
    Get the full path to an agent's directory.
    Deployed agents (with cardinal, e.g., monitor_log_1) are in pool/.
    Template agents (without cardinal, e.g., monitor_log) are in agents/.
    """
    if is_deployed_agent(agent_name):
        # Deployed agent in pool directory
        return os.path.join(get_pool_path(), agent_name)
    else:
        # Template agent in main agents directory
        return os.path.join(get_template_agents_path(), agent_name)


def get_agent_log_path(agent_name: str) -> str:
    """
    Get the log file path for an agent.
    The log file is named after the agent's directory name (with cardinal).
    Examples:
    - monitor_log_1 -> pool/monitor_log_1/monitor_log_1.log
    - monitor_netstat -> agents/monitor_netstat/monitor_netstat.log
    """
    agent_dir = get_agent_directory(agent_name)
    
    # Log file uses the full directory name (including cardinal)
    log_file = os.path.join(agent_dir, f"{agent_name}.log")
    return log_file


def load_config(path: str = "config.yaml") -> Dict:
    """Load configuration from YAML file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"❌ Error: {path} not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"❌ Error parsing {path}: {e}")
        sys.exit(1)


def save_reanim_offsets(offsets: Dict[str, int]):
    """Save file offsets for reanimation after restart."""
    try:
        with open(REANIM_FILE, "w", encoding="utf-8") as f:
            yaml.dump(offsets, f)
    except Exception as e:
        logging.warning(f"⚠️ Warning: Could not save reanimation offsets: {e}")


def load_reanim_offsets() -> Dict[str, int]:
    """Load saved file offsets for reanimation."""
    if not os.path.exists(REANIM_FILE):
        return {}
    try:
        with open(REANIM_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data else {}
    except Exception as e:
        logging.warning(f"⚠️ Warning: Could not load reanimation offsets: {e}")
        return {}


def check_log_for_pattern(log_path: str, offset: int, pattern: str, file_sizes: Dict[str, int]) -> tuple:
    """
    Check a log file for a configurable pattern string starting from offset.
    Smart polling that handles:
    - Log files that don't exist initially (waits for appearance)
    - Log files that are truncated/recreated (resets offset to 0)
    - Log files that decrease in size (treats as new file)
    
    Args:
        log_path: Path to the log file
        offset: Current read offset
        pattern: Pattern string to search for
        file_sizes: Dictionary tracking last known file sizes (modified in-place)
    
    Returns: (pattern_found: bool, new_offset: int, matched_line: str or None)
    """
    last_known_size = file_sizes.get(log_path, -1)  # -1 means never seen
    
    if not os.path.exists(log_path):
        # File doesn't exist - reset tracking and wait
        file_sizes[log_path] = -1  # Mark as "waiting for file"
        return False, 0, None  # Reset offset to 0 to catch content when file appears
    
    try:
        current_size = os.path.getsize(log_path)
        
        # Detect file truncation/recreation scenarios:
        # 1. File size decreased (truncated or recreated with less content)
        # 2. File appeared after being absent (last_known_size was -1)
        # 3. Current offset is beyond file size (stale offset from reanim.pos)
        if current_size < offset or last_known_size == -1 or current_size < last_known_size:
            if last_known_size == -1:
                logging.info(f"📁 Log file appeared: {log_path}")
            elif current_size < last_known_size:
                logging.info(f"🔄 Log file truncated/recreated: {log_path} ({last_known_size} -> {current_size} bytes)")
            else:
                logging.info(f"🔄 Stale offset detected for {log_path}, resetting")
            offset = 0  # Read from beginning
        
        # Update tracking
        file_sizes[log_path] = current_size
        
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            new_content = f.read()
            new_offset = f.tell()
        
        if pattern in new_content:
            # Find the line containing the pattern
            for line in new_content.split('\n'):
                if pattern in line:
                    return True, new_offset, line.strip()
        
        return False, new_offset, None
    
    except Exception as e:
        logging.error(f"Error reading log {log_path}: {e}")
        return False, offset, None


def send_email_smtp(smtp_config: Dict, email_config: Dict, subject: str, body: str, 
                    source_agent: str, matched_line: str, log_path: Optional[str] = None) -> bool:
    """
    Send an email notification via SMTP.
    
    Args:
        smtp_config: SMTP server configuration (host, port, username, password, use_tls, use_ssl, timeout)
        email_config: Email configuration (from_address, to_addresses, cc_addresses, bcc_addresses)
        subject: Email subject
        body: Email body template
        source_agent: Name of the agent that triggered the event
        matched_line: The log line that matched the pattern
        log_path: Optional path to the log file to attach
    
    Returns: True if email sent successfully, False otherwise
    """
    # Import socket here or ensuring it's available for timeout handling
    import socket

    try:
        # Format body with event details
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_body = body.format(
            source_agent=source_agent,
            matched_line=matched_line,
            timestamp=timestamp,
            log_file=log_path or "N/A"
        )
        
        # Format subject with event details
        formatted_subject = subject.format(
            source_agent=source_agent,
            timestamp=timestamp
        )
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = email_config.get('from_address', smtp_config.get('username', ''))
        msg['To'] = ', '.join(email_config.get('to_addresses', []))
        
        cc_addresses = email_config.get('cc_addresses', [])
        if cc_addresses:
            msg['Cc'] = ', '.join(cc_addresses)
        
        msg['Subject'] = formatted_subject
        msg.attach(MIMEText(formatted_body, 'plain', 'utf-8'))
        
        # Attach log file if enabled and exists
        if email_config.get('attach_log', False) and log_path and os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                    log_content = f.read()
                
                attachment = MIMEText(log_content, 'plain', 'utf-8')
                attachment.add_header('Content-Disposition', 'attachment', 
                                    filename=os.path.basename(log_path))
                msg.attach(attachment)
                logging.info(f"📎 Attached log file: {log_path}")
            except Exception as e:
                logging.warning(f"⚠️ Could not attach log file: {e}")
        
        # Build recipient list
        recipients = email_config.get('to_addresses', [])[:]
        recipients.extend(cc_addresses)
        recipients.extend(email_config.get('bcc_addresses', []))
        
        if not recipients:
            logging.error("❌ No recipients configured for email!")
            return False
        
        # Connect and send
        host = smtp_config.get('host', 'localhost')
        port = smtp_config.get('port', 587)
        use_ssl = smtp_config.get('use_ssl', False)
        use_tls = smtp_config.get('use_tls', True)
        timeout = smtp_config.get('timeout', 30) # Default timeout: 30 seconds
        
        logging.info(f"🔌 Connecting to SMTP server {host}:{port} (SSL={use_ssl}, TLS={use_tls}, Timeout={timeout}s)...")
        
        start_time = time.time()
        
        if use_ssl:
            server = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            server = smtplib.SMTP(host, port, timeout=timeout)
            if use_tls:
                logging.info("🔐 Starting TLS...")
                server.starttls()
        
        logging.info("🔗 Connection established. Logging in...")

        # Authenticate if credentials provided
        username = smtp_config.get('username', '')
        password = smtp_config.get('password', '')
        if username and password:
            server.login(username, password)
            logging.info("🔑 Authentication successful.")
        
        logging.info(f"📤 Sending email to {len(recipients)} recipient(s)...")
        
        # Send email
        server.sendmail(msg['From'], recipients, msg.as_string())
        server.quit()
        
        elapsed = time.time() - start_time
        logging.info(f"✉️ Email sent successfully to: {msg['To']} (took {elapsed:.2f}s)")
        return True
    
    except socket.timeout:
        logging.error(f"❌ SMTP Connection Timer Out ({timeout}s exceeded)")
        return False
    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"❌ SMTP Authentication failed: {e}")
        return False
    except smtplib.SMTPConnectError as e:
        logging.error(f"❌ SMTP Connection failed: {e}")
        return False
    except smtplib.SMTPException as e:
        logging.error(f"❌ SMTP Error: {e}")
        return False
    except Exception as e:
        logging.error(f"❌ Failed to send email: {e}")
        return False



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

def main():
    """Main loop for the Emailer agent."""
    config = load_config()
    
    # Write PID file immediately
    write_pid_file()
    
    try:
        # Get configuration sections
        source_agents: List[str] = config.get('source_agents', [])
        pattern: str = config.get('pattern', 'EVENT DETECTED')
        poll_interval: int = config.get('poll_interval', 1)  # Default 1s
        
        # SMTP configuration
        smtp_config: Dict = config.get('smtp', {})
        
        # Email configuration
        email_config: Dict = config.get('email', {})
        
        
        if not source_agents:
            logging.error("❌ No source agents configured. Exiting.")
            sys.exit(1)
        
        if not smtp_config:
            logging.error("❌ No SMTP configuration found. Exiting.")
            sys.exit(1)
        
        if not email_config.get('to_addresses'):
            logging.error("❌ No recipient email addresses configured. Exiting.")
            sys.exit(1)
        
        logging.info("📧 EMAILER AGENT STARTED")
        logging.info(f"📁 Pool path: {get_pool_path()}")
        logging.info(f"📁 Template path: {get_template_agents_path()}")
        logging.info(f"👀 Monitoring source agents: {source_agents}")
        logging.info(f"🔍 Pattern to detect: '{pattern}'")
        logging.info(f"📬 SMTP Server: {smtp_config.get('host', 'N/A')}:{smtp_config.get('port', 'N/A')}")
        logging.info(f"📨 Email recipients: {email_config.get('to_addresses', [])}")
        logging.info(f"⏱️ Poll interval: {poll_interval}s")
        
        # Log resolved paths for debugging
        for source in source_agents:
            log_path = get_agent_log_path(source)
            logging.info(f"   📄 {source} log: {log_path} (exists: {os.path.exists(log_path)})")
        
        logging.info("=" * 60)
        
        
        # Load saved offsets for reanimation
        offsets = load_reanim_offsets()
        
        # Initialize file size tracking for smart polling
        # -1 means file hasn't been seen yet (waiting for appearance)
        file_sizes: Dict[str, int] = {}
        
        # Initialize offsets for new sources
        for source in source_agents:
            if source not in offsets:
                log_path = get_agent_log_path(source)
                if os.path.exists(log_path):
                    # Start from beginning of file to detect patterns that may already exist
                    # This ensures we catch events like "STARTUP COMPLETE" that happen quickly
                    offsets[source] = 0
                    file_sizes[log_path] = os.path.getsize(log_path)
                    logging.info(f"📍 Initialized offset for {source}: {offsets[source]}")
                else:
                    # Log file may not exist yet (source agent hasn't started)
                    # Smart polling will detect when file appears
                    offsets[source] = 0
                    file_sizes[log_path] = -1  # Mark as waiting
        
        while True:
            patterns_detected = []
            
            # Check each source agent's log file
            for source in source_agents:
                log_path = get_agent_log_path(source)
                current_offset = offsets.get(source, 0)
                
                pattern_found, new_offset, matched_line = check_log_for_pattern(
                    log_path, current_offset, pattern, file_sizes
                )
                offsets[source] = new_offset
                
                if pattern_found:
                    logging.info(f"🚨 PATTERN DETECTED from '{source}': {matched_line}")
                    patterns_detected.append({
                        'source': source,
                        'line': matched_line,
                        'log_path': log_path
                    })
            
            # If any patterns detected, send email notification
            if patterns_detected:
                logging.info(f"📢 Pattern detected from {len(patterns_detected)} source(s). Sending email notifications...")
                
                for detection in patterns_detected:
                    logging.info(f"📧 Sending email notification for event from '{detection['source']}'...")
                    
                    success = send_email_smtp(
                        smtp_config=smtp_config,
                        email_config=email_config,
                        subject=email_config.get('subject', '[EMAILER ALERT] Pattern detected from {source_agent}'),
                        body=email_config.get('body', 
                            "Emailer Agent Alert\n\n"
                            "A pattern match was detected:\n\n"
                            "Source Agent: {source_agent}\n"
                            "Matched Line: {matched_line}\n"
                            "Log File: {log_file}\n"
                            "Timestamp: {timestamp}\n"
                        ),
                        source_agent=detection['source'],
                        matched_line=detection['line'],
                        log_path=detection['log_path']
                    )
                    
                    if success:
                        logging.info(f"✅ Email notification sent for '{detection['source']}'")
                    else:
                        logging.error(f"❌ Failed to send email notification for '{detection['source']}'")
                
                logging.info("=" * 60)
            
            # Save offsets for reanimation
            save_reanim_offsets(offsets)
            
            # Wait before next poll
            time.sleep(poll_interval)
    
    except KeyboardInterrupt:
        logging.info("\n⛔ Emailer agent stopped by user.")
    except Exception as e:
        logging.error(f"❌ Emailer agent error: {e}")
        raise
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()


if __name__ == "__main__":
    main()
