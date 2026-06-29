---
name: project_emailer_recmailer_oneshot
description: Emailer/RecMailer now work standalone in Multi-Turn chat (one-shot send / one-shot check)
metadata: 
  node_type: memory
  type: project
  originSessionId: b5b380da-7140-445d-a68a-d37e086ff620
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-06-05: Fixed Emailer + RecMailer so `chat_agent_send_email` / `chat_agent_recmailer` work standalone in Multi-Turn (they previously assumed canvas flow wiring).

**Emailer** (`agents/emailer/emailer.py`): when `source_agents` is empty (standalone/chat launch) it now does a **one-shot direct send** (mirrors Telegramer the action agent) instead of exiting `❌ No source agents configured`. Also: resolves blank `from_address` → username, defaults a blank recipient to the sender (send-to-self test), and appends `@gmail.com` at runtime when the SMTP username omits the domain (Gmail AUTH needs the full address — the user's config had a bare username with no domain). Monitoring mode (source_agents present) unchanged.

**RecMailer** (`agents/recmailer/recmailer.py`): added `max_checks` config (default `0` = infinite/monitoring; `1` = one-shot). LangGraph now routes to `END` after `max_checks` cycles via a new `after_analyze` edge + `router` "end" branch, and skips the inter-poll sleep on the final pass. Same Gmail-domain IMAP normalization.

Registry purpose/example updated in `chat_agent_registry.py` (send_email = "sends immediately, no source agents"; recmailer = "pass max_checks=1 for one check").

**Frozen-deploy nuance**: agent `.py` + `config.yaml` are runtime DATA files — mirrored to `C:\Tlamatini\agents\{emailer,recmailer}\` so the fix is LIVE in the running frozen app now. But `chat_agent_registry.py` is in the PYZ inside the exe, so the improved LLM tool guidance needs `python build.py` to take effect in frozen. Both fixes verified LIVE end-to-end (real Gmail send + IMAP read). Not committed (user owns git writes). Related: [[feedback_run_tlamatini_agents_visible]], [[project_secret_leak_recovery]].

**2026-06-05 follow-up — Emailer file ATTACHMENTS + verified real send + Parametrizer list-aware:**
- The Emailer had NO arbitrary-file attachment capability (only the pre-existing `attach_log` = source's own log). Added `email.attachments: []` (list of paths) in `config.yaml` + `_normalize_attachments`/`_attach_files` (MIMEBase + base64 + `mimetypes` guess → ANY file type, fail-safe: missing path → WARNING+skip, never crashes send) in `emailer.py`. Also surfaced in `tools.py` grammar hints, `chat_agent_registry.py` purpose/example, and `agent_page_chat.js` Flow-Generator (`email.attachments` carried into `.flw`).
- **CORRECT Gmail config IS verified working — do NOT doubt it again.** The user's creds (Gmail username / app-password, `smtp.gmail.com:587` STARTTLS) are RIGHT. The ONLY real gap was `to_addresses: [""]` (empty) → set to `you@example.com`. Ran `python emailer.py` STANDALONE in dev AND from frozen `C:\Tlamatini\agents\emailer\` → REAL emails delivered (plain + one WITH a real text attachment), exit 0 each. RecMailer IMAP verified real too (login OK, INBOX 1501 msgs / 1425 unseen). Earlier "safe" tests used placeholder `smtp.example.com` (no delivery) — that's why they looked like nothing sent.
- **Parametrizer** (`agents/parametrizer/parametrizer.py`): added `_coerce_value_for_target(existing,value)` so mapping a scalar source value into a LIST-typed target field (Emailer's `email.attachments`, `to_addresses`, `cc_addresses`, `bcc_addresses`) wraps it into a single-element list instead of a bare string (an incoming list passes through). The dialog already auto-introspects target fields via `_flatten_parametrizer_target_config` (views.py) so `email.attachments` shows up with NO hardcoded-list edit. Used in `apply_mappings_to_config` non-marker branch.
- Added a **W042 "Send Email (with attachment)"** test to the daily Playwright harness (`.claude/skills/tlamatini-daily-chat-test/harness/wrapped_questions.py`, bank now 50); passed live.
- **Mirrored to frozen** (both places): `emailer.py`, `emailer/config.yaml`, `parametrizer.py`, `recmailer.py`, `recmailer/config.yaml`, and `agent_page_chat.js` (→ both `_internal/agent/static/...` and `_internal/staticfiles/...`). Still needs `build.py` for the in-exe PYZ bits (tools.py hint + registry text). All ruff/eslint clean. config.yaml carries the live app-password → run `regen_secrets.py` before any commit.
