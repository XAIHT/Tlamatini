"""
Question bank generator for the Tlamatini daily chat test.

Produces EXACTLY 1000 questions, deterministically (stable order + stable ids),
so successive daily runs are comparable.

SAFETY CONTRACT
---------------
The run mode the user pinned is Multi-Turn ON, which makes Tlamatini an
*operator* -- it will REALLY execute tools. Therefore every question in this
bank is curated to be SAFE TO EXECUTE 1000x/day on the developer's own machine:

  * knowledge / introspection  -> the LLM mostly answers directly
  * self-knowledge             -> describes Tlamatini itself
  * benign read-only ops       -> get time, git *status/log*, read a few lines,
                                  search the codebase, system metrics, dir list
  * general IT/programming Q&A  -> answered directly, no side effects

It deliberately contains NO destructive prompts: nothing deletes/moves/writes
files, formats, kills processes, scans third-party hosts, sends messages, spawns
GUIs in bulk, or mutates remote state. ACPX/skill *execution* is excluded too
(ACPX is OFF for this run, so acp_* tools are filtered out) -- ACPX shows up only
as knowledge questions.

Each question is a dict:
    {
        "id":       "Q0001",
        "category": "agent-knowledge",
        "text":     "...",
        "expect":   ["keyword", ...],   # heuristic hint (>=1 expected, optional)
        "min_len":  40,                  # heuristic min answer length
    }
"""

from typing import List, Dict, Any

# Repo path used by the handful of benign read-only ops questions.
REPO = r"C:\Development\Tlamatini"

# --- The agent catalog (DISPLAY NAME casing is authoritative) -------------
# (display_name, [keywords the answer should plausibly mention])
AGENTS = [
    ("Starter", ["entry", "launch", "first"]),
    ("Ender", ["terminate", "kill", "cleaner"]),
    ("Stopper", ["kill", "pattern", "log"]),
    ("Cleaner", ["delete", "log", "pid"]),
    ("Sleeper", ["wait", "delay", "ms"]),
    ("Croner", ["schedule", "time", "trigger"]),
    ("Raiser", ["watch", "pattern", "downstream"]),
    ("Forker", ["route", "path", "branch"]),
    ("Asker", ["choice", "interactive", "user"]),
    ("Counter", ["counter", "threshold", "route"]),
    ("OR", ["gate", "either", "source"]),
    ("AND", ["gate", "both", "source"]),
    ("Barrier", ["gate", "all", "sources"]),
    ("Executer", ["shell", "command", "execute"]),
    ("Pythonxer", ["python", "ruff", "script"]),
    ("Prompter", ["llm", "prompt"]),
    ("Summarizer", ["summar", "llm", "text"]),
    ("Crawler", ["web", "crawl", "llm"]),
    ("Googler", ["google", "search", "playwright"]),
    ("Playwrighter", ["browser", "playwright", "steps"]),
    ("Apirer", ["http", "api", "rest"]),
    ("Gitter", ["git", "repo", "commit"]),
    ("SSHer", ["ssh", "remote", "command"]),
    ("SCPer", ["scp", "transfer", "file"]),
    ("Dockerer", ["docker", "container"]),
    ("Kuberneter", ["kubectl", "kubernetes"]),
    ("PSer", ["powershell", "command"]),
    ("Jenkinser", ["jenkins", "job"]),
    ("Sqler", ["sql", "query", "database"]),
    ("Mongoxer", ["mongo", "database"]),
    ("Mover", ["move", "copy", "glob"]),
    ("Deleter", ["delete", "glob", "file"]),
    ("Shoter", ["screenshot", "screen"]),
    ("Camcorder", ["camera", "webcam", "opencv"]),
    ("Recorder", ["microphone", "audio", "wav"]),
    ("AudioPlayer", ["audio", "playback", "speaker"]),
    ("VideoPlayer", ["video", "playback", "display"]),
    ("Mouser", ["mouse", "click", "pyautogui"]),
    ("Keyboarder", ["keyboard", "type", "hotkey"]),
    ("Windower", ["window", "win32", "focus"]),
    ("File-Creator", ["create", "file", "content"]),
    ("File-Interpreter", ["read", "interpret", "llm"]),
    ("File-Extractor", ["extract", "text", "pdf"]),
    ("Image-Interpreter", ["vision", "image", "llm"]),
    ("J-Decompiler", ["jar", "decompile", "java"]),
    ("De-Compresser", ["compress", "archive", "zip"]),
    ("Telegrammer", ["telegram", "message"]),
    ("TeleTlamatini", ["telegram", "bridge", "bot"]),
    ("ACPXer", ["acpx", "cli", "session"]),
    ("Unrealer", ["unreal", "engine", "mcp"]),
    ("Reviewer", ["review", "diff", "verdict"]),
    ("Analyzer", ["static", "analysis", "findings"]),
    ("Kalier", ["kali", "security", "nmap"]),
    ("STM32er", ["stm32", "firmware", "flash"]),
    ("ESP32er", ["esp32", "platformio", "firmware"]),
    ("Arduiner", ["arduino", "cli", "firmware"]),
    ("Kyber-KeyGen", ["kyber", "key", "quantum"]),
    ("Kyber-Cipher", ["kyber", "encrypt"]),
    ("Kyber-DeCipher", ["kyber", "decrypt"]),
    ("Parametrizer", ["map", "config", "queue"]),
    ("FlowBacker", ["backup", "session", "log"]),
    ("FlowCreator", ["flow", "design", "llm"]),
    ("Gatewayer", ["webhook", "ingress", "folder"]),
    ("Gateway-Relayer", ["webhook", "github", "relay"]),
    ("Node-Manager", ["node", "registry", "infrastructure"]),
    ("Monitor-Log", ["monitor", "log", "llm"]),
    ("Monitor-Netstat", ["monitor", "port", "network"]),
    ("Emailer", ["smtp", "email"]),
    ("RecMailer", ["imap", "email", "receive"]),
    ("Notifier", ["notification", "popup"]),
    ("Whatsapper", ["whatsapp", "message"]),
    ("FlowHypervisor", ["health", "monitor", "watchdog"]),
]

# --- Curated system / architecture knowledge questions --------------------
SYSTEM_KNOWLEDGE = [
    ("What is Tlamatini and what is it built with?", ["django", "rag"]),
    ("Explain Tlamatini's RAG system (FAISS + BM25).", ["faiss", "bm25"]),
    ("What does Multi-Turn mode do in Tlamatini?", ["tool", "plan"]),
    ("What is the difference between Multi-Turn ON and OFF?", ["one-shot", "tool"]),
    ("What is the Exec Report and when does it appear?", ["table", "agent"]),
    ("What does the ACPX toolbar toggle do?", ["acpx", "tool"]),
    ("What is ACPX in Tlamatini?", ["agent", "protocol", "cli"]),
    ("List the external coding agents ACPX can spawn.", ["claude", "gemini"]),
    ("Explain the acp_spawn tool.", ["spawn", "session"]),
    ("Explain the acp_relay tool.", ["relay", "transcript"]),
    ("What is acp_doctor used for?", ["health", "agent"]),
    ("What are the three ACPX transport modes?", ["oneshot", "tui", "json"]),
    ("What is a SKILL.md package in Tlamatini?", ["skill", "markdown"]),
    ("How does invoke_skill work?", ["skill", "harness"]),
    ("What does the Parametrizer agent do?", ["map", "config"]),
    ("Explain the INI_SECTION format used by source agents.", ["section", "body"]),
    ("What is the Flow Compiler in Tlamatini?", ["config.yaml", "compile"]),
    ("What is a .flw file?", ["flow", "json"]),
    ("How does the Create Flow button work?", ["tool", "flow"]),
    ("What is the Agent Contract registry?", ["contract", "connection"]),
    ("Explain the Five Layers of Tlamatini's system.", ["layer", "mcp"]),
    ("What MCP context providers does Tlamatini have?", ["metrics", "files"]),
    ("How does Tlamatini handle orphan conhost.exe processes?", ["reaper", "conhost"]),
    ("What is the Ask Execs toggle?", ["permission", "proceed"]),
    ("Describe the agent naming convention in Tlamatini.", ["display", "lowercase"]),
    ("Why must STM32er never be written STM32ER?", ["display", "casing"]),
    ("What is the Temp directory policy?", ["temp", "app"]),
    ("What is the Templates directory used for?", ["template", "project"]),
    ("How does self-knowledge injection work via Tlamatini.md?", ["self", "prompt"]),
    ("What does build.py --self-modify do?", ["source", "modify"]),
    ("How is Tlamatini's version derived?", ["git", "tag", "semver"]),
    ("What is the FlowHypervisor and what does it output?", ["ok", "attention"]),
    ("What is the FlowCreator agent skill?", ["flow", "design"]),
    ("How many workflow agent types does Tlamatini have?", ["74", "agent"]),
    ("What is the difference between an agent and a wrapped chat-agent tool?", ["canvas", "tool"]),
    ("What does the global execution planner do?", ["plan", "tool"]),
    ("What is the capability registry?", ["capability", "score"]),
    ("Explain the wrapped chat-agent runtime lifecycle.", ["run", "log"]),
    ("How does Tlamatini detect frozen vs source mode?", ["frozen", "executable"]),
    ("What ports does Tlamatini open?", ["8000", "8765"]),
    ("What is tlamatini.log and how is it written?", ["log", "tee"]),
    ("How does the reanimation (pause/resume) mechanism work?", ["reanim", "pause"]),
    ("What is the difference between target_agents and source_agents?", ["start", "monitor"]),
    ("What special connection fields do the OR and AND gates use?", ["source_agent"]),
    ("How does the Forker route between path A and path B?", ["pattern", "route"]),
    ("What is the role of the Starter agent in a flow?", ["entry", "first"]),
    ("Describe a typical linear flow pattern.", ["starter", "ender"]),
    ("Describe the fork-join flow pattern.", ["gate", "join"]),
    ("What does the De-Compresser agent support?", ["zip", "archive"]),
    ("How does the Notifier popup reach the chat UI?", ["notification", "poll"]),
]

# --- Self-knowledge questions ---------------------------------------------
SELF_KNOWLEDGE = [
    ("Who are you?", ["tlamatini"]),
    ("What does the name Tlamatini mean?", ["know", "nahuatl"]),
    ("What can you do?", ["agent", "tool"]),
    ("Describe your architecture in a few sentences.", ["django", "rag"]),
    ("What LLM backends do you support?", ["ollama", "claude"]),
    ("Are you running in frozen or source mode right now?", ["mode"]),
    ("Which ports do you open and why?", ["8000"]),
    ("What is your main chat page?", ["agent"]),
    ("Can you read and modify your own source code?", ["source", "modify"]),
    ("What is your repository URL?", ["github"]),
    ("What license are you under?", ["gpl"]),
    ("Who is your primary developer?", ["angel"]),
    ("What is the Agentic Control Panel?", ["canvas", "flow"]),
    ("Summarize your capabilities in one paragraph.", ["agent", "rag"]),
    ("What is the difference between you and a plain chatbot?", ["operator", "tool"]),
]

# --- Benign read-only operator tasks (these DO exercise tools) ------------
SAFE_OPS = [
    ("What is the current date and time?", ["time"]),
    ("What is today's date?", ["date"]),
    (f"Run 'git status' in the repository at {REPO} and tell me the current branch.", ["branch"]),
    (f"Run 'git log -n 3 --oneline' in {REPO} and show me the last three commits.", ["commit"]),
    ("Show me the current CPU and memory usage of this machine.", ["cpu", "memory"]),
    ("List the running TCP listening ports on this machine.", ["port"]),
    (f"Show me the first 15 lines of README.md in {REPO}.", ["tlamatini"]),
    (f"List the immediate subdirectories of {REPO}\\Tlamatini\\agent.", ["agents"]),
    (f"Search the codebase under {REPO} for the function 'login_view'.", ["login"]),
    ("Print the Python version available on this machine.", ["python", "3"]),
    ("How many CPU cores does this machine have?", ["core"]),
    ("What is the hostname of this machine?", ["host"]),
    ("Run a python one-liner that prints the numbers 1 to 5.", ["1", "5"]),
    ("Run a python snippet that computes the factorial of 6 and prints it.", ["720"]),
    ("Echo the text 'Tlamatini daily test OK' to the console.", ["tlamatini"]),
    (f"Count how many *.py files are under {REPO}\\Tlamatini\\agent\\agents.", ["py"]),
    ("What is the current working directory of the server process?", ["tlamatini"]),
    (f"Show the last 10 lines of tlamatini.log under {REPO}\\Tlamatini.", ["log"]),
    ("List the environment variable PATH entries (just the count).", ["path"]),
    ("Run a python snippet that prints the sum of the first 100 integers.", ["5050"]),
]

# --- General IT / programming Q&A (answered directly, side-effect free) ----
GENERAL_QA = [
    ("Explain the difference between TCP and UDP.", ["tcp", "udp"]),
    ("What is a Django migration?", ["migration", "schema"]),
    ("Write a Python function that reverses a string.", ["def"]),
    ("What is the difference between a process and a thread?", ["process", "thread"]),
    ("Explain what a REST API is.", ["rest", "http"]),
    ("What is the difference between SQL and NoSQL databases?", ["sql"]),
    ("Explain the concept of recursion with a simple example.", ["recursion"]),
    ("What is a WebSocket and how does it differ from HTTP?", ["websocket"]),
    ("Write a Python list comprehension that squares numbers 1 to 10.", ["for"]),
    ("What is Big-O notation?", ["complexity", "o("]),
    ("Explain what Docker containers are.", ["container", "image"]),
    ("What is the difference between Git merge and rebase?", ["merge", "rebase"]),
    ("What is an environment variable?", ["environment", "variable"]),
    ("Explain the model-view-controller pattern.", ["model", "view"]),
    ("What is a hash table and how does it work?", ["hash", "key"]),
    ("Write a Python function to check if a string is a palindrome.", ["def"]),
    ("What is the difference between authentication and authorization?", ["auth"]),
    ("Explain what CORS is and why it exists.", ["cors", "origin"]),
    ("What is a virtual environment in Python?", ["venv", "environment"]),
    ("Explain the difference between a stack and a queue.", ["stack", "queue"]),
    ("What is JSON and why is it widely used?", ["json"]),
    ("Write a SQL query to select all rows from a 'users' table where active = 1.", ["select"]),
    ("What is a foreign key in a relational database?", ["foreign", "key"]),
    ("Explain what an index does in a database.", ["index"]),
    ("What is the difference between GET and POST HTTP methods?", ["get", "post"]),
    ("What is a regular expression?", ["regex", "pattern"]),
    ("Explain what asynchronous programming is.", ["async"]),
    ("What is the purpose of a load balancer?", ["balance", "traffic"]),
    ("Write a Python function that returns the nth Fibonacci number.", ["def"]),
    ("What is dependency injection?", ["dependency", "inject"]),
    ("Explain the difference between compiled and interpreted languages.", ["compile"]),
    ("What is a race condition?", ["race", "concurren"]),
    ("What does ACID mean in databases?", ["atomic", "consistency"]),
    ("Explain what a CDN is.", ["content", "delivery"]),
    ("What is the difference between a list and a tuple in Python?", ["list", "tuple"]),
    ("Write a Python dictionary comprehension example.", ["for"]),
    ("What is a decorator in Python?", ["decorator"]),
    ("Explain garbage collection.", ["memory", "garbage"]),
    ("What is the difference between == and is in Python?", ["identity", "equal"]),
    ("What is a context manager in Python?", ["with", "context"]),
    ("Explain what unit testing is.", ["test", "unit"]),
    ("What is continuous integration?", ["ci", "integration"]),
    ("Write a bash command to find all .txt files in a directory tree.", ["find"]),
    ("What is the difference between a shallow and a deep copy?", ["shallow", "deep"]),
    ("Explain what an API rate limit is.", ["rate", "limit"]),
    ("What is OAuth?", ["oauth", "token"]),
    ("Explain the publish-subscribe pattern.", ["publish", "subscribe"]),
    ("What is a memory leak?", ["memory", "leak"]),
    ("Write a Python generator that yields even numbers up to 20.", ["yield"]),
    ("What is the difference between HTTP and HTTPS?", ["tls", "secure"]),
    ("Explain what a webhook is.", ["webhook", "http"]),
    ("What is idempotency in the context of APIs?", ["idempoten"]),
    ("What is the difference between concurrency and parallelism?", ["concurren", "parallel"]),
    ("Explain what a B-tree is.", ["tree", "node"]),
    ("What is the purpose of a reverse proxy?", ["proxy"]),
    ("Write a Python function that counts word frequency in a string.", ["def"]),
    ("What is a JWT?", ["jwt", "token"]),
    ("Explain the SOLID principles briefly.", ["single", "responsibility"]),
    ("What is the difference between a class and an instance?", ["class", "instance"]),
    ("What is a semaphore?", ["semaphore", "lock"]),
]

# --- Per-agent question templates -----------------------------------------
_AGENT_TEMPLATES = [
    "What does the {name} agent do in Tlamatini, and when should I use it?",
    "Give me a concrete example of using the {name} agent.",
    "What are the key config.yaml parameters of the {name} agent?",
    "Which other agents does {name} commonly connect to in a flow?",
    "Is {name} a state-changing or read-only/observational agent? Explain.",
    "Summarize the {name} agent in one sentence.",
]


def _q(idx: int, category: str, text: str, expect, min_len: int = 40) -> Dict[str, Any]:
    return {
        "id": f"Q{idx:04d}",
        "category": category,
        "text": text,
        "expect": list(expect) if expect else [],
        "min_len": min_len,
    }


def build_questions() -> List[Dict[str, Any]]:
    """Assemble exactly 1000 deterministic, safe-to-execute questions."""
    items: List[tuple] = []  # (category, text, expect, min_len)

    # 1) Agent knowledge -- 74 agents x 6 templates = 444
    for name, kw in AGENTS:
        for tmpl in _AGENT_TEMPLATES:
            items.append(("agent-knowledge", tmpl.format(name=name), kw, 30))

    # 2) System / architecture knowledge
    for text, kw in SYSTEM_KNOWLEDGE:
        items.append(("system-knowledge", text, kw, 40))

    # 3) Self knowledge
    for text, kw in SELF_KNOWLEDGE:
        items.append(("self-knowledge", text, kw, 20))

    # 4) Benign read-only operator tasks (real tool exercise)
    for text, kw in SAFE_OPS:
        items.append(("safe-op", text, kw, 5))

    # 5) General IT / programming Q&A
    for text, kw in GENERAL_QA:
        items.append(("general-qa", text, kw, 30))

    # Pad to exactly 1000 with additional general-knowledge variants so the
    # bank is always full-size even if a category list is edited later.
    _pad_pool = [
        "Explain the concept of {t} in simple terms.",
        "Give me a short example involving {t}.",
        "What are common pitfalls when working with {t}?",
        "Why does {t} matter in software engineering?",
    ]
    _pad_topics = [
        "caching", "logging", "pagination", "serialization", "encryption",
        "compression", "threading", "queues", "sockets", "DNS", "TLS",
        "hashing", "indexing", "sharding", "replication", "backpressure",
        "rate limiting", "retries", "timeouts", "circuit breakers",
        "feature flags", "observability", "tracing", "metrics", "profiling",
        "memoization", "immutability", "polymorphism", "inheritance",
        "interfaces", "generics", "closures", "coroutines", "event loops",
        "middleware", "schemas", "validation", "migrations", "transactions",
        "deadlocks", "race conditions", "idempotency", "statelessness",
        "load balancing", "service discovery", "blue-green deploys",
        "canary releases", "rollbacks", "checksums", "base64 encoding",
    ]
    pi = 0
    while len(items) < 1000:
        topic = _pad_topics[pi % len(_pad_topics)]
        tmpl = _pad_pool[(pi // len(_pad_topics)) % len(_pad_pool)]
        items.append(("general-qa", tmpl.format(t=topic), [topic.split()[0]], 30))
        pi += 1

    # Hard cap to exactly 1000 (in case category lists grew past it).
    items = items[:1000]

    questions = [
        _q(i + 1, cat, text, expect, min_len)
        for i, (cat, text, expect, min_len) in enumerate(items)
    ]
    assert len(questions) == 1000, f"expected 1000, got {len(questions)}"
    return questions


# Categories present (for the report header).
def category_counts(questions: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for q in questions:
        counts[q["category"]] = counts.get(q["category"], 0) + 1
    return counts


if __name__ == "__main__":
    qs = build_questions()
    print(f"Total questions: {len(qs)}")
    for cat, n in sorted(category_counts(qs).items()):
        print(f"  {cat:20s} {n}")
    print("First 3:")
    for q in qs[:3]:
        print(" ", q["id"], q["category"], "->", q["text"])
    print("Last 3:")
    for q in qs[-3:]:
        print(" ", q["id"], q["category"], "->", q["text"])
