# tests_e2e — visible (headed) Playwright end-to-end suites

These drive a **real, visible Chromium** against a **running** Tlamatini server
(they are NOT Django unit tests — those live in `agent/tests.py`). They dogfood
the live chat UI end-to-end.

## `test_create_flow_visual.py` — Create-Flow overhaul (2026-07-06)

Validates the three changes from the Create-Flow overhaul over the live
WebSocket wire, watching a headed browser:

- **REQ 1** — the whole-answer SUCCESS/FAILURE classifier is gone: the final
  `agent_message` frame carries **no** `answer_success` key.
- **REQ 2** — the **Create Flow** button appears whenever Multi-Turn ran with
  **≥1 successfully-executed agent** (no verdict gate), and the downloaded
  `.flw` contains **only** the successful agents (failed executions dropped);
  pure-Q&A answers show **no** button. Because the LLM is **not deterministic**
  about actually invoking an agent for a given prompt, the oracle is derived
  from the live WebSocket frame — `button present == an agent actually ran
  successfully (tool_calls_log has a success)` — NOT from a hardcoded guess.
  A turn where the model chose not to run the agent (button correctly absent)
  is reported as informational, not a failure.
- **REQ 3** — the **Exec report** checkbox is enabled **only** while Multi-Turn
  is checked (disabled + greyed otherwise), mirroring **Ask Execs**.

Verified live 2026-07-06: 100/100 questions answered, **0 hard failures**,
REQ2 100/100, 12/12 downloaded flows successful-only, REQ3 3/3.

### Prerequisites

1. The Tlamatini server is running the **current** code (restart it if you just
   edited `consumers.py` / `response_parser.py` / the static JS —
   `runserver --noreload` does not hot-reload). Note the chat page is at
   **`/agent/agent/`** (the app's urls are mounted under the `agent/` prefix and
   the chat view is `path('agent/', …)`), while `/agent/` and `/` are the login
   page — the harness logs in then navigates to `/agent/agent/`.
2. The DB is **migrated** and the login user exists (source ships an EMPTY
   `db.sqlite3`): `python Tlamatini/manage.py migrate` then create the user
   (`createsuperuser`). Clear stale chat history before a run for a clean
   baseline (`AgentMessage.objects.all().delete()`), or old messages inflate the
   per-turn bot-message count.
3. `playwright` is installed with Chromium: `pip install playwright` +
   `playwright install chromium`.

### Run

```bat
set TLAMATINI_USER=<your username>
set TLAMATINI_PASS=<your password>
python Tlamatini/tests_e2e/test_create_flow_visual.py
```

Useful env knobs: `NUM_QUESTIONS` (default 100), `HEADLESS=1` (default visible),
`ANSWER_TIMEOUT_S` (default 180), `DOWNLOAD_SAMPLE` (default 12; `-1` = validate
every button-bearing flow), `BASE_URL` (default `http://127.0.0.1:8000`).

The suite writes a dated `create_flow_visual_report_<ts>.md` + screenshots +
downloaded `.flw` files under `<repo>/Temp` and exits non-zero on any hard
failure. Only **safe** agents are exercised (Executer `echo`, File-Creator into
`Temp`, Grepper/Globber reads).
