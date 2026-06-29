# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
One functional question per WRAPPED chat-agent in Tlamatini.

Source of truth: agent/chat_agent_registry.py :: WRAPPED_CHAT_AGENT_SPECS
(49 wrapped agents as of 2026-06-05). Each question is an OPERATOR prompt
(Multi-Turn ON) that exercises that agent's actual functionality. The
send_email agent additionally carries a second question that exercises the
file-attachment path (email.attachments), so the bank is 50 questions.

Safety choices (this runs for real):
  * file ops act on THROWAWAY files the question first creates, under the app
    Temp dir -- nothing pre-existing is moved/deleted.
  * crypto does a self-contained round-trip (keygen -> cipher -> decipher).
  * external / infra agents (ssh, scp, sql, mongo, docker, k8s, jenkins, email,
    telegram, whatsapp, imap, kali, unreal) target localhost / sanctioned hosts
    or are told to "report the result if it can't connect" -- a graceful failure
    is a valid exercise of the agent's launch + report path. The email
    attachment test points at smtp.example.com (no real delivery) and attaches
    a THROWAWAY file it first creates under the app Temp dir.
  * desktop agents use their least-disruptive real action (windower=list,
    mouser=move-no-click, shoter/camcorder/recorder=capture).
  * firmware agents (stm32er/esp32er/arduiner) use their lightest meta action;
    NOTE they may trigger a one-time toolchain bootstrap download -- they are
    ordered LAST so the rest finish first.

Same dict shape as questions.py so run_test.py can consume either bank.
"""

from typing import List, Dict, Any

REPO = r"C:\Development\Tlamatini"
TEMP = r"C:\Development\Tlamatini\Temp"

# (wrapped key, display, question text, expect-keywords)
# Ordered: compute/IO -> crypto -> observational/desktop -> monitors ->
# external/infra -> firmware (last, may download toolchains).
WRAPPED = [
    # --- compute / IO -----------------------------------------------------
    ("executer", "Executer",
     "Run the shell command: echo Tlamatini wrapped-agent test -- and show me the output.",
     ["tlamatini"]),
    ("pythonxer", "Pythonxer",
     "Run this Python and show the result: print(sum(range(1, 101)))",
     ["5050"]),
    ("gitter", "Gitter",
     f"Run 'git status' in the repository at {REPO} and tell me the current branch and whether the working tree is clean.",
     ["branch"]),
    ("apirer", "Apirer",
     "Call the API https://api.github.com/repos/anthropics/claude-code with method GET and show me the HTTP status and a few fields from the JSON.",
     ["200", "github"]),
    ("prompter", "Prompter",
     "Run a prompt: explain the CAP theorem in distributed systems with a one-line example for each of the three trade-offs.",
     ["cap", "consistency"]),
    ("summarize_text", "Summarize Text",
     "Summarize the following text in about 30 words: 'Tlamatini is a locally-deployed AI developer assistant built with Django, featuring a RAG system, a multi-turn orchestration layer, a visual agentic workflow designer with 74 agent types, an ACPX runtime for external coding CLIs, and a skills system.'",
     ["tlamatini"]),
    ("crawler", "Crawler",
     "Crawl the page https://example.com and give me a short summary of its headings and any links.",
     ["example"]),
    ("file_creator", "File Creator",
     f"Create a file at {TEMP}\\wrapped_test.txt with the content 'Tlamatini wrapped-agent test', then confirm it was written.",
     ["wrapped_test"]),
    ("file_extractor", "File Extractor",
     f"Extract the text from {REPO}\\README.md and show me the first few lines.",
     ["tlamatini"]),
    ("file_interpreter", "File Interpreter",
     f"Read and briefly summarize the file {REPO}\\CLAUDE.md.",
     ["tlamatini"]),
    ("de_compresser", "De-Compresser",
     f"Create a small text file at {TEMP}\\zip_me.txt with some content, compress it into {TEMP}\\zip_me.zip, and confirm the archive was created.",
     ["zip"]),
    ("move_file", "Move File",
     f"Create a file at {TEMP}\\move_src.txt, then move it into the folder {TEMP}\\moved\\ and confirm the move.",
     ["move"]),
    ("deleter", "Deleter",
     f"Create a throwaway file at {TEMP}\\delete_me.txt, then delete it and confirm it no longer exists.",
     ["delete"]),
    ("j_decompiler", "J-Decompiler",
     f"Decompile the Java archive at {TEMP}\\sample.jar. If the file does not exist, report that clearly.",
     ["jar"]),

    # --- cryptography (self-contained round-trips) ------------------------
    ("kyber_keygen", "Kyber Keygen",
     "Generate a CRYSTALS-Kyber key pair using the kyber-768 variant and show me the (base64) public key.",
     ["kyber", "key"]),
    ("kyber_cipher", "Kyber Cipher",
     "Generate a Kyber-768 key pair, then encrypt the text 'secret message' with that public key and show me the ciphertext.",
     ["kyber", "cipher"]),
    ("kyber_deciph", "Kyber Deciph",
     "Generate a Kyber-768 key pair, encrypt the text 'hello quantum world' with the public key, then decrypt it with the private key and confirm the decrypted text matches.",
     ["kyber", "decrypt"]),

    # --- observational / desktop ------------------------------------------
    ("shoter", "Shoter",
     "Take a screenshot of the current screen and save it, then tell me where it was saved.",
     ["screenshot"]),
    ("camcorder", "Camcorder",
     "Take a photo with this system's main webcam (camera index 0) and tell me where the photo was saved.",
     ["camera", "photo"]),
    ("image_interpreter", "Image Interpreter",
     "Take a screenshot of the current screen, then describe what is visible in that screenshot.",
     ["screen"]),
    ("recorder", "Recorder",
     "Record 4 seconds of audio from the default microphone, save it as a WAV file, and tell me where it was saved.",
     ["audio", "wav"]),
    ("whisperer", "Whisperer",
     "Using Whisperer, record from the default microphone and transcribe the speech to text with the local faster-whisper engine. Report the engine, device, status, and the transcript text.",
     ["transcri"]),
    ("audioplayer", "AudioPlayer",
     r"Play the Windows system sound file C:\Windows\Media\chimes.wav through the default speakers. If that file is missing, report it.",
     ["play"]),
    ("videoplayer", "VideoPlayer",
     f"Play the video file at {TEMP}\\sample.mp4 for 5 seconds. If the file does not exist, report that clearly.",
     ["video"]),
    ("windower", "Windower",
     "List all currently open application windows on this system.",
     ["window"]),
    ("mouser", "Mouser",
     "Move the mouse pointer to screen coordinates (300, 300) without clicking, then confirm.",
     ["mouse"]),
    ("keyboarder", "Keyboarder",
     "Using the keyboard, type the text 'tlamatini wrapped test' (do NOT press Enter afterwards).",
     ["type"]),
    ("pser", "PSer",
     "Find the running process whose name looks like 'chrome' and report its details (PID, etc.).",
     ["chrome", "process"]),
    ("notifier", "Notifier",
     "Send me a one-shot notification with the message 'Tlamatini wrapped-agent test completed' and play a sound.",
     ["notif"]),
    ("asker", "Asker",
     "Ask me to choose between path A 'Continue the test' and path B 'Stop the test'.",
     ["choose", "path"]),
    ("sleeper", "Sleeper",
     "Sleep for 5 seconds (5000 ms), then tell me it is done.",
     ["sleep", "done"]),
    ("playwrighter", "Playwrighter",
     "Use Playwrighter to open https://example.com in a browser, extract the page's main heading text, and report it.",
     ["example", "heading"]),

    # --- monitors ---------------------------------------------------------
    ("monitor_log", "Monitor Log",
     f"Check the log file {REPO}\\Tlamatini\\tlamatini.log for the keywords 'ERROR' or 'WARNING' and report what you find.",
     ["log"]),
    ("monitor_netstat", "Monitor Netstat",
     "Check the network connections on port 8000 and report whether anything is LISTENING or ESTABLISHED.",
     ["port", "listen"]),

    # --- external / infra (graceful if unconfigured) ----------------------
    ("dockerer", "Dockerer",
     "Run 'docker ps -a' and list the containers. If Docker isn't running, report that.",
     ["docker"]),
    ("kuberneter", "Kuberneter",
     "Run 'kubectl get nodes'. If no cluster is configured, report the result.",
     ["kube", "node"]),
    ("sqler", "SQLer",
     "Run the SQL query 'SELECT 1 AS ok' against a SQL Server at localhost (database master). If it can't connect, report the connection error.",
     ["sql"]),
    ("mongoxer", "Mongoxer",
     "Run the MongoDB query db.test.find().limit(1) against mongodb://localhost:27017 (database test). If it can't connect, report the error.",
     ["mongo"]),
    ("ssher", "SSHer",
     "SSH into 127.0.0.1 as the current user and run the command 'whoami'. If SSH isn't available, report the connection result.",
     ["ssh"]),
    ("scper", "SCPer",
     f"Use SCP to send the file {REPO}\\README.md to 127.0.0.1 for user 'test'. Report the transfer result (a connection failure is fine to report).",
     ["scp"]),
    ("jenkinser", "Jenkinser",
     "Check the status of the Jenkins job 'build-app' at http://localhost:8080. Report what you find (if Jenkins isn't reachable, say so).",
     ["jenkins"]),
    ("send_email", "Send Email",
     "Send a test email to test@example.com with subject 'Tlamatini wrapped-agent test' and body 'hello' via SMTP host smtp.example.com port 587. This is a connectivity test -- if it can't connect/authenticate, report the error.",
     ["email", "smtp"]),
    ("send_email", "Send Email (with attachment)",
     f"First create a small text file at {TEMP}\\email_attach.txt with the content 'Tlamatini attachment test', then send an email to test@example.com with subject 'Tlamatini attachment test' and body 'See the attached file.' AND attach that file (set email.attachments to that path) via SMTP host smtp.example.com port 587. This is a connectivity test -- if it can't connect/authenticate, report the error, but confirm the file was attached to the message.",
     ["attach", "email", "smtp"]),
    ("recmailer", "Recmailer",
     "Check for received emails containing 'invoice' via IMAP at imap.example.com. If no credentials are configured, report the result.",
     ["imap", "email"]),
    ("telegrammer", "Telegrammer",
     "Send a Telegram message 'Tlamatini test' to @example using Telegrammer. If no official Telegram credentials/cache are configured, report that.",
     ["telegram"]),
    ("whatsapper", "Whatsapper",
     "Send a WhatsApp alert 'Tlamatini test' to +5215555555555 using Meta WhatsApp Cloud API. If no official Meta credentials are configured, report the result.",
     ["whatsapp"]),
    ("kalier", "Kalier",
     "Using Kalier, run the 'health' check against the Kali server at its default URL (http://127.0.0.1:5000) and report whether the MCP-Kali-Server is reachable.",
     ["kali", "health"]),
    ("unrealer", "Unrealer",
     "Send the Unreal Engine command to take a viewport screenshot (or get the current level) via the Unreal MCP at 127.0.0.1:55557. If Unreal isn't connected, report the connection result.",
     ["unreal"]),

    # --- firmware (LAST: may trigger a one-time toolchain bootstrap) ------
    ("stm32er", "STM32er",
     "Using STM32er, run the 'validate' action to check the STM32 toolchain / environment, and report the result.",
     ["stm32"]),
    ("esp32er", "ESP32er",
     "Using ESP32er, run 'system_info' to report the PlatformIO environment status (board/toolchain availability).",
     ["esp32", "platformio"]),
    ("arduiner", "Arduiner",
     "Using Arduiner, run 'system_info' to report the arduino-cli environment status.",
     ["arduino"]),
]


def build_wrapped_questions() -> List[Dict[str, Any]]:
    questions = []
    for i, (key, display, text, expect) in enumerate(WRAPPED, 1):
        questions.append({
            "id": f"W{i:03d}",
            "category": f"wrapped:{key}",
            "key": key,            # wrapped-agent key (e.g. send_email) -- used by --select
            "display": display,    # display name (e.g. Send Email)     -- used by --select
            "text": text,
            "expect": list(expect),
            "min_len": 15,
        })
    return questions


def category_counts(questions):
    counts = {}
    for q in questions:
        counts[q["category"]] = counts.get(q["category"], 0) + 1
    return counts


if __name__ == "__main__":
    qs = build_wrapped_questions()
    print(f"Total wrapped-agent questions: {len(qs)}")
    for q in qs:
        print(f"  {q['id']} {q['category']:24s} {q['text'][:70]}")
