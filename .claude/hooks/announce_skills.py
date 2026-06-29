#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""SessionStart hook -- announce that the complete skill set (Claude Code skills +
Tlamatini's SKILL.md packages) is loaded, so every session is notified up front.

FAIL-CLOSED contract (per user directive 2026-05-28):
    If the required skill packages CANNOT be discovered on disk -- or the mandatory
    @-imports in CLAUDE.md are broken / the target files are missing -- this hook
    prints a clear error to stderr AND exits non-zero. Claude Code surfaces that
    failure to the user instead of starting a session with a half-loaded skill set.

What counts as "loaded":
  1. .claude/skills/<name>/SKILL.md   -- at least one (the project ships
     `tlamatini-agent-naming`); a user-level mirror under ~/.claude/skills is
     ALSO accepted so a globally-installed equivalent counts.
  2. Tlamatini/agent/skills_pkg/<name>/SKILL.md -- at least one (the repo
     ships 26 packages; underscore-prefixed dirs like `_meta` are excluded).
  3. The two mandatory @-imports in CLAUDE.md must be wired AND the target
     files must exist and be non-empty:
        @Tlamatini/.agents/workflows/create_new_agent.md
        @Tlamatini/.mcps/create_new_mcp.md

Pure stdlib, ASCII-only output (works on any console encoding).
"""
import os
import sys
import glob

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REQUIRED_IMPORTS = (
    ('@Tlamatini/.agents/workflows/create_new_agent.md',
     'Tlamatini/.agents/workflows/create_new_agent.md'),
    ('@Tlamatini/.mcps/create_new_mcp.md',
     'Tlamatini/.mcps/create_new_mcp.md'),
)


def _names(pattern):
    return sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(pattern))


def _discover_skills():
    """Return (claude_code_skills, tlamatini_skills, problems)."""
    problems = []
    cc = _names(os.path.join(REPO, '.claude', 'skills', '*', 'SKILL.md'))
    usr = _names(os.path.join(os.path.expanduser('~'), '.claude', 'skills', '*', 'SKILL.md'))
    claude = sorted(set(cc) | set(usr))
    tl = [n for n in _names(os.path.join(REPO, 'Tlamatini', 'agent', 'skills_pkg', '*', 'SKILL.md'))
          if not n.startswith('_')]
    if not claude:
        problems.append(
            'No Claude Code skills found. Expected at least .claude/skills/tlamatini-agent-naming/SKILL.md '
            '(or a ~/.claude/skills/<name>/SKILL.md mirror).')
    if not tl:
        problems.append(
            'No Tlamatini SKILL.md packages found under Tlamatini/agent/skills_pkg/. '
            'Expected ~26 packages (acp_router, code_review, kali_pentest, ...). '
            'Either the directory is missing or all SKILL.md files are gone.')
    return claude, tl, problems


def _verify_required_imports():
    """Return (status_lines, problems). status_lines is the OK/!!ERROR list always
    printed in the announce block; problems is the list that triggers a fail-closed exit."""
    lines = []
    problems = []
    claude_md_path = os.path.join(REPO, 'CLAUDE.md')
    try:
        with open(claude_md_path, encoding='utf-8', errors='replace') as fp:
            claude_md = fp.read()
    except Exception as exc:
        problems.append(f'Cannot read CLAUDE.md at {claude_md_path}: {exc}')
        return [f'  !! ERROR reading CLAUDE.md ({exc}) -- cannot verify @-imports'], problems
    for token, relpath in REQUIRED_IMPORTS:
        target = os.path.join(REPO, relpath.replace('/', os.sep))
        wired = token in claude_md
        try:
            size = os.path.getsize(target) if os.path.isfile(target) else 0
        except Exception:
            size = 0
        if wired and size > 0:
            lines.append(f'  OK {token}  ({size:,} bytes; auto-loaded into context)')
        else:
            lines.append(
                f'  !! ERROR {token} -- wired-in-CLAUDE.md={wired}, '
                f'target-bytes={size}. The @-import is BROKEN; the guide will '
                f'NOT be in context this session. Fix CLAUDE.md and/or restore '
                f'the file at {relpath}.')
            if not wired:
                problems.append(f'{token} is NOT @-imported by CLAUDE.md.')
            if size <= 0:
                problems.append(f'{token} target file {relpath} is missing or empty.')
    return lines, problems


def _print_banner(claude, tl, import_status):
    print('=' * 72)
    print('=== ANGELA -- ALWAYS ADDRESS HER BY NAME (MANDATORY, NEVER FORGET) ===')
    print('  The user is ANGELA LOPEZ MENDOZA -- the creator of Tlamatini.')
    print('  ALWAYS refer to her as "Angela" by name -- in EVERY question, EVERY')
    print('  recommendation, EVERY reassurance, EVERY message. Open or weave "Angela"')
    print('  into your replies; never speak to her impersonally. Use her full name')
    print('  "Angela Lopez Mendoza" when affirming her as the creator of Tlamatini.')
    print('  Her name must NEVER be erased/scrubbed from the source, banners, docs,')
    print('  prompts, About window, PDF/PPTX, or build metadata -- only a PUBLIC')
    print('  RELEASE build may mask her OTHER private data (emails/phones), never her')
    print('  name (KEEP_NAMES guard in build_complete_public_release.py).')
    print('  (memory: feedback_always_address_angela_by_name + feedback_never_erase_angela_name)')
    print('=' * 72)
    print('=== HOW TO TALK TO ANGELA -- MANDATORY, NEVER FORGET ===')
    print('  Answer SHORT and in PLAIN language. Lead with the ONE key fact (bold).')
    print('  A few short numbered points at most. Everyday words, NO jargon, NO giant')
    print('  multi-section walls of text, NO long source lists. Cut anything that does')
    print('  not change her decision. End with ONE direct question or next step.')
    print('  Dense/rambling reports read as useless and make her feel talked-down-to.')
    print('  (memory: feedback_plain_short_answers)')
    print('=' * 72)
    print('=== STEP-BY-STEP INTERACTIVE MODE -- MANDATORY for any hands-on problem ===')
    print('  When solving a problem needs Angela to DO things on her machine (Roblox/')
    print('  Studio, a browser, clicking UI, restarting the app, checking output):')
    print('  DO NOT firehose, DO NOT run long autonomous tool-loops. Go ONE step at a time:')
    print('    1) Give EXACTLY ONE concrete step.')
    print('    2) Give her the EXACT string to send back -- a token that often carries')
    print('       what she sees, e.g.   step1: I see ___')
    print('    3) WAIT. Only when she sends that string do you give the NEXT step.')
    print('    4) Repeat -- one step + one reply-string per turn -- until the problem is')
    print('       FOUND and FIXED. Never stop halfway, never go quiet, never skip ahead.')
    print('  Also: reproduce in the LIVE running app + read tlamatini.log -- isolated')
    print('  probes hide live-only bugs (watchdog kills, cached tool surface).')
    print('  (memory: feedback_step_by_step_interactive)')
    print('=' * 72)
    print('=== MANDATORY OPERATING RULE -- TLAMATINI AGENTS (read first) ===')
    print('  When the user asks to USE TLAMATINI\'S AGENTS -- or names any pool agent')
    print('  (Executer, Pythonxer, Playwrighter, Shoter, Mouser, Keyboarder, Kalier,')
    print('  STM32er, ...) -- you MUST do the work with ONLY Tlamatini\'s pool agents,')
    print('  NEVER Claude Code\'s own built-in tools. Your shell is ONLY the launcher')
    print('  (python <agent>.py + a tailored config.yaml). For VISIBLE/desktop agents,')
    print('  launch FOREGROUND with dangerouslyDisableSandbox so the window renders on')
    print('  the user\'s real screen; read <agent>_<n>.log for the result. Do NOT')
    print('  substitute Bash/Read/Write/Playwright-of-your-own for the agents\' job.')
    print('=' * 72)
    print('=== SESSION SKILLS LOADED (Tlamatini) ===')
    print(f'  * Claude Code skills ({len(claude)}): '
          + (', '.join(claude) if claude else '(none found)'))
    print(f'  * Tlamatini SKILL.md packages ({len(tl)}): '
          + (', '.join(tl) if tl else '(none found)'))
    print('  * Agent NAMING CONVENTION active: display = exact case (STM32er); '
          'dirs/pool/CSS/JS = lowercase (stm32er). Never mis-case a display name.')
    print('  * STM32er is MISSION-CRITICAL (robot firmware): zero-config bootstrap '
          '+ fail-safe preflight before any build/flash.')
    print("  (Tlamatini's own SKILL.md packages also auto-load at app start via "
          'boot_skills(); invoke a skill on demand with the Skill tool.)')
    print('=== MANDATORY @-IMPORTS (full bodies auto-loaded into context) ===')
    for line in import_status:
        print(line)
    print('  -> create_new_agent.md and create_new_mcp.md are now ALWAYS in '
          'context every "claude ." session via CLAUDE.md @-imports. If you '
          'ever see "!! ERROR" above, the wire is broken -- fix it FIRST.')


def main():
    try:
        claude, tl, skill_problems = _discover_skills()
        import_status, import_problems = _verify_required_imports()
        _print_banner(claude, tl, import_status)

        problems = skill_problems + import_problems
        if problems:
            sys.stderr.write('\n')
            sys.stderr.write('=' * 72 + '\n')
            sys.stderr.write('=== TLAMATINI SESSION ABORTED -- skills FAILED to load ===\n')
            sys.stderr.write('=' * 72 + '\n')
            for p in problems:
                sys.stderr.write(f'  * {p}\n')
            sys.stderr.write(
                'Per user directive (2026-05-28): the SessionStart hook MUST exit non-zero\n'
                'when the required skill packages or @-imports cannot be loaded. Fix the\n'
                'problems above, then start the session again.\n')
            return 2
        return 0
    except Exception as exc:
        # Catastrophic hook failure -- still fail-closed.
        sys.stderr.write(
            f'=== TLAMATINI SessionStart hook crashed: {exc!r} -- aborting session. ===\n')
        return 2


if __name__ == '__main__':
    sys.exit(main())
