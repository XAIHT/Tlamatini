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

// Prompt Designer - Assets panel (left column)
// LOAD ORDER: #4 - Depends on: prompt-designer-globals.js

/* global pdAssetsList, pdAssetsPanel, pdSprintNotice */

// ========================================
// ASSETS LIST
// ========================================

// The catalogue of prompt assets a later sprint will drag onto the canvas.
// It is EMPTY on purpose: the approved design shows the Assets panel bare,
// and shipping invented rows would promise a catalogue that does not exist.
// Push entries of the shape { name, gradient } here to populate it — the
// renderer below is already written for them.
const PD_ASSET_ITEMS = [];

/**
 * Paint the Assets panel from PD_ASSET_ITEMS.
 *
 * With the list empty this renders nothing and the panel stays bare, exactly
 * as designed. Every row it does paint answers with the sprint notice.
 */
function renderPromptAssetsList() {
    if (!pdAssetsList) return;
    pdAssetsList.innerHTML = '';

    PD_ASSET_ITEMS.forEach((asset) => {
        const item = document.createElement('div');
        item.classList.add('asset-item');
        item.setAttribute('data-asset-name', asset.name);
        item.setAttribute('title', asset.name);

        const icon = document.createElement('div');
        icon.classList.add('asset-item-icon');
        if (asset.gradient) icon.style.background = asset.gradient;

        const label = document.createElement('span');
        label.textContent = asset.name;

        item.appendChild(icon);
        item.appendChild(label);
        item.addEventListener('click', (event) => {
            pdSprintNotice(`Assets ▸ ${asset.name}`, event);
        });

        pdAssetsList.appendChild(item);
    });
}

function initPromptDesignerAssets() {              // eslint-disable-line no-unused-vars
    renderPromptAssetsList();

    // The panel itself answers too. While the catalogue is empty there is no
    // row to press, and a panel that stays silent reads as a dead page rather
    // than as a feature that has not landed yet.
    if (pdAssetsPanel) {
        pdAssetsPanel.addEventListener('click', (event) => {
            if (event.target.closest && event.target.closest('.asset-item')) return;
            pdSprintNotice('Assets panel', event);
        });
    }

    console.log(`--- [PROMPT-DESIGNER] Assets panel wired (${PD_ASSET_ITEMS.length} assets)`);
}
