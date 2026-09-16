/* Tlamatini Author Banner — Angela López Mendoza */
/* Offline PDF.js viewer. Loaded only inside agent/pdf/canvas.html. */
(() => {
    'use strict';

    const CHANNEL = 'tlamatini-pdf-canvas';
    const status = document.getElementById('pdf-status');
    const pageInput = document.getElementById('pdf-page');
    const pageCount = document.getElementById('pdf-page-count');
    const previous = document.getElementById('pdf-previous');
    const next = document.getElementById('pdf-next');
    const zoom = document.getElementById('pdf-zoom');
    const rotate = document.getElementById('pdf-rotate');
    const scrollMode = document.getElementById('pdf-scroll-mode');
    const passwordForm = document.getElementById('pdf-password-form');
    const passwordInput = document.getElementById('pdf-password');
    const container = document.getElementById('pdf-viewer-container');
    let loadingTask = null;
    let pdfDocument = null;
    let viewer = null;
    let passwordCallback = null;
    let documentPassword = '';
    let opened = false;
    let failed = false;
    let extracting = false;

    function send(type, detail = {}) {
        window.parent.postMessage({ channel: CHANNEL, type, ...detail }, window.location.origin);
    }

    function fail(error) {
        if (failed) return;
        failed = true;
        passwordCallback = null;
        passwordForm.hidden = true;
        status.textContent = `Unable to open PDF: ${error.message || error}. Use Reopen to choose another file.`;
        send('error', { message: status.textContent });
        if (loadingTask) void loadingTask.destroy().catch(() => {});
    }

    function updateNavigation() {
        pageInput.value = viewer.currentPageNumber;
        previous.disabled = viewer.currentPageNumber <= 1;
        next.disabled = viewer.currentPageNumber >= viewer.pagesCount;
    }

    async function open(file) {
        try {
            const pdfjs = await import('../vendor/pdfjs/build/pdf.mjs');
            const { EventBus, PDFViewer, PDFLinkService, LinkTarget } =
                await import('../vendor/pdfjs/web/pdf_viewer.mjs');
            pdfjs.GlobalWorkerOptions.workerSrc = new URL('../vendor/pdfjs/build/pdf.worker.mjs', document.baseURI).href;

            // File.slice reads only requested byte ranges. Never arrayBuffer the
            // whole file, upload it, base64 it, or automatically prefetch its tail.
            class FileRangeTransport extends pdfjs.PDFDataRangeTransport {
                constructor() {
                    super(file.size, new Uint8Array(), true, file.name);
                    this.cancelled = false;
                }
                requestDataRange(begin, end) {
                    file.slice(begin, end).arrayBuffer().then(buffer => {
                        if (!this.cancelled) this.onDataRange(begin, new Uint8Array(buffer));
                    }).catch(error => { if (!this.cancelled) fail(error); });
                }
                abort() { this.cancelled = true; }
            }

            const eventBus = new EventBus();
            const linkService = new PDFLinkService({
                eventBus, externalLinkTarget: LinkTarget.BLANK,
                externalLinkRel: 'noopener noreferrer',
            });
            viewer = new PDFViewer({
                container, viewer: document.getElementById('pdf-viewer'), eventBus, linkService,
                annotationEditorMode: pdfjs.AnnotationEditorType.DISABLE,
                // Display form values/annotations without implying edits are saved.
                annotationMode: pdfjs.AnnotationMode.ENABLE,
                imageResourcesPath: new URL('../vendor/pdfjs/web/images/', document.baseURI).href,
                maxCanvasPixels: 8 * 1024 * 1024,
                maxCanvasDim: 16384,
            });
            linkService.setViewer(viewer);
            eventBus.on('pagesinit', () => {
                viewer.currentScaleValue = 'page-width';
                pageInput.max = pdfDocument.numPages;
                pageCount.textContent = `of ${pdfDocument.numPages}`;
                for (const control of [pageInput, zoom, rotate, scrollMode]) control.disabled = false;
                // PDF.js switches very long documents to single-page scrolling
                // before browser scroll-height limits can make their end unreachable.
                scrollMode.value = String(viewer.scrollMode);
                if (viewer.scrollMode === 3) {
                    scrollMode.querySelector('option[value="0"]').disabled = true;
                }
                updateNavigation();
                status.textContent = '';
                send('ready', { pages: pdfDocument.numPages, password: documentPassword });
            });
            eventBus.on('pagechanging', updateNavigation);
            eventBus.on('pagerendered', event => {
                if (event.error) status.textContent = `Page ${event.pageNumber} could not be rendered: ${event.error.message}`;
            });

            const base = new URL('../vendor/pdfjs/', document.baseURI);
            loadingTask = pdfjs.getDocument({
                range: new FileRangeTransport(),
                rangeChunkSize: 256 * 1024,
                disableAutoFetch: true, disableStream: true,
                cMapUrl: new URL('cmaps/', base).href, cMapPacked: true,
                standardFontDataUrl: new URL('standard_fonts/', base).href,
                wasmUrl: new URL('wasm/', base).href,
                iccUrl: new URL('iccs/', base).href,
                isEvalSupported: false,
                enableXfa: true,
            });
            loadingTask.onPassword = (callback, reason) => {
                passwordCallback = callback;
                document.getElementById('pdf-password-label').textContent =
                    reason === pdfjs.PasswordResponses.INCORRECT_PASSWORD ? 'Incorrect password. Try again:' : 'Password for this PDF';
                passwordForm.hidden = false;
                passwordInput.focus();
            };
            pdfDocument = await loadingTask.promise;
            passwordForm.hidden = true;
            linkService.setDocument(pdfDocument);
            viewer.setDocument(pdfDocument);
            // Initialization failures must not leave a permanently blank canvas.
            await viewer.pagesPromise;
        } catch (error) {
            fail(error);
        }
    }

    async function extractText(requestId) {
        if (!pdfDocument || failed || extracting) {
            send('text-error', { requestId, message: 'PDF is not ready to extract text.' });
            return;
        }
        extracting = true;
        try {
            const pages = [];
            for (let number = 1; number <= pdfDocument.numPages; number++) {
                status.textContent = `Reading text: page ${number} of ${pdfDocument.numPages}…`;
                const page = await pdfDocument.getPage(number);
                const content = await page.getTextContent();
                pages.push(content.items.map(item => (item.str || '') + (item.hasEOL ? '\n' : ' ')).join(''));
                // Cleanup unrendered pages; cleanup safely returns false during rendering.
                if (!viewer.getPageView(number - 1)?.div.querySelector('canvas')) page.cleanup();
            }
            const text = pages.join('\n\n');
            if (!text.trim()) throw new Error('This PDF has no selectable text. Image-only pages require OCR.');
            send('text', { requestId, text });
        } catch (error) {
            send('text-error', { requestId, message: error.message });
        } finally {
            extracting = false;
            status.textContent = '';
        }
    }

    window.addEventListener('message', event => {
        if (event.source !== window.parent || event.origin !== window.location.origin || event.data?.channel !== CHANNEL) return;
        if (event.data.type === 'open' && !opened && event.data.file instanceof File) {
            opened = true;
            void open(event.data.file);
        } else if (event.data.type === 'text') {
            void extractText(event.data.requestId);
        } else if (event.data.type === 'context-status') {
            status.textContent = event.data.message;
        }
    });
    previous.addEventListener('click', () => { viewer.currentPageNumber--; });
    next.addEventListener('click', () => { viewer.currentPageNumber++; });
    pageInput.addEventListener('change', () => {
        const number = Number(pageInput.value);
        if (Number.isInteger(number) && number >= 1 && number <= viewer.pagesCount) viewer.currentPageNumber = number;
        updateNavigation();
    });
    zoom.addEventListener('change', () => { viewer.currentScaleValue = zoom.value; });
    rotate.addEventListener('click', () => { viewer.pagesRotation = (viewer.pagesRotation + 90) % 360; });
    scrollMode.addEventListener('change', () => { viewer.scrollMode = Number(scrollMode.value); });
    passwordForm.addEventListener('submit', event => {
        event.preventDefault();
        const password = passwordInput.value;
        documentPassword = password;
        passwordInput.value = '';
        passwordForm.hidden = true;
        passwordCallback?.(password);
        passwordCallback = null;
    });
    document.getElementById('pdf-password-cancel').addEventListener('click', () => fail(new Error('Password entry cancelled')));
    new ResizeObserver(() => {
        if (viewer?.pagesCount && ['page-width', 'page-fit'].includes(zoom.value)) viewer.currentScaleValue = zoom.value;
    }).observe(container);
    // Parent waits for this handshake, not a timeout or the frame's load event.
    send('initialized');
})();
