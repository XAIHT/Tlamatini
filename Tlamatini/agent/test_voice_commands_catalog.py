# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza · @angelahack1
# ═══════════════════════════════════════════════════════════════════
"""VOICE COMMANDS — the catalog section added by migration 0201 (2026-09-12).

Three contracts, and they fail for three different reasons on purpose:

1. **PLACEMENT.** ``voice_commands`` is entry ZERO of
   ``views.PROMPT_CATEGORY_ORDER`` — Angela's instruction was the *very
   beginning* of the catalog, ahead of Getting Started — and
   ``/agent/list_prompts/`` really serves it first.

2. **ANGELA'S SENTENCE IS VERBATIM.** Prompt 122 carries her words letter for
   letter. A later "tidy-up" migration that paraphrases them fails here.

3. **THE BADGES ARE WHAT SHE ASKED FOR.** The natures are not a stored flag —
   ``tools_dialog.js::classifyPromptModes`` DERIVES them from the prompt text,
   and ``applyPromptModesToToggles`` then ticks exactly those checkboxes. So the
   only way to pin "this card is Multi-turn + Exec-report + ACPX" is to run the
   same classification over the seeded content. ``_classify_prompt_modes`` below
   is a faithful Python port of that function, and
   ``ClassifierPortFidelityTests`` re-reads the real JS to prove the port has not
   drifted from it — a port nobody checks is worse than no port.

   ⚠️ The classifier is why prompt 122 NAMES ``invoke_skill`` / ``acp_spawn`` /
   ``acp_send_and_wait`` in its PRE-FLIGHT, and why prompt 121 must NOT. That is
   not keyword-stuffing: with ACPX unticked, ``agent.acpx.filter_acpx_tools``
   strips the whole ACPX/Skills surface before the executor sees it, so a spoken
   instruction that turns out to need a peer CLI or a skill would find nothing
   bound. The card ticks ACPX because the card genuinely needs it.

The end-to-end proof that the REAL browser does all of this lives in the VISIBLE
headed-Chrome runner
``.claude/skills/tlamatini-daily-chat-test/harness/voice_commands_visible.py``
(Playwrighter drives, Shoter photographs). Headless tests are forbidden here.
"""
import os
import re

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from agent.models import Prompt
from agent.views import PROMPT_CATEGORY_ORDER

SECTION_KEY = 'voice_commands'
SECTION_LABEL = 'Voice Commands'
OPENER_ID = 121
ANGELA_CARD_ID = 122

# Angela's own words, 2026-09-12. Stored exactly as she wrote them, trailing
# "go!." and all — this string is the reason the card exists.
ANGELA_SENTENCE = (
    "Tlamatini, using Whisperer record my voice till I finish to tell you a "
    "prompt, then use the text extracted as a prompt and invoke it, go!."
)

_JS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'static', 'agent', 'js', 'tools_dialog.js',
)

# ── the port of tools_dialog.js::classifyPromptModes ────────────────────────
_SCRUB = re.compile(r"(?:do\s+not|don['’]?t|never|not)\s+use\b[^.;]*[.;]?", re.I)
_ACPX_TOOLS = re.compile(
    r"\b(?:acp_doctor|acp_spawn|acp_send|acp_send_and_wait|acp_relay|acp_kill"
    r"|acp_transcript|acp_session_status|acp_list_sessions|list_acp_agents"
    r"|invoke_skill|list_skills)\b", re.I)
_ACPX_SKILL_A = re.compile(r"\b(?:code-review|security-audit)\b[\s\S]{0,16}\bskill\b", re.I)
_ACPX_SKILL_B = re.compile(r"\bskill\b[\s\S]{0,16}\b(?:code-review|security-audit)\b", re.I)
_WRAPPED = re.compile(r"\bchat_agent_\w+", re.I)
_MULTITURN_WORD = re.compile(r"\bmulti-?turn\b", re.I)
_SXS_A = re.compile(
    r"step-?by-?step\s+(?:wizard|checkbox|toggle|mode|nature|guidance|pacing"
    r"|cadence|setup)", re.I)
_SXS_B = re.compile(r"(?:tick|check|enable|turn\s+on)[^.\n]{0,60}step-?by-?step", re.I)


def _classify_prompt_modes(content):
    """Faithful port of tools_dialog.js::classifyPromptModes."""
    c = content or ''
    scrubbed = _SCRUB.sub(' ', c)
    acpx = bool(
        _ACPX_TOOLS.search(scrubbed)
        or _ACPX_SKILL_A.search(scrubbed)
        or _ACPX_SKILL_B.search(scrubbed)
    )
    multiturn = acpx or bool(_WRAPPED.search(c)) or bool(_MULTITURN_WORD.search(c))
    stepbystep = bool(_SXS_A.search(c) or _SXS_B.search(c))
    if acpx:
        modes = ['multiturn', 'acpx']
    elif multiturn:
        modes = ['multiturn']
    else:
        modes = ['oneshot']
    if stepbystep:
        modes.append('stepbystep')
    if 'oneshot' not in modes:
        modes.append('execreport')
    return modes


class VoiceCommandsSectionPlacementTests(SimpleTestCase):
    """Angela: the section goes at the VERY BEGINNING of the catalog."""

    def test_voice_commands_is_the_first_section(self):
        keys = [key for key, _label in PROMPT_CATEGORY_ORDER]
        self.assertEqual(
            keys[0], SECTION_KEY,
            'VOICE COMMANDS must be the FIRST catalog section (Angela, '
            '2026-09-12) — it currently sits at index %d' % (
                keys.index(SECTION_KEY) if SECTION_KEY in keys else -1),
        )

    def test_section_label(self):
        # Rendered uppercase by .prompt-category-label { text-transform: uppercase }
        # so the header reads VOICE COMMANDS on screen.
        self.assertEqual(dict(PROMPT_CATEGORY_ORDER)[SECTION_KEY], SECTION_LABEL)

    def test_it_is_distinct_from_media_voice(self):
        # Media & Voice = producing/consuming media. Voice Commands = DRIVING
        # Tlamatini by speaking. Collapsing them would bury the new section.
        keys = [key for key, _label in PROMPT_CATEGORY_ORDER]
        self.assertIn('media_voice', keys)
        self.assertNotEqual(SECTION_KEY, 'media_voice')


class VoiceCommandsPromptTests(TestCase):
    """The two seeded cards."""

    def test_both_cards_exist_in_the_section(self):
        rows = {
            r.idPrompt: r
            for r in Prompt.objects.filter(category=SECTION_KEY, hidden=False)
        }
        self.assertEqual(
            sorted(rows), [OPENER_ID, ANGELA_CARD_ID],
            'migration 0201 did not seed both VOICE COMMANDS cards',
        )
        self.assertEqual(rows[OPENER_ID].sort_rank, 10)   # reserved opener slot
        self.assertEqual(rows[ANGELA_CARD_ID].sort_rank, 20)
        self.assertEqual(rows[ANGELA_CARD_ID].promptName, 'prompt-%d' % ANGELA_CARD_ID)

    def test_angelas_sentence_is_stored_verbatim(self):
        body = Prompt.objects.get(idPrompt=ANGELA_CARD_ID).promptContent
        self.assertIn(
            ANGELA_SENTENCE, body,
            "prompt %d no longer carries Angela's sentence word for word"
            % ANGELA_CARD_ID,
        )

    def test_angelas_card_drives_whisperer_with_the_sound_gate(self):
        body = Prompt.objects.get(idPrompt=ANGELA_CARD_ID).promptContent
        self.assertIn('chat_agent_whisperer', body)
        self.assertIn('silence_timeout_seconds', body)
        # The whole card depends on NOT passing record_seconds: that parameter is
        # the mode switch that turns the sound gate OFF and would cut Angela off
        # mid-sentence at a fixed length (v1.51.7 contract).
        self.assertNotIn(
            'record_seconds=', body,
            'the card must never hand Whisperer a duration — that disarms the '
            'sound gate and truncates the spoken prompt',
        )
        self.assertIn('record_seconds out entirely', body)

    def test_angelas_card_refuses_to_invent_a_prompt_it_could_not_hear(self):
        # The honesty gate: an empty/unavailable transcription must stop the run,
        # never be replaced by a plausible guess.
        body = Prompt.objects.get(idPrompt=ANGELA_CARD_ID).promptContent
        self.assertIn('engine_unavailable', body)
        self.assertIn('empty', body)

    def test_the_opener_is_a_genuine_step_by_step_wizard(self):
        # Duplicated on purpose from test_prompt_catalog_contiguous so a failure
        # here names the VOICE COMMANDS section specifically.
        body = Prompt.objects.get(idPrompt=OPENER_ID).promptContent.lower()
        self.assertIn('step-by-step', body)
        self.assertIn('wait', body)
        self.assertIn('chat_agent_whisperer', body)


class VoiceCommandsModeBadgeTests(TestCase):
    """The natures Angela specified, derived the way the browser derives them."""

    def test_angelas_card_is_multiturn_acpx_execreport(self):
        modes = _classify_prompt_modes(
            Prompt.objects.get(idPrompt=ANGELA_CARD_ID).promptContent)
        self.assertEqual(
            modes, ['multiturn', 'acpx', 'execreport'],
            'clicking the card must tick Multi-Turn + ACPX + Exec report '
            '(Angela, 2026-09-12); got %r' % (modes,),
        )

    def test_angelas_card_is_not_mis_badged_as_step_by_step(self):
        modes = _classify_prompt_modes(
            Prompt.objects.get(idPrompt=ANGELA_CARD_ID).promptContent)
        self.assertNotIn('stepbystep', modes)

    def test_the_acpx_tokens_survive_the_forbidden_tool_scrub(self):
        # classifyPromptModes deletes "do not use <…>" clauses BEFORE looking for
        # tool names, so an ACPX token parked inside such a sentence would be
        # thrown away and the badge would silently vanish.
        body = Prompt.objects.get(idPrompt=ANGELA_CARD_ID).promptContent
        self.assertTrue(_ACPX_TOOLS.search(_SCRUB.sub(' ', body)))

    def test_the_opener_is_multiturn_stepbystep_execreport_not_acpx(self):
        modes = _classify_prompt_modes(
            Prompt.objects.get(idPrompt=OPENER_ID).promptContent)
        self.assertEqual(modes, ['multiturn', 'stepbystep', 'execreport'])


class VoiceCommandsServedFirstTests(TestCase):
    """End-to-end against the endpoint the catalog modal actually calls."""

    def setUp(self):
        User.objects.create_user(username='voice-tester', password='x')  # noqa: S106
        self.client.login(username='voice-tester', password='x')  # noqa: S106
        response = self.client.get('/agent/list_prompts/')
        self.assertEqual(response.status_code, 200)
        self.payload = response.json()

    def test_first_category_served_is_voice_commands(self):
        self.assertEqual(self.payload['categories'][0]['key'], SECTION_KEY)
        self.assertEqual(self.payload['categories'][0]['label'], SECTION_LABEL)

    def test_first_two_cards_served_are_the_voice_commands_in_rank_order(self):
        first_two = self.payload['prompts'][:2]
        self.assertEqual([p['index'] for p in first_two], [OPENER_ID, ANGELA_CARD_ID])
        self.assertTrue(all(p['category'] == SECTION_KEY for p in first_two))


class ClassifierPortFidelityTests(SimpleTestCase):
    """Prove the Python port above still matches the real tools_dialog.js.

    Not a byte comparison — the two languages spell regexes differently. What is
    checked is the VOCABULARY the port depends on: if the JS stops recognising
    ``invoke_skill`` / ``acp_spawn`` as ACPX markers, or stops scrubbing
    forbidden-tool clauses, these tests go red and the badge contract above is
    re-examined instead of quietly becoming fiction.
    """

    def setUp(self):
        with open(_JS, encoding='utf-8') as handle:
            self.js = handle.read()

    def test_js_still_defines_the_classifier_and_the_toggle_applier(self):
        self.assertIn('function classifyPromptModes(', self.js)
        self.assertIn('function applyPromptModesToToggles(', self.js)

    def test_js_still_recognises_the_acpx_tokens_the_card_relies_on(self):
        for token in ('invoke_skill', 'list_skills', 'acp_spawn', 'acp_send_and_wait'):
            self.assertIn(
                token, self.js,
                'tools_dialog.js no longer treats %r as an ACPX marker — prompt '
                '%d would lose its ACPX badge' % (token, ANGELA_CARD_ID),
            )

    def test_js_still_scrubs_forbidden_tool_clauses_first(self):
        self.assertIn("\\s+use\\b[^.;]*[.;]?", self.js)

    def test_js_still_ticks_all_four_toolbar_boxes(self):
        for box in ('multi-turn-enabled', 'acpx-enabled',
                    'exec-report-enabled', 'step-by-step-enabled'):
            self.assertIn(box, self.js)
