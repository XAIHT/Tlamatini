from dataclasses import dataclass, field


@dataclass(frozen=True)
class ChatWrappedAgentSpec:
    key: str
    template_dir: str
    tool_name: str
    tool_description: str
    display_name: str
    purpose: str
    example_request: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    security_hints: tuple[str, ...] = field(default_factory=tuple)
    poll_window_seconds: int = 8
    long_running: bool = False


WRAPPED_CHAT_AGENT_SPECS: tuple[ChatWrappedAgentSpec, ...] = (
    ChatWrappedAgentSpec(
        key="crawler",
        template_dir="crawler",
        tool_name="chat_agent_crawler",
        tool_description="Chat-Agent-Crawler",
        display_name="Crawler",
        purpose="Crawl any URL and capture its full page content (HTML, scripts, styles, meta tags) or plain text. Supports JavaScript-rendered SPAs. Use when the user asks to scrape, read, or analyze a web page.",
        example_request="Crawl url='https://example.com' with system_prompt='Extract all links, headings, and a page summary' and content_mode='text'",
        aliases=("crawler", "crawl", "web crawler"),
        security_hints=("crawl", "crawler", "url", "website", "web page", "scrape"),
    ),
    ChatWrappedAgentSpec(
        key="send_email",
        template_dir="emailer",
        tool_name="chat_agent_send_email",
        tool_description="Chat-Agent-Send-Email",
        display_name="Send Email",
        purpose="Send an email via SMTP. Use when the user asks to send, compose, or deliver an email message.",
        example_request="Send email with smtp.host='smtp.gmail.com' and smtp.port=587 and smtp.username='user@gmail.com' and smtp.password='APP_PASSWORD' and email.from_address='user@gmail.com' and email.to_addresses='recipient@example.com' and email.subject='Status Report' and pattern='EVENT DETECTED'",
        aliases=("send_email", "emailer", "email"),
        security_hints=("email", "send email", "smtp", "mail"),
        poll_window_seconds=3,
        long_running=True,
    ),
    ChatWrappedAgentSpec(
        key="executer",
        template_dir="executer",
        tool_name="chat_agent_executer",
        tool_description="Chat-Agent-Executer",
        display_name="Executer",
        purpose="Execute any shell command or program in an isolated subprocess. Use for running scripts, build tools, system commands, or any CLI operation. PREFERRED over chat_agent_keyboarder for running anything: invoke `python script.py`, `gcc`, `npm`, `dotnet`, `git`, etc. directly — never drive Keyboarder to type a command into a terminal window. For creating source files first, pair with chat_agent_file_creator (write the file, then execute it here).",
        example_request="Execute with script='npm run build' and non_blocking=false",
        aliases=("executer", "executor", "execute"),
        security_hints=("execute", "run command", "launch program"),
    ),
    ChatWrappedAgentSpec(
        key="gitter",
        template_dir="gitter",
        tool_name="chat_agent_gitter",
        tool_description="Chat-Agent-Gitter",
        display_name="Gitter",
        purpose="Run any git operation (clone, pull, push, commit, status, log, diff, branch, checkout, merge, etc.). Use when the user asks about git repositories.",
        example_request="Run git with repo_path='E:\\Projects\\myapp' and command='log' and branch='main'",
        aliases=("gitter", "git", "gitter"),
        security_hints=("git", "repository", "branch", "commit", "clone", "pull", "push"),
    ),
    ChatWrappedAgentSpec(
        key="sqler",
        template_dir="sqler",
        tool_name="chat_agent_sqler",
        tool_description="Chat-Agent-SQLer",
        display_name="SQLer",
        purpose="Execute SQL queries against any database (SQLite, PostgreSQL, MySQL, SQL Server). Use when the user asks to query, inspect, or modify database data.",
        example_request="Run SQL with sql_connection.server='localhost' and sql_connection.database='mydatabase' and sql_connection.username='sa' and sql_connection.password='PASSWORD' and script='SELECT name, email FROM users WHERE active=1'",
        aliases=("sqler", "sql", "database"),
        security_hints=("sql", "database", "query", "select", "insert", "update", "delete from"),
    ),
    ChatWrappedAgentSpec(
        key="ssher",
        template_dir="ssher",
        tool_name="chat_agent_ssher",
        tool_description="Chat-Agent-SSHer",
        display_name="SSHer",
        purpose="Execute commands on remote hosts via SSH. Use when the user asks to check, configure, or operate a remote server.",
        example_request="SSH with ip='10.0.0.10' and user='admin' and script='df -h && free -m && uptime'",
        aliases=("ssher", "ssh", "remote shell"),
        security_hints=("ssh", "remote host", "remote command"),
    ),
    ChatWrappedAgentSpec(
        key="scper",
        template_dir="scper",
        tool_name="chat_agent_scper",
        tool_description="Chat-Agent-SCPer",
        display_name="SCPer",
        purpose="Transfer files between local machine and remote hosts via SCP (Secure Copy). Use for uploading or downloading files from remote servers.",
        example_request="Copy file with ip='10.0.0.10' and user='admin' and file='E:\\Backups\\db.sql' and direction='send'",
        aliases=("scper", "scp", "secure copy"),
        security_hints=("scp", "copy file", "transfer file"),
    ),
    ChatWrappedAgentSpec(
        key="pythonxer",
        template_dir="pythonxer",
        tool_name="chat_agent_pythonxer",
        tool_description="Chat-Agent-Pythonxer",
        display_name="Pythonxer",
        purpose="Run inline Python code directly. Use when the user needs a quick computation, data transformation, file parsing, code generation, or any task best solved with Python code. PREFERRED over chat_agent_keyboarder for executing ad-hoc Python: pass the code in `script` and it runs in one shot — never drive Keyboarder to type Python into Notepad, IDLE, or any editor. To author a `.py` file on disk, use chat_agent_file_creator instead (atomic and exact); use Pythonxer to RUN code or to generate computed content.",
        example_request="Run python with script='import json; data = {\"name\": \"test\", \"value\": 42}; print(json.dumps(data, indent=2))'",
        aliases=("pythonxer", "python", "run python"),
        security_hints=("python", "run python", "execute python"),
    ),
    ChatWrappedAgentSpec(
        key="dockerer",
        template_dir="dockerer",
        tool_name="chat_agent_dockerer",
        tool_description="Chat-Agent-Dockerer",
        display_name="Dockerer",
        purpose="Run any Docker CLI command (ps, images, build, run, stop, logs, compose, etc.). Use when the user asks about containers or Docker operations.",
        example_request="Run docker with command='docker ps -a --format table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'",
        aliases=("dockerer", "docker"),
        security_hints=("docker", "container", "image", "compose"),
    ),
    ChatWrappedAgentSpec(
        key="kuberneter",
        template_dir="kuberneter",
        tool_name="chat_agent_kuberneter",
        tool_description="Chat-Agent-Kuberneter",
        display_name="Kuberneter",
        purpose="Run any kubectl command against a Kubernetes cluster. Use when the user asks about pods, deployments, services, namespaces, or any K8s resources.",
        example_request="Run kubectl with command='kubectl get pods -n default -o wide'",
        aliases=("kuberneter", "kubernetes", "kubectl", "k8s"),
        security_hints=("kubectl", "kubernetes", "k8s", "pod", "cluster"),
    ),
    ChatWrappedAgentSpec(
        key="jenkinser",
        template_dir="jenkinser",
        tool_name="chat_agent_jenkinser",
        tool_description="Chat-Agent-Jenkinser",
        display_name="Jenkinser",
        purpose="Trigger Jenkins operations through the Jenkinser template agent.",
        example_request="Run jenkins operation with jenkins_url='http://localhost:8080', job_name='build-app'",
        aliases=("jenkinser", "jenkins"),
        security_hints=("jenkins", "job", "pipeline", "build server"),
    ),
    ChatWrappedAgentSpec(
        key="mongoxer",
        template_dir="mongoxer",
        tool_name="chat_agent_mongoxer",
        tool_description="Chat-Agent-Mongoxer",
        display_name="Mongoxer",
        purpose="Execute MongoDB operations through the Mongoxer template agent.",
        example_request="Run MongoDB operation with mongo_connection.connection_string='mongodb://localhost:27017/' and mongo_connection.database='mydatabase' and script='db.users.find().limit(5)'",
        aliases=("mongoxer", "mongo", "mongodb"),
        security_hints=("mongo", "mongodb", "collection", "document db"),
    ),
    ChatWrappedAgentSpec(
        key="file_creator",
        template_dir="file_creator",
        tool_name="chat_agent_file_creator",
        tool_description="Chat-Agent-File-Creator",
        display_name="File Creator",
        purpose="Create or overwrite a file with specified content at any path. Use when the user asks to create, write, generate, save, or author a file — source code, scripts, configs, JSON, YAML, fixtures, prompt templates, anything. PREFERRED over chat_agent_keyboarder for ALL code / script / text-file authorship: pass the full content in `content` and the file lands on disk atomically — never open Notepad / VS Code / an IDE and type the file through Keyboarder (slow, brittle, mangles quotes/backslashes/indentation, leaves no artefact unless a human saves the editor). For multiple files, call this tool once per file. To then EXECUTE what you wrote, chain into chat_agent_executer (`python file.py`, `node file.js`, ...) or chat_agent_pythonxer.",
        example_request="Create file with filepath='E:\\Temp\\config.yaml' and content='server:\\n  host: 0.0.0.0\\n  port: 8080'",
        aliases=("file_creator", "create file"),
        security_hints=("create file", "write file", "save file"),
    ),
    ChatWrappedAgentSpec(
        key="file_extractor",
        template_dir="file_extractor",
        tool_name="chat_agent_file_extractor",
        tool_description="Chat-Agent-File-Extractor",
        display_name="File Extractor",
        purpose="Extract readable text from any document (PDF, DOCX, XLSX, TXT, CSV, HTML, etc.). Use when the user asks to read or extract content from a document file.",
        example_request="Extract text with path_filenames='E:\\Documents\\report.pdf'",
        aliases=("file_extractor", "extract file"),
        security_hints=("extract file", "read document", "parse file"),
    ),
    ChatWrappedAgentSpec(
        key="file_interpreter",
        template_dir="file_interpreter",
        tool_name="chat_agent_file_interpreter",
        tool_description="Chat-Agent-File-Interpreter",
        display_name="File Interpreter",
        purpose="Interpret and analyze file contents using an LLM. Use when the user asks to understand, summarize, or analyze a document's meaning rather than just extract its text.",
        example_request="Analyze file with path_filenames='E:\\Docs\\contract.pdf' and reading_type='summarized'",
        aliases=("file_interpreter", "interpret file", "analyze file"),
        security_hints=("interpret file", "analyze document", "summarize file"),
    ),
    ChatWrappedAgentSpec(
        key="image_interpreter",
        template_dir="image_interpreter",
        tool_name="chat_agent_image_interpreter",
        tool_description="Chat-Agent-Image-Interpreter",
        display_name="Image Interpreter",
        purpose="Analyze images using vision AI — describe scenes, OCR text, identify objects, read diagrams, interpret screenshots. This is the CANONICAL tool for ANY interpret / describe / analyze / read / OCR / 'what's in this image' request. It reads the pixels server-side and returns a TEXT answer — it does NOT open any viewer window. Use it (or its siblings opus_analyze_image / qwen_analyze_image) whenever the user asks about the CONTENT of an image, photo, picture, screenshot, diagram, or chart. NEVER use launch_view_image for interpretation — that tool only pops a viewer window and produces no analysis; reserve it strictly for explicit 'view / show / open / display the image' requests.",
        example_request="Analyze image with images_pathfilenames='E:\\Screenshots\\error.png' and llm.prompt='Describe what you see and transcribe any visible text or error messages'",
        aliases=("image_interpreter", "interpret image", "analyze image"),
        security_hints=(
            "image", "vision", "screenshot", "photo", "picture",
            "interpret image", "describe image", "analyze image", "analyse image",
            "read image", "ocr", "caption", "transcribe image",
            "what is in the image", "what's in the image",
            "interpret the image", "describe the image", "analyze the image",
        ),
    ),
    ChatWrappedAgentSpec(
        key="summarize_text",
        template_dir="summarizer",
        tool_name="chat_agent_summarize_text",
        tool_description="Chat-Agent-Summarize-Text",
        display_name="Summarize Text",
        purpose="Summarize a block of text in one shot using an LLM. Pass the verbatim text in `input_text` (required). Optionally set `target_words` to ask for a specific length, or override `system_prompt` to control tone/format. Use when the user has a large block of text and wants a concise summary, key points, or executive overview.",
        example_request="Summarize with input_text='<the full text to summarize>' and target_words=40",
        aliases=("summarize_text", "summarizer", "summarize"),
        security_hints=("summarize", "summary", "condense text"),
    ),
    ChatWrappedAgentSpec(
        key="pser",
        template_dir="pser",
        tool_name="chat_agent_pser",
        tool_description="Chat-Agent-PSer",
        display_name="PSer",
        purpose="Find a running process by fuzzy/semantic name (LLM picks the best-matching process from the live process list). Use when the user wants to locate a specific program that may already be running. NOT a PowerShell executor — use chat_agent_executer for shell commands.",
        example_request="Find process with likely_process_name='Paint'",
        aliases=("pser", "process-finder", "find-process"),
        security_hints=("process", "find process", "running process", "pid"),
    ),
    ChatWrappedAgentSpec(
        key="notifier",
        template_dir="notifier",
        tool_name="chat_agent_notifier",
        tool_description="Chat-Agent-Notifier",
        display_name="Notifier",
        purpose="Show a desktop notification with optional sound alert. Use when the user asks to be notified or alerted about something.",
        example_request="Notify with target.mode='oneshot' and target.search_strings='BUILD DONE' and target.outcome_detail='The build finished successfully' and target.sound_enabled=true",
        aliases=("notifier", "notification", "notify"),
        security_hints=("notification", "notify", "desktop alert"),
    ),
    ChatWrappedAgentSpec(
        key="asker",
        template_dir="asker",
        tool_name="chat_agent_asker",
        tool_description="Chat-Agent-Asker",
        display_name="Asker",
        purpose="Pause execution and show the user an interactive A/B choice dialog. Use when the user must pick between two paths before continuing (e.g., 'reboot now or later', 'apply hotfix or escalate').",
        example_request="Ask user with legend_path_a='Reboot now' and legend_path_b='Reboot later'",
        aliases=("asker", "ask user", "choose path"),
        security_hints=("ask user", "choose", "a or b", "decision"),
        long_running=True,
        poll_window_seconds=300,
    ),
    ChatWrappedAgentSpec(
        key="shoter",
        template_dir="shoter",
        tool_name="chat_agent_shoter",
        tool_description="Chat-Agent-Shoter",
        display_name="Shoter",
        purpose="Take a silent screenshot of the current screen and save it to disk — the file is NEVER opened in a viewer (no popup, no focus stolen). The wrapped result includes a top-level 'output_path' field with the absolute path of the saved PNG, so you do NOT need to parse the log to find it. Use when the user asks for a screenshot, screen capture, or visual snapshot of what's on screen, OR as a final verification step at the end of a desktop-UI workflow (after closing the target window) to confirm the desktop is back to its baseline state. DO NOT use it as an 'is the window open?' gate between launching an app and the first Keyboarder/Mouser action — `chat_agent_executer` returning exit_code=0 already proves the launch succeeded; for an explicit yes/no window check, use `chat_agent_window_present` (it's <100 ms) instead of pairing Shoter with the 20–30 s `chat_agent_image_interpreter` vision call. Reserve `chat_agent_image_interpreter` for genuine vision tasks (reading content, OCR, describing a chart) — never for binary 'is X visible?' checks. NEVER follow chat_agent_shoter with launch_view_image — that would pop a viewer window and steal focus from the workflow's target app (e.g. Notepad), breaking subsequent chat_agent_keyboarder / chat_agent_mouser steps.",
        example_request="Take screenshot with output_dir='E:\\Screenshots'",
        aliases=("shoter", "screenshot", "screen capture"),
        security_hints=(
            "screenshot", "screen capture", "take screenshot",
            "snapshot", "capture screen", "visual snapshot",
            "verify it is opened", "verify the window", "confirm visually",
        ),
    ),
    ChatWrappedAgentSpec(
        key="mouser",
        template_dir="mouser",
        tool_name="chat_agent_mouser",
        tool_description="Chat-Agent-Mouser",
        display_name="Mouser",
        purpose=(
            "Move the mouse pointer and click anywhere on the desktop — the canonical "
            "primitive for focusing a window, clicking a button, dragging a selection, or "
            "scrolling. **DO NOT use this tool as part of a code-authoring or script-creation "
            "flow (e.g., clicking through an IDE menu to insert/save code) — `chat_agent_file_creator` "
            "writes the file directly, `chat_agent_executer` runs the command, and `chat_agent_pythonxer` "
            "runs inline Python; none of those need pointer events.** Mouser is reserved for genuine "
            "desktop-UI automation and may be used ONLY when (a) the user EXPLICITLY asks for mouse / "
            "pointer / click automation, (b) the user EXPLICITLY asks for a desktop-UI demo, or (c) "
            "there is genuinely no programmatic alternative. Seven movement_type modes (pick the one "
            "that matches the task, do NOT default to 'localized' when a smarter mode exists):\n"
            "  • 'click_at_window' (PREFERRED for focus-the-window-then-type) — set "
            "    window_title='Notepad' (or any substring of the title) and window_anchor "
            "    ∈ {center|topleft|topright|bottomleft|bottomright|titlebar} (default "
            "    'center'); the agent looks the window up via pyautogui.getWindowsWithTitle, "
            "    moves to the anchor and fires button_click. Bullet-proof and locale-independent "
            "    — NO screenshot / vision LLM needed.\n"
            "  • 'locate_image' — set locate_image_path='C:\\path\\to\\button.png' (and "
            "    optionally locate_confidence ∈ [0.5, 1.0], default 0.8); the agent runs "
            "    pyautogui.locateCenterOnScreen on the live desktop and clicks the center of "
            "    the first match. Use when you have a reference image of the exact button/icon.\n"
            "  • 'localized' — pre-computed (end_posx, end_posy); set actual_position=false "
            "    plus ini_posx/ini_posy to start from a fixed point instead of the current "
            "    cursor. Use when you already have pixel coordinates (e.g. parsed out of an "
            "    Image-Interpreter answer).\n"
            "  • 'click' — click at the CURRENT pointer position (no move). Useful as the "
            "    second step of a chain after another tool moved the cursor.\n"
            "  • 'drag' — drag from (ini_posx, ini_posy) to (end_posx, end_posy) holding "
            "    button_click (defaults to left for 'none'). Use for selections, sliders, "
            "    drag-and-drop.\n"
            "  • 'scroll' — roll the wheel scroll_amount clicks at the current pointer "
            "    position (positive = up, negative = down).\n"
            "  • 'random' — wander randomly for total_time seconds (no click).\n"
            "button_click ∈ {none|left|right|middle|double-left|double-right|double-middle} "
            "for any mode that fires a click.\n\n"
            "RESULT FIELDS (promoted to top-level keys on the wrapped tool's JSON return): "
            "movement_type, end_posx, end_posy, button_click, clicked (true/false), "
            "located_via ∈ {manual|window_title|locate_image|current_position|random|no_match|"
            "platform_unsupported|no_image_file|no_window_title}. When located_via='no_match' "
            "the target wasn't found — adjust the title/image/confidence and retry once.\n\n"
            "Pair with chat_agent_executer (launch app), chat_agent_keyboarder (type after "
            "clicking), and — only when no window title is known and no reference image exists "
            "— chat_agent_shoter + chat_agent_image_interpreter to extract (x, y) coordinates. "
            "For CLOSING a window, prefer chat_agent_keyboarder('alt+f4') over hunting the X "
            "button by pixel; only use Mouser on 'Don't Save'/'Cancel' if alt-letter shortcuts "
            "(alt+n/alt+s/alt+c) are unavailable."
        ),
        example_request="Click Notepad's editing area with movement_type='click_at_window' and window_title='Notepad' and window_anchor='center' and button_click='left'",
        aliases=("mouser", "mouse", "move mouse", "click", "pointer", "drag", "scroll", "click into window", "click the control"),
        security_hints=(
            "mouse", "move mouse", "move the mouse", "mouse pointer",
            "click", "click on", "left click", "right click", "double click",
            "double-click", "middle click", "triple click",
            "focus window", "focus the window", "focus notepad",
            "click into", "click in", "click the window", "click the button",
            "click on the button", "click save", "click ok", "click cancel",
            "click yes", "click no", "click submit", "click apply",
            "press the button on screen", "tap the button",
            "point to", "move pointer", "move the cursor", "move the pointer",
            "drag", "drag and drop", "drag from", "drag to",
            "scroll", "scroll up", "scroll down", "scroll wheel",
            "locate the button", "locate image", "find the button on screen",
            "click where", "click at", "click center", "click top-right",
        ),
    ),
    ChatWrappedAgentSpec(
        key="windower",
        template_dir="windower",
        tool_name="chat_agent_windower",
        tool_description="Chat-Agent-Windower",
        display_name="Windower",
        purpose=(
            "Manage an application WINDOW by its title — the window manager of the "
            "desktop-UI trio (Windower=the window itself, Mouser=clicks inside it, "
            "Keyboarder=typing into it). Use this — NOT chat_agent_mouser — whenever "
            "the goal is the window as a whole: bring it to the front / focus it, "
            "minimize, maximize, restore, move, resize, close it by title, pin it "
            "always-on-top, tile/snap it to a screen edge, OR list every open window "
            "with its position and size. Mouser is only for clicking a control INSIDE "
            "a window; reach for Windower when no clicking is involved.\n\n"
            "Set action ∈ {list | focus | minimize | maximize | restore | move | "
            "resize | move_resize | close | topmost | untopmost | arrange} and "
            "window_title='<title or substring>' (window_title is optional ONLY for "
            "action='list', which enumerates every window). Tune matching with "
            "match_mode ∈ {substring|exact|regex} and match_index (0-based, when "
            "several windows share a title). Geometry: move uses pos_x/pos_y; resize "
            "uses width/height; move_resize uses all four; arrange uses arrange_mode "
            "∈ {left|right|top|bottom|top-left|top-right|bottom-left|bottom-right|"
            "center|full}. activate_after=true (default) raises the window after a "
            "geometry op. Set fail_if_absent=true to hard-fail when no window matches "
            "(so an upstream gate / Forker can branch on it).\n\n"
            "RESULT FIELDS (promoted to top-level keys on the wrapped tool's JSON "
            "return): action, window_title, matched (true/false), match_count, state "
            "∈ {normal|minimized|maximized|hidden|no_match|no_window_title|"
            "win32_unavailable}, left, top, width, height. When matched='false' the "
            "window was not found — adjust window_title/match_mode and retry once.\n\n"
            "Pair with chat_agent_executer (launch the app first), chat_agent_window_present "
            "(confirm it is up), chat_agent_keyboarder (type after focusing), and "
            "chat_agent_mouser (click a specific control). Canonical desktop flow: "
            "launch app → window_present → Windower(action='focus' or 'maximize') → "
            "Keyboarder → ... → Windower(action='close') or Keyboarder('alt+f4')."
        ),
        example_request="Manage window with action='maximize' and window_title='Notepad' and activate_after=true",
        aliases=(
            "windower", "window", "windows", "manage window", "window manager",
            "focus window", "resize window", "maximize window", "minimize window",
            "move window", "close window", "arrange windows", "tile window",
        ),
        security_hints=(
            "window", "the window", "manage window", "window manager",
            "bring to front", "bring the window to front", "bring window to the front",
            "focus the window", "focus window", "raise the window", "raise window",
            "switch to the window", "activate the window", "foreground window",
            "maximize", "maximize the window", "maximise the window", "maximize window",
            "minimize", "minimize the window", "minimise the window", "minimize window",
            "restore the window", "restore window", "unminimize",
            "resize the window", "resize window", "make the window bigger",
            "make the window smaller", "set the window size", "set window size",
            "move the window", "move window", "reposition the window",
            "close the window", "close window", "close by title", "close it by title",
            "always on top", "always-on-top", "pin the window", "keep on top",
            "tile the window", "tile windows", "snap the window", "snap to the left",
            "snap to the right", "arrange windows", "arrange the windows",
            "left half", "right half", "split screen the window",
            "list windows", "list the windows", "list open windows",
            "which windows are open", "what windows are open", "enumerate windows",
            "show me the open windows", "open windows",
        ),
    ),
    ChatWrappedAgentSpec(
        key="keyboarder",
        template_dir="keyboarder",
        tool_name="chat_agent_keyboarder",
        tool_description="Chat-Agent-Keyboarder",
        display_name="Keyboarder",
        purpose="Simulate keyboard input against the active foreground window — type literal text and/or fire key sequences (modifiers, hotkeys, navigation keys). **DO NOT use this tool to author source code, scripts, configuration files, or any file content by typing into Notepad / VS Code / an IDE / a terminal — use `chat_agent_file_creator` (write the file atomically), `chat_agent_executer` (run a command), or `chat_agent_pythonxer` (run inline Python) instead.** Keyboarder is reserved for genuine desktop-UI automation and may be used ONLY when one of these is true: (a) the user EXPLICITLY names Keyboarder / asks for keyboard typing / a Notepad demo / a GUI replay; (b) the user EXPLICITLY asks for a desktop-UI demonstration (hotkey to a third-party app, screencast-style replay, focus-and-type drill); or (c) there is genuinely NO programmatic alternative on this host. Absent that explicit instruction, prefer the file-creator / executer / pythonxer path. Pair with chat_agent_executer (to launch the target app). INPUT_SEQUENCE FORMAT (READ CAREFULLY): comma-separated tokens; literal text MUST be wrapped in single quotes ('like this'); key names go bare (enter, esc, tab); chord keys join with + (ctrl+s, alt+f4). To embed an apostrophe inside single-quoted literal text, double it SQL-style ('I''m' types I'm) OR backslash-escape it ('I\\'m' types I'm). DO NOT double the OUTER quotes (''text'' is wrong). Correct examples: 'Hi, I''m Tlamatini', enter — types `Hi, I'm Tlamatini` then presses Enter. 'Hello world', tab, ctrl+s — types `Hello world` then Tab then saves. If you forget the quotes around text, the agent falls back to typing the entire input literally — but quoting is the canonical form. WINDOW CLEANUP — every desktop-UI workflow you start MUST end by closing the window you opened: send 'alt+f4' to close the active window; if the app raises a 'Save changes?' confirmation (Notepad, Word, most editors) the standard English buttons are 'Save' (alt+s), 'Don't Save' (alt+n), 'Cancel' (alt+c or escape) — when the workflow only typed demo text and the file does NOT need to be kept, send 'alt+n' to discard. If alt-letter shortcuts are unavailable (non-English UI, custom dialog), navigate with 'tab' until the desired button is focused, then 'enter'.",
        example_request="Type with input_sequence=\"'Hi!, I''m Tlamatini', enter\" and stride_delay=80",
        aliases=("keyboarder", "keyboard", "type", "press keys", "send keys", "hotkey"),
        security_hints=(
            "keyboard", "keystrokes", "type into", "type text", "type the text",
            "press key", "press keys", "hotkey", "shortcut", "send keys",
            "simulate keyboard", "simulate typing", "as if typing",
            "if I were typing", "write into notepad", "type in notepad",
            "ctrl+c", "ctrl+v", "alt+tab", "win+r", "enter key",
            "close window", "close the window", "close notepad", "close the app",
            "alt+f4", "dismiss dialog", "dismiss the dialog", "don't save",
            "discard changes", "discard the file", "save dialog", "save prompt",
            "clean up the window", "shut the window", "exit the app",
        ),
    ),
    ChatWrappedAgentSpec(
        key="telegramer",
        template_dir="telegramer",
        tool_name="chat_agent_telegramer",
        tool_description="Chat-Agent-Telegramer",
        display_name="Telegramer",
        purpose="Send Telegram messages through the Telegramer template agent.",
        example_request="Send Telegram message with telegram.api_id=123456, telegram.api_hash='hash', telegram.chat_id='Angela-Bennet', telegram.message='Hello from chat'",
        aliases=("telegramer", "telegram"),
        security_hints=("telegram", "telegram message", "send telegram"),
    ),
    ChatWrappedAgentSpec(
        key="whatsapper",
        template_dir="whatsapper",
        tool_name="chat_agent_whatsapper",
        tool_description="Chat-Agent-Whatsapper",
        display_name="Whatsapper",
        purpose="Send WhatsApp messages through the Whatsapper template agent.",
        example_request="Send WhatsApp alert with textmebot.phone='+5215555555555' and textmebot.apikey='YOUR_TEXTMEBOT_KEY' and keywords='error, critical' and poll_interval=5",
        aliases=("whatsapper", "whatsapp"),
        security_hints=("whatsapp", "send whatsapp", "chat message"),
    ),
    ChatWrappedAgentSpec(
        key="apirer",
        template_dir="apirer",
        tool_name="chat_agent_apirer",
        tool_description="Chat-Agent-Apirer",
        display_name="Apirer",
        purpose="Call any HTTP REST API endpoint (GET, POST, PUT, DELETE, PATCH). Use when the user asks to call an API, fetch data from a URL, or interact with a web service.",
        example_request="Call API with url='https://api.github.com/repos/anthropics/claude-code' and method='GET' and expected_status=200 and timeout=30",
        aliases=("apirer", "api", "http api"),
        security_hints=("api", "http request", "rest", "endpoint"),
    ),
    ChatWrappedAgentSpec(
        key="prompter",
        template_dir="prompter",
        tool_name="chat_agent_prompter",
        tool_description="Chat-Agent-Prompter",
        display_name="Prompter",
        purpose="Send a prompt to another LLM instance for processing. Use for sub-queries, creative writing, code generation, translation, or any task best delegated to a separate LLM call.",
        example_request="Run prompt with prompt='Explain the CAP theorem in distributed systems with a practical example for each trade-off'",
        aliases=("prompter", "sub prompt", "llm prompt"),
        security_hints=("prompt another llm", "sub prompt", "llm prompt"),
    ),
    ChatWrappedAgentSpec(
        key="monitor_log",
        template_dir="monitor_log",
        tool_name="chat_agent_monitor_log",
        tool_description="Chat-Agent-Monitor-Log",
        display_name="Monitor Log",
        purpose="Monitor log files continuously through the Monitor Log template agent.",
        example_request="Monitor log with target.logfile_path='E:\\Temp\\app.log' and target.keywords='ERROR,FATAL'",
        aliases=("monitor_log", "log monitor", "monitor log"),
        security_hints=("monitor log", "watch log", "tail log"),
        poll_window_seconds=3,
        long_running=True,
    ),
    ChatWrappedAgentSpec(
        key="monitor_netstat",
        template_dir="monitor_netstat",
        tool_name="chat_agent_monitor_netstat",
        tool_description="Chat-Agent-Monitor-Netstat",
        display_name="Monitor Netstat",
        purpose="Monitor network connections continuously through the Monitor Netstat template agent.",
        example_request="Monitor netstat with target.port='8080' and target.keywords='ESTABLISHED,LISTENING'",
        aliases=("monitor_netstat", "netstat monitor", "monitor network"),
        security_hints=("netstat", "port status", "monitor network", "listen port"),
        poll_window_seconds=3,
        long_running=True,
    ),
    ChatWrappedAgentSpec(
        key="kyber_keygen",
        template_dir="kyber_keygen",
        tool_name="chat_agent_kyber_keygen",
        tool_description="Chat-Agent-Kyber-Keygen",
        display_name="Kyber Keygen",
        purpose="Generate Kyber keys through the Kyber Keygen template agent.",
        example_request="Generate Kyber keys with kyber_variant='kyber-768'",
        aliases=("kyber_keygen", "kyber keygen", "key generation"),
        security_hints=("kyber", "keygen", "generate keys", "pqc"),
    ),
    ChatWrappedAgentSpec(
        key="kyber_cipher",
        template_dir="kyber_cipher",
        tool_name="chat_agent_kyber_cipher",
        tool_description="Chat-Agent-Kyber-Cipher",
        display_name="Kyber Cipher",
        purpose="Encrypt data through the Kyber Cipher template agent.",
        example_request="Encrypt data with kyber_variant='kyber-768' and public_key='<base64-public-key>' and buffer='secret text'",
        aliases=("kyber_cipher", "encrypt", "kyber encrypt"),
        security_hints=("encrypt", "encryption", "cipher", "kyber"),
    ),
    ChatWrappedAgentSpec(
        key="kyber_deciph",
        template_dir="kyber_decipher",
        tool_name="chat_agent_kyber_deciph",
        tool_description="Chat-Agent-Kyber-Deciph",
        display_name="Kyber Deciph",
        purpose="Decrypt data through the Kyber Decipher template agent.",
        example_request="Decrypt data with kyber_variant='kyber-768' and private_key='<base64-private-key>' and encapsulation='<base64-encapsulation>' and initialization_vector='<base64-iv>' and cipher_text='<base64-ciphertext>'",
        aliases=("kyber_deciph", "kyber_decipher", "decrypt", "kyber decrypt"),
        security_hints=("decrypt", "decryption", "decipher", "kyber"),
    ),
    ChatWrappedAgentSpec(
        key="move_file",
        template_dir="mover",
        tool_name="chat_agent_move_file",
        tool_description="Chat-Agent-Move-File",
        display_name="Move File",
        purpose="Move or rename files through the Mover template agent.",
        example_request="Move file with source_files='E:\\Temp\\old.txt' and destination_folder='E:\\Archive' and operation='move' and trigger_mode='immediate'",
        aliases=("move_file", "mover", "move file", "rename file"),
        security_hints=("move file", "rename file", "relocate file"),
    ),
    ChatWrappedAgentSpec(
        key="deleter",
        template_dir="deleter",
        tool_name="chat_agent_deleter",
        tool_description="Chat-Agent-Deleter",
        display_name="Deleter",
        purpose="Delete files through the Deleter template agent.",
        example_request="Delete file with files_to_delete='E:\\Temp\\obsolete.txt' and trigger_mode='immediate'",
        aliases=("deleter", "delete file", "remove file"),
        security_hints=("delete file", "remove file", "erase file"),
    ),
    ChatWrappedAgentSpec(
        key="recmailer",
        template_dir="recmailer",
        tool_name="chat_agent_recmailer",
        tool_description="Chat-Agent-Recmailer",
        display_name="Recmailer",
        purpose="Check received emails through the Recmailer template agent.",
        example_request="Check received emails with imap.host='imap.gmail.com' and imap.port=993 and imap.username='user@example.com' and imap.password='APP_PASSWORD' and keywords_or_phrases='invoice, receipt'",
        aliases=("recmailer", "receive email", "check mailbox"),
        security_hints=("receive email", "mailbox", "imap", "read email"),
        poll_window_seconds=3,
        long_running=True,
    ),
    ChatWrappedAgentSpec(
        key="j_decompiler",
        template_dir="j_decompiler",
        tool_name="chat_agent_j_decompiler",
        tool_description="Chat-Agent-J-Decompiler",
        display_name="J-Decompiler",
        purpose=(
            "Bulk-decompile every .class, .jar, .war, or .ear file under a directory using the "
            "bundled jd-cli — the canvas-workflow counterpart of the single-file `decompile_java` "
            "direct tool. Use this when the user wants to decompile MANY files at once, when "
            "wildcard patterns are involved (e.g. `*.jar,*.war`), or when recursive subdirectory "
            "scanning is required. The `directory` parameter accepts either a bare folder path "
            "(defaults to `*.class,*.jar,*.war,*.ear`) or a path-with-embedded-wildcards form "
            "`<base>\\\\<patterns>` where patterns are comma-separated (e.g. "
            "`C:\\\\Temp\\\\*.jar,*.war`). When `recursive=true` the wildcards apply at every "
            "depth under `<base>`. Decompiled output for archives lands in a sibling directory "
            "named after the archive; .class files emit their .java beside the .class. Prefer "
            "this wrapped agent for batch / directory work; prefer the direct `decompile_java` "
            "tool when the user explicitly names ONE jar/war file."
        ),
        example_request=(
            "Decompile java with directory='C:\\\\Temp\\\\*.class,*.jar,*.war,*.ear' "
            "and recursive=true"
        ),
        aliases=("j_decompiler", "jdecompiler", "j-decompiler", "decompile-batch"),
        security_hints=(
            "decompile", "decompile java", "decompile jar", "decompile war",
            "decompile class", "batch decompile", "jd-cli", "jar files",
            "war files", "ear files", ".class files", "java decompiler",
            "decompile directory", "decompile folder",
        ),
    ),
    ChatWrappedAgentSpec(
        key="de_compresser",
        template_dir="de_compresser",
        tool_name="chat_agent_de_compresser",
        tool_description="Chat-Agent-De-Compresser",
        display_name="De-Compresser",
        purpose=(
            "Deterministic archive worker that either DECOMPRESSES an archive into a "
            "directory or COMPRESSES a file/directory into an archive. The direction is "
            "inferred from the extensions: if `input` ends in .gz / .7z / .zip / .tar.gz "
            "/ .gz.tar the agent decompresses into the `output` directory; if `output` "
            "ends in those extensions the agent compresses `input` into `output`. "
            "Supports .gz (GNU Zip — single-file), .zip (universal), .7z (LZMA/LZMA2 "
            "via the 7z CLI), and .tar.gz / .gz.tar (gzipped tar via a temp .tar). "
            "Password handling: pass `passwordless=true` to skip passwords; pass "
            "`passwordless=false` and the agent reads the password from the OS "
            "environment variable DE_COMPRESSER_PWD (the user must export it before "
            "starting Tlamatini — if undefined the agent fails fast and still triggers "
            "any downstream `target_agents`). Use this whenever the user asks to "
            "compress, decompress, unzip, extract, zip up, archive, or pack a file or "
            "a folder. Prefer this over `chat_agent_executer` invoking tar/zip CLIs."
        ),
        example_request=(
            "Decompress archive with input='E:\\\\Drops\\\\backup.zip' "
            "and output='E:\\\\Restored' and passwordless=true"
        ),
        aliases=(
            "de_compresser", "decompresser", "de-compresser",
            "compressor", "decompressor", "archiver", "zipper",
            "unzipper", "tarball", "archive_helper",
        ),
        security_hints=(
            "decompress", "compress", "unzip", "extract archive",
            "zip up", "pack folder", "tar gz", "gzip", "7z",
            "create archive", "extract zip", "extract 7z", "extract tar",
            "decompresser", "de-compresser", "decompressor",
        ),
    ),
    ChatWrappedAgentSpec(
        key="unrealer",
        template_dir="unrealer",
        tool_name="chat_agent_unrealer",
        tool_description="Chat-Agent-Unrealer",
        display_name="Unrealer",
        purpose=(
            "Drive Unreal Engine (UE5) via the Unreal MCP plugin's TCP socket protocol "
            "(127.0.0.1:55557 by default — the plugin must already be running inside a UE5 "
            "editor instance; this agent does NOT start the engine). Sends one JSON command "
            "per call: {\"type\": <command>, \"params\": {...}}. Supports the full 28-command "
            "Unreal MCP surface across five categories: "
            "(1) editor — get_actors_in_level, find_actors_by_name, spawn_actor, delete_actor, "
            "set_actor_transform, get_actor_properties, set_actor_property, spawn_blueprint_actor; "
            "(2) blueprint — create_blueprint, add_component_to_blueprint, set_static_mesh_properties, "
            "set_component_property, set_physics_properties, compile_blueprint, set_blueprint_property; "
            "(3) node — add_blueprint_event_node, add_blueprint_input_action_node, "
            "add_blueprint_function_node, connect_blueprint_nodes, add_blueprint_variable, "
            "add_blueprint_get_self_component_reference, add_blueprint_self_reference; "
            "(4) project — create_input_mapping; "
            "(5) umg — create_umg_widget_blueprint, add_text_block_to_widget, add_button_to_widget, "
            "bind_widget_event, add_widget_to_viewport, set_text_block_binding. "
            "Use when the user asks to manipulate the Unreal Editor — spawn or move actors, create "
            "or edit Blueprints, wire Blueprint event/function nodes, add UMG widgets to the "
            "viewport, configure input mappings, or read level state. For multi-step UE5 workflows "
            "(create Blueprint → add components → compile → spawn instance) call this tool once "
            "per step. The wrapped agent emits an INI_SECTION_UNREALER block so the full Unreal "
            "response JSON is captured in the run log and is consumable by Parametrizer downstream. "
            "Override host/port with host='10.0.0.5' and port=55557 to target a remote UE instance."
        ),
        example_request=(
            "Run Unreal command with command='spawn_actor' and params.name='MyCube' "
            "and params.type='StaticMeshActor' and params.location=[0,0,100]"
        ),
        aliases=("unrealer", "unreal", "unreal engine", "ue5", "ue", "unreal_mcp"),
        security_hints=(
            "unreal", "unreal engine", "ue5", "ue", "unreal mcp",
            "spawn actor", "delete actor", "blueprint", "create blueprint",
            "compile blueprint", "umg", "widget blueprint", "viewport",
            "actors in level", "level editor", "static mesh", "pawn",
            "input mapping", "blueprint variable", "blueprint event",
        ),
    ),
    ChatWrappedAgentSpec(
        key="sleeper",
        template_dir="sleeper",
        tool_name="chat_agent_sleeper",
        tool_description="Chat-Agent-Sleeper",
        display_name="Sleeper",
        purpose="Sleep for a deterministic number of milliseconds and then return — the canonical 'wait N seconds' helper for desktop-UI flows. Use whenever the user says 'wait', 'pause', 'hold for', 'sleep' between two actions in a chained workflow (e.g. 'open notepad, type X, wait 30 seconds, close it'). Pass duration_ms in milliseconds (30 seconds = 30000). Do NOT spin chat_agent_pythonxer for time.sleep, do NOT use chat_agent_executer with `timeout /t` — both are slower, larger blast radius, and not what the user expects when they ask for a simple wait.",
        example_request="Sleep with duration_ms=30000",
        aliases=("sleeper", "sleep", "wait", "pause", "delay"),
        security_hints=(
            "wait", "wait for", "wait n seconds", "wait 30 seconds",
            "wait some seconds", "wait a few seconds", "sleep",
            "pause", "pause for", "delay", "hold for",
            "milliseconds", "ms", "duration_ms",
        ),
        # Sleeper IS long-running by definition — for a 30 s wait we want the
        # tool to drain inside the wrapped runtime so the LLM sees a single
        # blocking call rather than poll/run_status round-trips.
        poll_window_seconds=600,
        long_running=False,
    ),
    ChatWrappedAgentSpec(
        key="playwrighter",
        template_dir="playwrighter",
        tool_name="chat_agent_playwrighter",
        tool_description="Chat-Agent-Playwrighter",
        display_name="Playwrighter",
        purpose=(
            "Drive a REAL browser (Playwright / Chromium) through a scripted, "
            "interactive, stateful flow: navigate, fill forms, click, wait for "
            "elements, extract text/attributes, screenshot, assert, download. "
            "Use this for INTERACTIVE / AUTHENTICATED / JS-rendered web work — "
            "log into a site, submit a multi-step form, click through a wizard, "
            "scrape a single-page-app dashboard behind a login, run an end-to-end "
            "UI check, or capture a screenshot of a specific post-interaction "
            "state. This is DIFFERENT from chat_agent_crawler (static one-shot "
            "HTTP fetch, no interaction) and from the `googler` tool (web SEARCH "
            "only): reach for Playwrighter whenever the task needs clicks, typing, "
            "waits, logins, or a multi-step sequence. Pass the whole script as a "
            "JSON array in `steps_json` (the flat request grammar cannot express a "
            "list-of-dicts). Each step is {\"action\": <verb>, ...}. Supported "
            "verbs: goto{url,wait_until?}, click{selector}, dblclick{selector}, "
            "fill{selector,value}, type{selector,text,delay?}, press{key,selector?}, "
            "select{selector,value}, check/uncheck{selector}, "
            "wait_for{selector,state?}, wait{ms}, "
            "extract_text{selector?,name?}, extract_attr{selector,attr,name?}, "
            "screenshot{path?,full_page?}, assert_visible{selector}, "
            "assert_text{contains,selector?}, download{selector,save_path?}. "
            "Set headless=false to WATCH the browser; set storage_state_out to "
            "persist the logged-in session for a later run. When the user wants "
            "to SEE the browser or asks to keep it open / wait before closing "
            "(e.g. 'wait 10 seconds before closing so I can watch it'), pass "
            "hold_open_seconds=<N> (e.g. hold_open_seconds=10) — the browser then "
            "lingers N seconds after the last step before it closes. Do NOT rely "
            "on a trailing wait step for this; hold_open_seconds is the dedicated "
            "knob. Extracted values and the final status/assert verdict come back "
            "in the run log (INI_SECTION_PLAYWRIGHTER) for Parametrizer/Exec-Report."
        ),
        example_request=(
            "Run Playwrighter with start_url='https://example.com/login' and headless=true and "
            "steps_json='[{\"action\":\"fill\",\"selector\":\"#email\",\"value\":\"me@example.com\"},"
            "{\"action\":\"fill\",\"selector\":\"#password\",\"value\":\"hunter2\"},"
            "{\"action\":\"click\",\"selector\":\"button[type=submit]\"},"
            "{\"action\":\"wait_for\",\"selector\":\"#dashboard\"},"
            "{\"action\":\"extract_text\",\"selector\":\".welcome\",\"name\":\"greeting\"},"
            "{\"action\":\"assert_visible\",\"selector\":\"#logout\"}]'"
        ),
        aliases=(
            "playwrighter", "playwright", "browser", "browser automation",
            "headless browser", "web automation", "e2e", "end to end",
        ),
        security_hints=(
            "playwright", "playwrighter", "browser automation", "control the browser",
            "drive the browser", "headless browser", "automate the browser",
            "fill the form", "fill in the form", "submit the form", "log into",
            "log in to", "login to the site", "click the button on the page",
            "navigate the site", "scrape after login", "authenticated scrape",
            "e2e test", "end-to-end test", "ui test", "browser test",
            "click through", "wait for the element", "extract from the page",
            "single page app", "spa", "web form", "web wizard",
        ),
        # A real browser flow (login + several steps + screenshots) can take a
        # while; drain inside the wrapped runtime rather than poll round-trips.
        poll_window_seconds=180,
        long_running=True,
    ),
)


WRAPPED_CHAT_AGENT_MAP = {spec.key: spec for spec in WRAPPED_CHAT_AGENT_SPECS}
WRAPPED_CHAT_AGENT_BY_TOOL_NAME = {spec.tool_name: spec for spec in WRAPPED_CHAT_AGENT_SPECS}
WRAPPED_CHAT_AGENT_BY_DESCRIPTION = {spec.tool_description: spec for spec in WRAPPED_CHAT_AGENT_SPECS}


def get_wrapped_agent_security_hints() -> tuple[str, ...]:
    hints: list[str] = []
    for spec in WRAPPED_CHAT_AGENT_SPECS:
        for hint in spec.security_hints:
            if hint not in hints:
                hints.append(hint)
    return tuple(hints)
