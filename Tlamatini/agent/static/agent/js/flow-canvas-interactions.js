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
    // A press remains a native click until movement exceeds four screen pixels.
    // In particular, capturing the viewport on pointerdown retargets click and
    // dblclick away from the node. Both editors share this transaction lifecycle.
    function nodeDrag({ viewport, duplicate, move, finish, failed }) {
        let active = null;
        function release(current) {
            if (viewport.hasPointerCapture(current.pointerId)) viewport.releasePointerCapture(current.pointerId);
        }
        async function settle(current) {
            if (current.pending || current.settling) return;
            current.settling = true;
            try {
                if (current.started) {
                    if (!current.cancelled) move(current.data, current.x - current.startX, current.y - current.startY);
                    await finish(current.data, current.cancelled);
                }
            } catch (error) { failed(error); }
            finally { if (active === current) active = null; release(current); }
        }
        function end(cancelled = false) {
            if (!active) return false;
            const current = active;
            current.ended = true; current.cancelled ||= cancelled;
            release(current);
            void settle(current);
            return true;
        }
        function start(event, data) {
            if (active) return false;
            active = { data, pointerId: event.pointerId, startX: event.clientX, startY: event.clientY,
                x: event.clientX, y: event.clientY, copy: modified(event), started: false,
                pending: false, ended: false, cancelled: false, settling: false };
            return true;
        }
        document.addEventListener('pointermove', async event => {
            const current = active;
            if (!current || current.ended || current.pointerId !== event.pointerId) return;
            current.x = event.clientX; current.y = event.clientY;
            if (current.pending) return;
            if (!current.started) {
                if (Math.hypot(current.x - current.startX, current.y - current.startY) < 4) return;
                current.started = true;
                viewport.setPointerCapture(current.pointerId);
                if (current.copy) {
                    current.pending = true;
                    try { await duplicate(current.data); }
                    catch (error) { current.cancelled = true; current.ended = true; failed(error); }
                    finally { current.pending = false; }
                }
            }
            if (current.ended) { void settle(current); return; }
            move(current.data, current.x - current.startX, current.y - current.startY);
        });
        document.addEventListener('pointerup', event => {
            if (active?.pointerId !== event.pointerId) return;
            active.x = event.clientX; active.y = event.clientY; end();
        });
        document.addEventListener('pointercancel', event => { if (active?.pointerId === event.pointerId) end(true); });
        viewport.addEventListener('lostpointercapture', () => { if (active && !active.ended) end(true); });
        window.addEventListener('blur', () => end(true));
        document.addEventListener('keydown', event => {
            if (event.key === 'Escape' && end(true)) { event.preventDefault(); }
        });
        return { start, cancel: () => end(true), get active() { return active !== null; } };
    }
    window.FlowCanvasInteractions = Object.freeze({ modified, clampZoom, connectionPath, intersects, fitView, isTyping, showMenu, bindDivider, connectionDrag, nodeDrag });
})();
