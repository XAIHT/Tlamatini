/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 *
 *   Every line of this file was written by Angela López Mendoza.
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 */

// Prompt Designer - Prompt Canvas toolbar buttons
// LOAD ORDER: #3 - Depends on: prompt-designer-globals.js

/* global pdBtnValidate, pdBtnStart, pdBtnStop, pdBtnPause, pdBtnClear,
          pdSprintNotice */

// ========================================
// TOOLBAR
// ========================================

// The five controls of the Prompt Canvas header, in the left-to-right order
// they are painted. They ship in the greyed "nothing wired yet" look of the
// design, but they are NOT `disabled`: a disabled button eats its own click
// and the user would get no answer at all.
const PD_TOOLBAR_BUTTONS = [
    { element: pdBtnValidate, label: 'Validate' },
    { element: pdBtnStart, label: 'Start' },
    { element: pdBtnStop, label: 'Stop' },
    { element: pdBtnPause, label: 'Pause' },
    { element: pdBtnClear, label: 'Clear' }
];

function initPromptDesignerControls() {            // eslint-disable-line no-unused-vars
    PD_TOOLBAR_BUTTONS.forEach(({ element, label }) => {
        if (!element) return;
        element.addEventListener('click', (event) => {
            pdSprintNotice(label, event);
        });
    });
    console.log('--- [PROMPT-DESIGNER] Toolbar wired'
        + ` (${PD_TOOLBAR_BUTTONS.filter((b) => b.element).length} buttons)`);
}
