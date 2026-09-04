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

// Prompt Designer - Global State & DOM References
// LOAD ORDER: #1 - Must be loaded before all other prompt-designer-*.js files.
//
// Sibling of acp-globals.js. The Designer is a NEW page with its own script
// set, so nothing here is shared with the Agentic Control Panel: an edit on
// either side can never reach across and break the other.

// ---- DOM References (top-level, available globally) ----
const pdContainer = document.getElementById('designer-container');
const pdAssetsPanel = document.getElementById('main-assets-container');
const pdCanvasPanel = document.getElementById('promptcanvas-container');
const pdSubCanvas = document.getElementById('subpromptcanvas-container');
const pdCanvasContent = document.getElementById('prompt-canvas-content');
const pdDivider = document.getElementById('designer-drag-divider');
const pdAssetsList = document.getElementById('assets-list');
const pdFilenameSpan = document.getElementById('promptcanvas-filename');

// File menu entries
const pdFileOpenBtn = document.getElementById('pd-file-open-button');
const pdFileSaveAsBtn = document.getElementById('pd-file-save-as-button');
const pdFileCloseBtn = document.getElementById('pd-file-close-button');

// Prompt Canvas toolbar buttons
const pdBtnValidate = document.getElementById('pd-btn-validate');
const pdBtnStart = document.getElementById('pd-btn-start');
const pdBtnStop = document.getElementById('pd-btn-stop');
const pdBtnPause = document.getElementById('pd-btn-pause');
const pdBtnClear = document.getElementById('pd-btn-clear');

// ========================================
// SPRINT NOTICE
// ========================================

// The ONE message every control on this page answers with while the Designer
// is still being built. Declared once so a later sprint that implements a
// button only has to delete its call, never hunt for a duplicated string.
const PD_SPRINT_NOTICE = 'Working on it for further sprints';

// ========================================
// THEMED POPUPS
// ========================================
//
// Native alert()/confirm() are FORBIDDEN inside a themed Tlamatini dialog:
// they paint OS chrome carrying the page URL, they block the page, and a
// headed Playwright run cannot photograph what is behind them. These are the
// Designer's themed replacements — same shape and the same fail-open contract
// as acpAlert / acpConfirm on the Agentic Control Panel.

const PD_DIALOG_BUTTON_CSS = {
    'background-color': '#55BBAA',
    'color': 'white',
    'border-radius': '6px',
    'font-size': '0.88rem'
};

/**
 * Paint the CONFIRM button of a jQuery-UI dialog teal, and leave every other
 * button to dialog_theme.css.
 *
 * @param {jQuery} [$scope] Optional button-pane (or dialog) to limit the
 *   search to. Omit it to style the whole page.
 */
function stylePdDialogButtons($scope) {
    const selector = 'button:contains("Save"), button:contains("Go!"), '
        + 'button:contains("Continue"), button:contains("OK"), '
        + 'button:contains("Proceed"), button:contains("Start"), '
        + 'button:contains("Run")';
    const $buttons = $scope && $scope.length
        ? $scope.find(selector)
        : $('.ui-dialog-buttonpane').find(selector);
    $buttons.css(PD_DIALOG_BUTTON_CSS);
}

function _pdModal(primary, secondary, buttons, title) {
    const host = document.getElementById('confirmation-dialog-message');
    const primaryEl = document.getElementById('confirmation-primary-dialog-legend');
    const secondaryEl = document.getElementById('confirmation-secondary-dialog-legend');
    if (!host || !primaryEl || !secondaryEl || typeof $ !== 'function') return null;

    primaryEl.textContent = primary || '';
    primaryEl.style.display = primary ? '' : 'none';
    secondaryEl.textContent = secondary || '';

    const $host = $(host);
    if ($host.hasClass('ui-dialog-content')) {
        $host.dialog('destroy');
    }
    $host.dialog({
        title: title || 'Tlamatini',
        modal: true,
        width: 480,
        resizable: false,
        draggable: true,
        closeText: '',
        buttons: buttons,
        open: function () {
            stylePdDialogButtons($(this).parent().find('.ui-dialog-buttonpane'));
        }
    });
    return $host;
}

/** Themed replacement for `window.alert`. */
function pdAlert(message, title) {
    const $host = _pdModal('', String(message == null ? '' : message), [{
        text: 'OK',
        click: function () { $(this).dialog('close'); }
    }], title);
    if (!$host) {
        window.alert(message);                     // fail open — never lose a notice
    }
}

/**
 * Themed replacement for `window.confirm`. Returns a Promise<boolean>.
 * Closing the dialog any other way resolves FALSE: an action is never taken
 * because a dialog was dismissed.
 */
function pdConfirm(primary, secondary, title) {    // eslint-disable-line no-unused-vars
    return new Promise((resolve) => {
        let decided = false;
        const finish = (value) => {
            if (!decided) { decided = true; resolve(value); }
        };
        const $host = _pdModal(primary, secondary, [
            {
                text: 'Cancel',
                click: function () { finish(false); $(this).dialog('close'); }
            },
            {
                text: 'Continue',
                click: function () { finish(true); $(this).dialog('close'); }
            }
        ], title || 'Please confirm');
        if (!$host) {
            finish(window.confirm([primary, secondary].filter(Boolean).join('\n\n')));
            return;
        }
        $host.off('dialogclose.pdconfirm')
            .on('dialogclose.pdconfirm', () => finish(false));
    });
}

/**
 * Announce that the control the user just pressed is not implemented yet.
 *
 * Every menu entry, toolbar button, asset row and canvas gesture on this page
 * routes here. `label` names the control so the notice is truthful about WHAT
 * is pending, while the message itself stays exactly the agreed sentence.
 *
 * @param {string} [label] Human name of the control that was activated.
 * @param {Event}  [event] Optional event to swallow (menu anchors, etc.).
 */
function pdSprintNotice(label, event) {            // eslint-disable-line no-unused-vars
    if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
    }
    const title = label ? `Prompt Designer — ${label}` : 'Prompt Designer';
    console.log(`--- [PROMPT-DESIGNER] ${label || 'control'}: ${PD_SPRINT_NOTICE}`);
    pdAlert(PD_SPRINT_NOTICE, title);
}
