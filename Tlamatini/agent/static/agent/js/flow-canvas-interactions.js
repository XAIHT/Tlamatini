/* Tlamatini — "one who knows"
 * Created by Angela López Mendoza · @angelahack1
 * Tlamatini Author Banner — do not remove */
(() => {
    'use strict';
    const modified = event => event.ctrlKey || event.metaKey;
    const clampZoom = value => Math.max(.25, Math.min(2, Math.round(value * 100) / 100));
    const connectionPath = (sx, sy, tx, ty) => {
        const distance = Math.abs(tx - sx) * .5;
        return `M ${sx} ${sy} C ${sx + distance} ${sy}, ${tx - distance} ${ty}, ${tx} ${ty}`;
    };
    const intersects = (a, b) => !(b.left > a.right || b.right < a.left || b.top > a.bottom || b.bottom < a.top);
    const fitView = (viewport, bounds) => {
        const zoom = clampZoom(Math.min(1, (viewport.clientWidth - 80) / Math.max(1, bounds.right - bounds.left),
            (viewport.clientHeight - 80) / Math.max(1, bounds.bottom - bounds.top)));
        return { zoom, left: Math.max(0, bounds.left * zoom - 40), top: Math.max(0, bounds.top * zoom - 40) };
    };
    const isTyping = event => event.defaultPrevented || event.isComposing ||
        event.target.closest('input, textarea, select, [contenteditable="true"], .ui-dialog') ||
        [...document.querySelectorAll('.ui-dialog')].some(dialog => dialog.getClientRects().length);
    function showMenu(menu, x, y) {
        menu.style.left = '0px'; menu.style.top = '0px'; menu.style.display = 'block';
        const rect = menu.getBoundingClientRect();
        menu.style.left = Math.min(Math.max(x, 8), Math.max(8, window.innerWidth - rect.width - 8)) + 'px';
        menu.style.top = Math.min(Math.max(y, 8), Math.max(8, window.innerHeight - rect.height - 8)) + 'px';
    }
    function bindDivider({ element, value, atPointer, apply, before }) {
        let pointerId = null;
        function end() {
            if (pointerId === null) return;
            const previous = pointerId; pointerId = null;
            document.body.classList.remove('resizing');
            if (element.hasPointerCapture(previous)) element.releasePointerCapture(previous);
        }
        element.style.touchAction = 'none';
        element.addEventListener('pointerdown', event => {
            if (event.button !== 0) return;
            event.preventDefault(); before(); pointerId = event.pointerId;
            element.setPointerCapture(pointerId); document.body.classList.add('resizing');
        });
        document.addEventListener('pointermove', event => { if (pointerId === event.pointerId) apply(atPointer(event.clientX)); });
        document.addEventListener('pointerup', end);
        document.addEventListener('pointercancel', end);
        element.addEventListener('lostpointercapture', end);
        window.addEventListener('blur', end);
        document.addEventListener('keydown', event => { if (event.key === 'Escape') end(); });
        element.addEventListener('keydown', event => {
            if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
            event.preventDefault(); before(); apply(value() + (event.key === 'ArrowLeft' ? -1 : 1));
        });
    }

    // Both editors use this gesture lifecycle. Adapters own graph validation and
    // persistence; pointer capture, highlighting and cancellation are identical.
    function connectionDrag({ viewport, canEdit, targetAt, begin, move, complete, dispose }) {
        let active = null;
        function clear(keepPreview = false) {
            if (!active) return false;
            const previous = active; active = null;
            previous.port.classList.remove('connecting-source');
            previous.target?.classList.remove('connecting-target');
            dispose(previous.data, keepPreview);
            if (previous.pointerId !== undefined && viewport.hasPointerCapture(previous.pointerId)) {
                viewport.releasePointerCapture(previous.pointerId);
            }
            return true;
        }
        function finish(target) {
            if (!active) return;
            let keepPreview = false;
            try { if (target && canEdit()) keepPreview = complete(active.data, target) === true; }
            finally { clear(keepPreview); }
        }
        function start(port, pointerId) {
            clear();
            if (!canEdit()) return;
            const data = begin(port);
            active = { port, pointerId, data, target: null };
            port.classList.add('connecting-source');
            if (pointerId !== undefined) viewport.setPointerCapture(pointerId);
        }
        document.addEventListener('pointermove', event => {
            if (!active || active.pointerId !== event.pointerId) return;
            if (!canEdit() || !active.port.isConnected) { clear(); return; }
            move(active.data, event);
            const target = targetAt(event);
            if (active.target !== target) {
                active.target?.classList.remove('connecting-target');
                target?.classList.add('connecting-target');
                active.target = target;
            }
        });
        document.addEventListener('pointerup', event => {
            if (active?.pointerId === event.pointerId) finish(targetAt(event));
        });
        document.addEventListener('pointercancel', () => clear());
        viewport.addEventListener('lostpointercapture', () => clear());
        window.addEventListener('blur', () => clear());
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && active) { event.preventDefault(); clear(); }
        });
        return { start, finish, cancel: () => clear(), get active() { return active; } };
    }
    window.FlowCanvasInteractions = Object.freeze({ modified, clampZoom, connectionPath, intersects, fitView, isTyping, showMenu, bindDivider, connectionDrag });
})();
