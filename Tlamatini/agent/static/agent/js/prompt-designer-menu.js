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

// Prompt Designer - Navbar / File menu
// LOAD ORDER: #2 - Depends on: prompt-designer-globals.js

/* global pdFileOpenBtn, pdFileSaveAsBtn, pdFileCloseBtn, pdSprintNotice */

// ========================================
// FILE MENU
// ========================================

// One row per File-menu entry: the element it lives on and the name the
// notice reports. Kept as data rather than three near-identical handlers so
// a new entry is one line, and so a later sprint replaces `pdSprintNotice`
// with the real action in exactly one place per entry.
const PD_FILE_MENU_ENTRIES = [
    { element: pdFileOpenBtn, label: 'File ▸ Open' },
    { element: pdFileSaveAsBtn, label: 'File ▸ Save as' },
    { element: pdFileCloseBtn, label: 'File ▸ Close' }
];

function initPromptDesignerMenu() {                // eslint-disable-line no-unused-vars
    PD_FILE_MENU_ENTRIES.forEach(({ element, label }) => {
        if (!element) return;
        element.addEventListener('click', (event) => {
            pdSprintNotice(label, event);
        });
    });
    console.log('--- [PROMPT-DESIGNER] File menu wired'
        + ` (${PD_FILE_MENU_ENTRIES.filter((e) => e.element).length} entries)`);
}
