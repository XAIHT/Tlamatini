# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#   Created by  Angela López Mendoza · @angelahack1
# ═══════════════════════════════════════════════════════════════════
"""Catalog-of-Prompts INVARIANTS.

`manage.py test` builds a fresh test DB by running EVERY migration — 0002 seeds
the prompts, later migrations add the demos, 0179 renumbered the catalog to a
contiguous 1..N, 0180 appended the Kali setup wizard, and **0181 adds
`sort_rank`** and seeds the audited display order. So these tests prove the
invariants hold on the REAL seeded prompt set (no live DB is touched).

TWO SEPARATE CONTRACTS — do not conflate them:

  * `idPrompt`  = IDENTITY. Contiguous 1..N, matches `promptName`, and is
    NEVER renumbered. New prompts are APPENDED at max(idPrompt)+1.
  * `sort_rank` = DISPLAY ORDER inside a section (migration 0181). This is what
    makes append-only safe: before 0181 the display order WAS idPrompt, so every
    appended prompt landed last in its section forever (migration 0180 shipped
    the Kali setup WIZARD — a prerequisite and the section's only Step-by-Step
    prompt — as id 97, i.e. dead last in Security & Recon).

The old `test_grouped_by_category_rank` (which required category rank to be
monotonic in idPrompt) is intentionally GONE: that invariant was exactly the
coupling 0181 removes, and 0180 had already broken it. Its real intent —
"every section renders as one contiguous block in the UI's order" — is now
tested end-to-end against `list_prompts_view` in
`PromptCatalogDisplayOrderTests`, where it actually belongs.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from agent.models import Prompt
from agent.views import PROMPT_CATEGORY_ORDER

_RANK = {key: i for i, (key, _label) in enumerate(PROMPT_CATEGORY_ORDER)}
_OTHER = _RANK['other']

# Rank 10 is deliberately left FREE at the top of every section by migration 0181
# so a Step-by-Step opener can be seeded there later without touching anything.
_RESERVED_OPENER_RANK = 10


def _rank(category):
    return _RANK.get((category or '').strip(), _OTHER)


class PromptCatalogContiguityTests(TestCase):
    """`idPrompt` identity contract — unchanged by 0181."""

    def _rows(self):
        return list(
            Prompt.objects.all()
            .values('idPrompt', 'promptName', 'category', 'sort_rank', 'promptContent')
            .order_by('idPrompt')
        )

    def test_ids_are_contiguous_1_to_n_no_gaps(self):
        ids = [r['idPrompt'] for r in self._rows()]
        self.assertTrue(ids, 'the catalog must not be empty')
        self.assertEqual(
            ids, list(range(1, len(ids) + 1)),
            'idPrompt must be a contiguous 1..N with NO gaps',
        )

    def test_promptname_matches_id(self):
        for r in self._rows():
            self.assertEqual(r['promptName'], f"prompt-{r['idPrompt']}")

    def test_new_stm32_platformio_prompts_present_and_firmware(self):
        fw = Prompt.objects.filter(category='firmware_iot')
        # The Blue Pill (STM32F103) demos + the F407 Discovery walkthrough.
        self.assertTrue(fw.filter(promptContent__contains='bluepill_f103c8').exists())
        self.assertTrue(fw.filter(promptContent__contains='disco_f407vg').exists())
        # Both step-by-step camera-verified walkthroughs drive Camcorder.
        self.assertTrue(fw.filter(promptContent__contains='chat_agent_camcorder').exists())


class PromptSortRankTests(TestCase):
    """`sort_rank` display-order contract (migration 0181)."""

    def test_every_prompt_has_a_rank(self):
        # 0 means "unranked" and sorts LAST; after 0181 nothing should be at 0,
        # because the migration also assigns a trailing rank to anything its
        # explicit order map did not cover.
        unranked = list(
            Prompt.objects.filter(sort_rank=0).values_list('idPrompt', flat=True)
        )
        self.assertEqual(unranked, [], f'prompts left unranked by 0181: {unranked}')

    def test_ranks_are_unique_within_a_section(self):
        # A tie would make the display order depend on idPrompt again for those
        # two cards — i.e. exactly the coupling 0181 removes.
        by_section = {}
        for r in Prompt.objects.filter(hidden=False).values('idPrompt', 'category', 'sort_rank'):
            by_section.setdefault(_rank(r['category']), []).append(r)
        for section, rows in by_section.items():
            ranks = [r['sort_rank'] for r in rows]
            self.assertEqual(
                len(ranks), len(set(ranks)),
                f'duplicate sort_rank inside section rank {section}: '
                f'{sorted((r["sort_rank"], r["idPrompt"]) for r in rows)}',
            )

    def test_opener_slot_holds_at_most_one_prompt_per_section(self):
        # Rank 10 is the Step-by-Step opener slot (0181 reserved it, 0182 filled
        # nine of them). Two prompts sharing it inside one section would make the
        # section opener depend on idPrompt again.
        by_section = {}
        for r in Prompt.objects.filter(sort_rank=_RESERVED_OPENER_RANK, hidden=False).values(
            'idPrompt', 'category'
        ):
            by_section.setdefault(_rank(r['category']), []).append(r['idPrompt'])
        for section, ids in by_section.items():
            self.assertEqual(
                len(ids), 1,
                f'section rank {section} has {len(ids)} prompts at the reserved '
                f'opener rank {_RESERVED_OPENER_RANK}: {sorted(ids)}',
            )

    def test_known_section_openers(self):
        # Angela's rule, section by section. Four wizards already existed and were
        # promoted by 0181; the other nine were authored by 0182.
        expected_first = {
            'getting_started': 1,    # create a new Tlamatini user      (pre-existing)
            'firmware_iot': 70,      # STM32F407 blink, on-board ST-Link (pre-existing)
            'security_recon': 97,    # Kali back-end setup               (pre-existing)
            'messaging': 83,         # Telegrammer setup                 (pre-existing)
            'files_search': 98,      # Files & Search guided tour        (0182)
            'run_execute': 99,       # Run & Execute wizard              (0182)
            'code_gen': 100,         # scaffold a small project          (0182)
            'images': 101,           # Images & Vision wizard            (0182)
            'agents_flows': 102,     # Guided First Agents               (0182)
            'acpx_skills': 103,      # ACPX & Skills first contact       (0182)
            'desktop_ui': 104,       # Desktop First Steps               (0182)
            'games_3d': 105,         # 3D Bridges first contact          (0182)
            'media_voice': 106,      # Media & Voice first steps         (0182)
        }
        # Every section that exists must be covered by this map — a NEW section
        # added later without an opener fails here rather than slipping through.
        live = set(
            Prompt.objects.filter(hidden=False)
            .exclude(category='')
            .values_list('category', flat=True)
        )
        self.assertEqual(
            live - set(expected_first), set(),
            'these sections have no declared Step-by-Step opener',
        )
        for category, want_id in expected_first.items():
            first = (
                Prompt.objects.filter(category=category, hidden=False)
                .order_by('sort_rank', 'idPrompt')
                .values_list('idPrompt', flat=True)
                .first()
            )
            self.assertEqual(
                first, want_id,
                f'section {category!r} must open with prompt {want_id} '
                f'(its Step-by-Step wizard), got {first}',
            )

    def test_every_section_opens_with_a_genuine_step_by_step_wizard(self):
        # The invariant behind Angela's rule, checked on CONTENT rather than on a
        # hardcoded id list: the first card of every section must tell the user to
        # tick Step-by-Step AND must promise to WAIT between actions. A prompt that
        # merely lists "Step 1: / Step 2:" for the LLM to run unattended does NOT
        # qualify — that was the exact false positive the 2026-07-20 audit had to
        # rule out in 9 of 13 sections.
        for category in sorted(
            set(
                Prompt.objects.filter(hidden=False)
                .exclude(category='')
                .values_list('category', flat=True)
            )
        ):
            first = (
                Prompt.objects.filter(category=category, hidden=False)
                .order_by('sort_rank', 'idPrompt')
                .first()
            )
            body = (first.promptContent or '').lower()
            self.assertIn(
                'step-by-step', body,
                f'section {category!r} opener (prompt {first.idPrompt}) never names '
                f'the Step-by-Step checkbox',
            )
            # "wait" is the load-bearing marker (STOP and WAIT for me). The reply
            # token itself is a convention, not a requirement — prompt 83 says
            # "WAIT for my reply" and never uses the word READY, and it is a
            # perfectly genuine wizard.
            self.assertIn(
                'wait', body,
                f'section {category!r} opener (prompt {first.idPrompt}) does not '
                f'promise to WAIT for the user between actions',
            )


class PromptCatalogDisplayOrderTests(TestCase):
    """End-to-end: what /agent/list_prompts/ actually hands the catalog modal."""

    def setUp(self):
        # /agent/list_prompts/ is wrapped in `secure_get` (login required), so an
        # anonymous GET 302s to the login page — log a user in first.
        User.objects.create_user(username='catalog-tester', password='x')  # noqa: S106
        self.client.login(username='catalog-tester', password='x')  # noqa: S106
        response = self.client.get('/agent/list_prompts/')
        self.assertEqual(response.status_code, 200)
        self.payload = response.json()

    def test_sections_are_contiguous_blocks_in_display_order(self):
        # Replaces the old idPrompt-based grouping test: every category must form
        # ONE contiguous run of cards, and the runs must follow
        # PROMPT_CATEGORY_ORDER. This is the invariant the UI actually depends on.
        seen_order, blocks = [], []
        for p in self.payload['prompts']:
            if not blocks or blocks[-1] != p['category']:
                blocks.append(p['category'])
                seen_order.append(p['category'])
        self.assertEqual(
            len(blocks), len(set(blocks)),
            f'a category is split across non-adjacent blocks: {blocks}',
        )
        self.assertEqual(
            seen_order, sorted(seen_order, key=_rank),
            'category blocks must follow PROMPT_CATEGORY_ORDER',
        )

    def test_categories_payload_matches_the_blocks(self):
        blocks = []
        for p in self.payload['prompts']:
            if not blocks or blocks[-1] != p['category']:
                blocks.append(p['category'])
        self.assertEqual([c['key'] for c in self.payload['categories']], blocks)

    def test_hidden_prompts_are_absent(self):
        hidden_names = set(
            Prompt.objects.filter(hidden=True).values_list('promptName', flat=True)
        )
        served = {p['name'] for p in self.payload['prompts']}
        self.assertEqual(served & hidden_names, set())

    def test_unranked_prompt_sorts_last_in_its_section_not_first(self):
        # The fail-open guarantee: a future migration that forgets to set a rank
        # must degrade to "appears at the end", NEVER to "hijacks the opener".
        victim = (
            Prompt.objects.filter(category='getting_started', hidden=False)
            .order_by('-sort_rank').first()
        )
        Prompt.objects.filter(idPrompt=victim.idPrompt).update(sort_rank=0)
        payload = self.client.get('/agent/list_prompts/').json()
        section = [p for p in payload['prompts'] if p['category'] == 'getting_started']
        self.assertEqual(section[-1]['index'], victim.idPrompt)
        self.assertNotEqual(section[0]['index'], victim.idPrompt)
