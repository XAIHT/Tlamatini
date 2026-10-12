/* Tlamatini Author Banner — Angela López Mendoza */
(() => {
    'use strict';
    // Layout adapters own measurements/persistence. This owns the gesture,
    // including an interrupted drag over a PDF frame or outside the window.
    function bindPointer({ element, resizingClass, onMove, before = () => {} }) {
        let pointerId = null;
        function stop() {
            if (pointerId === null) return;
            const previous = pointerId;
            pointerId = null;
            element.removeAttribute('data-resizing');
            document.body.classList.remove(resizingClass);
            if (element.hasPointerCapture(previous)) element.releasePointerCapture(previous);
        }
        element.style.touchAction = 'none';
        element.addEventListener('pointerdown', event => {
            if (pointerId !== null || !event.isPrimary || event.button !== 0) return;
            before();
            element.setPointerCapture(event.pointerId);
            pointerId = event.pointerId;
            element.focus({ preventScroll: true });
            element.setAttribute('data-resizing', '');
            document.body.classList.add(resizingClass);
            event.preventDefault();
        });
        element.addEventListener('pointermove', event => {
            if (event.pointerId !== pointerId) return;
            if (event.pointerType === 'mouse' && !(event.buttons & 1)) { stop(); return; }
            onMove(event);
        });
        ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => {
            element.addEventListener(type, event => { if (event.pointerId === pointerId) stop(); });
        });
        window.addEventListener('blur', stop);
        window.addEventListener('pagehide', stop);
        document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
        document.addEventListener('keydown', event => { if (event.key === 'Escape') stop(); });
        return stop;
    }
    function bind({ element, value, atPointer, apply, before = () => {}, axis = 'x', keyDirection = 1, min, max }) {
        bindPointer({ element, before, resizingClass: axis === 'y' ? 'resizing-vertical' : 'resizing',
            onMove: event => apply(atPointer(axis === 'y' ? event.clientY : event.clientX)) });
        const keys = axis === 'y' ? ['ArrowUp', 'ArrowDown'] : ['ArrowLeft', 'ArrowRight'];
        element.addEventListener('keydown', event => {
            if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
            let next;
            if (keys.includes(event.key)) next = value() + (event.key === keys[0] ? -1 : 1) * keyDirection * (event.shiftKey ? 5 : 1);
            else if (event.key === 'Home' && min !== undefined) next = typeof min === 'function' ? min() : min;
            else if (event.key === 'End' && max !== undefined) next = typeof max === 'function' ? max() : max;
            else return;
            event.preventDefault(); before(); apply(next);
        });
    }
    function describe(element, value, min, max, text) {
        element.setAttribute('aria-valuemin', String(min));
        element.setAttribute('aria-valuemax', String(max));
        element.setAttribute('aria-valuenow', String(Math.round(value * 10) / 10));
        element.setAttribute('aria-valuetext', text);
    }
    window.TlmSplitters = Object.freeze({ bindPointer, bind, describe });
})();
