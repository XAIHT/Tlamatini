---
name: project_taskbar_flash_attention
description: Taskbar-flash + uppercase log banner attention notice for Ask-Execs prompts and Notifier notifications (the toast successor)
metadata: 
  node_type: memory
  type: project
  originSessionId: 921d575a-54c3-4cf5-a135-07be8a287b96
---
<!--
═══════════════════════════════════════════════════════════════════
  ✦  T L A M A T I N I  ✦   —   "one who knows"
  Created by  Angela López Mendoza   ·   @angelahack1
  Developer · Architect · Creator of Tlamatini
  Tlamatini Author Banner — do not remove (Angela's name is kept in every build)
═══════════════════════════════════════════════════════════════════
-->

2026-05-31: Successor to the removed Notifier toast ([[project_native_toast]]). User wanted a "blinking taskbar icon when an app needs attention" on (a) Ask-Execs approval prompts in agent_page.html and (b) Notifier notifications (chat + ACP).

**Hard constraint stated up front (honored)**: page JS is sandboxed — CANNOT flash its own *browser* taskbar button (same wall as the toast), and backend can't reliably pick the right browser window. So we flash the **Tlamatini.exe window the Django process itself owns**. User explicitly chose ".exe window only + UPPERCASE log banner naming the page" (browser title/favicon-blink alternative NOT built).

**Implementation** (source edits, NOT committed; frozen C:\Tlamatini needs `python build.py` — window_flash.py/views.py/urls.py live in the PYZ):
- NEW `agent/window_flash.py`: `flash_console_window(count=5)` = `FlashWindowEx(GetConsoleWindow(), FLASHW_ALL, count)`; `build_attention_banner(page,reason)` = fully UPPERCASE banner (user wanted mayúsculas; test asserts `banner==banner.upper()`); `notify_attention()` flashes + `print()`s banner (tee'd to tlamatini.log). **Fail-safe — never raises**; headless/windowless → banner only, returns False.
- `POST /agent/flash_window/` (`views.flash_window_view`, `secure_post` = login+csrf+POST). Body `{page,reason}`, tolerates malformed body.
- `shared-runtime-dialogs.js`: `flashTlamatiniWindow(reason,page)` (self-contained csrf cookie read, auto-detects page from pathname), exported on `window.SharedRuntimeDialogs`. Called INSIDE `renderNotifierToast()` (the ONE shared renderer for both chat poller + ACP → one hook covers both; fires once/notification since backend deletes notification.json after read) AND in `agent_page_chat.js` exec-permission-request handler (page pinned 'agent_page.html').

Tests: `FlashWindowAttentionTests` (8, drive real view+helper; Win32 flash → False in headless test). ruff + eslint clean (0 errors). Fix-log entry in docs/claude/recent-fixes.md (2026-05-31).
