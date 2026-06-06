---
name: Apostrophe / quote fix in keyboarder + wrapper
description: 2026-05-07 fix for the "Hi!, i''m tlamatini" bug — the LLM passed `''Hi!, I''m Tlamatini''` (doubled outer + SQL-doubled inner apostrophe) and it survived all the way to Notepad as two literal `'` chars.
type: project
originSessionId: 161aebfa-f2df-4d28-bcdf-e79b7579c58e
---
The 2026-05-07 desktop-UI test typed `Hi!, i''m tlamatini` instead of `Hi!, I'm Tlamatini`. Root cause was three layers all missing escape support for apostrophes inside quoted values.

**Why:** the LLM passed `input_sequence=''Hi!, I''m Tlamatini''` (Python-style doubled outer quote + SQL-style doubled inner apostrophe). The wrapper stripped one outer layer leaving `'Hi!, I''m Tlamatini'`, did not decode the SQL `''`, YAML stored it verbatim, the keyboarder loaded back `'Hi!, I''m Tlamatini'` and naively toggled in_single state on every `'` — closing prematurely after the apostrophe in `I'm`, and re-opening on the real closing apostrophe (which then swallowed the rest of the sequence).

**How to apply:** when the user reports "the apostrophe gets doubled" / "letters became lowercase after I'm" / similar text-typing artefacts via Keyboarder, this commit is the reference fix.

## The three coordinated fixes

1. **Wrapper `_unquote_preserving_backslashes` (tools.py:639)** — now decodes SQL/YAML-single-quoted-style `''` → `'` (and `""` → `"`) inside the matching outer quote. Combined with the existing backslash decode, this collapses both common LLM escape conventions before the value lands in YAML.
2. **Keyboarder `split_sequence` (keyboarder.py:217)** — now (a) supports `''` and `\'` (and the double-quote variants) inside literals, (b) uses the same lookahead heuristic as the wrapper to disambiguate "internal apostrophe vs closing quote" — a `'` inside a single-quoted literal is a closer ONLY if followed (after optional whitespace) by `,` or EOF; otherwise it's literal, (c) falls back to typing the entire input as a literal string when no token resolves to a recognized key (defensive — covers "LLM forgot quotes around literal text" cases like `Hi!, I'm Tlamatini`).
3. **chat_agent_keyboarder spec (chat_agent_registry.py)** — purpose / example_request now explicitly document: "literal text MUST be wrapped in single quotes; embed `'` as `''` SQL-style or `\'` backslash-style; do NOT double the OUTER quotes". Example updated to `"'Hi!, I''m Tlamatini', enter"`.

## End-to-end verification (5/5 LLM-input variants → `Hi!, I'm Tlamatini`)

| LLM raw input | Wrapper coerced | Keyboarder typed |
|---|---|---|
| `"'Hi!, I''m Tlamatini', enter"` (canonical) | `'Hi!, I''m Tlamatini', enter` | `Hi!, I'm Tlamatini` + Enter |
| `'Hi!, I''m Tlamatini'` (single outer + SQL inner) | `Hi!, I'm Tlamatini` | `Hi!, I'm Tlamatini` |
| `''Hi!, I''m Tlamatini''` (the screenshot bug) | `'Hi!, I'm Tlamatini'` | `Hi!, I'm Tlamatini` |
| `Hi!, I am Tlamatini` (no quotes — fallback) | `Hi!, I am Tlamatini` | `Hi!, I am Tlamatini` |
| `"'Hi!, I\\'m Tlamatini'"` (backslash) | `'Hi!, I\\'m Tlamatini'` | `Hi!, I'm Tlamatini` |

## Files touched

- `agent/tools.py` — `_unquote_preserving_backslashes` (SQL `''` decode added)
- `agent/agents/keyboarder/keyboarder.py` — `split_sequence` rewrite + `_decode_literal_escapes` + `_RECOGNIZED_KEYS` set + `_all_keys_recognized` helper
- `agent/chat_agent_registry.py` — Keyboarder purpose / example_request

## Open issue (not addressed by this fix)

The screenshot also showed `i` and `t` lowercase in `i''m tlamatini`. After this fix, the typed text is `Hi!, I'm Tlamatini` with **one** apostrophe — pyautogui's keyboard-layout-sensitive shift handling around the dead-key apostrophe on Spanish/Latin keyboard layouts may have caused the lowercase. With only one apostrophe instead of two consecutive ones, the dead-key state is less likely to leak into the next char. If the user reports lowercase recurring, the next step is to switch the literal-typing path from `pyautogui.write` to a clipboard-paste mechanism (set clipboard → `pyautogui.hotkey('ctrl','v')`) which bypasses keyboard layout entirely.
