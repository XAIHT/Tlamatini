/* Tlamatini Author Banner — Angela López Mendoza */
/* global loadSelectedCanvasFile */
/* Read-only Markdown presentation. The source code element remains authoritative
 * for context/copy; the original File remains authoritative for Save. */
(() => {
    'use strict';
    const host = document.getElementById('markdown-canvas-host');
    const article = document.getElementById('markdown-canvas-document');
    const toolbar = document.getElementById('markdown-canvas-toolbar');
    const previewButton = document.getElementById('markdown-preview-button');
    const sourceButton = document.getElementById('markdown-source-button');
    const folderButton = document.getElementById('markdown-folder-button');
    const folderInput = document.getElementById('markdown-folder-input');
    const status = document.getElementById('markdown-canvas-status');
    const editor = document.getElementById('editor-container');
    const allowedTags = 'a abbr b blockquote br caption code col colgroup dd del details div dl dt em h1 h2 h3 h4 h5 h6 hr i img input ins kbd li mark ol p pre s small span strong sub summary sup table tbody td tfoot th thead tr u ul'.split(' ');
    let current = null;
    let serial = 0;

    function revokeImages() {
        current?.urls.forEach(url => URL.revokeObjectURL(url));
        if (current) current.urls = [];
    }

    function close() {
        if (!current) return;
        revokeImages();
        current = null;
        article.replaceChildren();
        status.textContent = '';
        folderInput.value = '';
        host.hidden = toolbar.hidden = true;
        editor.hidden = false;
    }

    function selectView(preview) {
        if (!current) return;
        host.hidden = !preview;
        editor.hidden = preview;
        previewButton.setAttribute('aria-pressed', String(preview));
        sourceButton.setAttribute('aria-pressed', String(!preview));
    }

    function localPath(value) {
        try {
            const path = decodeURIComponent(value.split(/[?#]/)[0]).replace(/\\/g, '/');
            if (/^(?:\/|[a-z][a-z\d+.-]*:)/i.test(path)) return null;
            const parts = current.base ? current.base.split('/') : [];
            for (const part of path.split('/')) {
                if (part === '..') { if (!parts.length) return null; parts.pop(); }
                else if (part && part !== '.') parts.push(part);
            }
            return parts.join('/');
        } catch (_) { return null; }
    }

    function resource(value) {
        const path = localPath(value);
        return path === null ? null : current.files.get(path);
    }

    function externalUrl(value, image = false) {
        try {
            const url = new URL(value);
            if (['https:', 'http:'].includes(url.protocol)) return url.href;
            if (!image && url.protocol === 'mailto:') return url.href;
            if (image && /^data:image\/(?:png|jpeg|gif|webp|avif|bmp);base64,/i.test(value)) return value;
        } catch (_) { /* Relative URLs need explicitly selected local files. */ }
        return null;
    }

    function imagePlaceholder(img, message) {
        const placeholder = document.createElement('span');
        placeholder.className = 'markdown-missing-image';
        placeholder.textContent = `${img.alt || 'Image'} — ${message}`;
        img.replaceWith(placeholder);
    }

    async function openLocalLink(state, file, event) {
        event.preventDefault();
        if (current !== state) return;
        await loadSelectedCanvasFile(file);
        if (current?.file !== file) return;
        current.files = state.files;
        const path = [...state.files].find(([, value]) => value === file)?.[0] || '';
        current.base = path.split('/').slice(0, -1).join('/');
        render();
    }

    function render() {
        const state = current;
        revokeImages();
        try {
            if (!window.marked?.parse || !window.DOMPurify?.sanitize) {
                throw new Error('The Markdown renderer could not load. The complete source is available.');
            }
            const fragment = window.DOMPurify.sanitize(window.marked.parse(state.source, {
                gfm: true, breaks: false, async: false,
            }), {
                ALLOWED_TAGS: allowedTags,
                ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'id', 'class', 'align', 'width', 'height',
                    'start', 'colspan', 'rowspan', 'open', 'type', 'checked', 'disabled'],
                ALLOW_DATA_ATTR: false, ALLOW_ARIA_ATTR: false,
                RETURN_DOM_FRAGMENT: true,
            });
            const anchors = new Map();
            const used = new Set();
            let needsFolder = false;
            for (const element of fragment.querySelectorAll('*')) {
                // File-supplied classes must never opt into application styles.
                const language = element.tagName === 'CODE'
                    ? [...element.classList].find(name => /^language-[\w+-]+$/.test(name)) : null;
                element.removeAttribute('class');
                if (language) element.classList.add(language);
                if (element.id || /^H[1-6]$/.test(element.tagName)) {
                    const original = element.id || element.textContent.trim().toLowerCase()
                        .replace(/[^\p{L}\p{N}_\-\s]/gu, '').replace(/\s/g, '-');
                    let slug = original || 'section';
                    let count = 0;
                    while (used.has(slug)) slug = `${original || 'section'}-${++count}`;
                    used.add(slug);
                    element.id = `tlm-md-${state.id}-${slug}`;
                    if (!anchors.has(original)) anchors.set(original, element.id);
                    anchors.set(slug, element.id);
                }
                if (element.tagName === 'INPUT') {
                    if (element.type !== 'checkbox') { element.remove(); continue; }
                    element.disabled = true;
                    element.setAttribute('aria-label', element.checked ? 'Completed task' : 'Incomplete task');
                    element.parentElement?.classList.add('markdown-task');
                }
            }
            for (const link of fragment.querySelectorAll('a')) {
                const href = link.getAttribute('href') || '';
                link.removeAttribute('href');
                if (href.startsWith('#')) {
                    let key;
                    try { key = decodeURIComponent(href.slice(1)); } catch (_) { key = href.slice(1); }
                    const target = anchors.get(key);
                    if (target) {
                        link.href = `#${target}`;
                        link.addEventListener('click', event => {
                            event.preventDefault();
                            const heading = document.getElementById(target);
                            heading?.scrollIntoView({ block: 'start' });
                            if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
                        });
                    }
                } else if (externalUrl(href)) {
                    link.href = externalUrl(href);
                    link.target = '_blank';
                    link.rel = 'noopener noreferrer';
                } else if (href && localPath(href) !== null) {
                    const file = resource(href);
                    if (file && /\.(md|markdown)$/i.test(file.name)) {
                        link.href = '#';
                        link.addEventListener('click', openLocalLink.bind(null, state, file));
                    } else {
                        needsFolder = true;
                        link.title = `Local link: ${href}. Choose its folder to open Markdown files.`;
                        link.classList.add('markdown-local-link');
                    }
                }
            }
            for (const img of fragment.querySelectorAll('img')) {
                const src = img.getAttribute('src') || '';
                img.removeAttribute('src');
                const file = resource(src);
                const remote = externalUrl(src, true);
                if (file && /\.(png|jpe?g|gif|webp|avif|bmp|svg)$/i.test(file.name)) {
                    const url = URL.createObjectURL(file);
                    state.urls.push(url);
                    img.src = url;
                } else if (remote) {
                    img.src = remote;
                    img.referrerPolicy = 'no-referrer';
                } else {
                    needsFolder = true;
                    imagePlaceholder(img, `choose the document folder to load ${src || 'this image'}`);
                    continue;
                }
                img.loading = 'lazy';
                img.addEventListener('error', () => imagePlaceholder(img, 'image could not be loaded'), { once: true });
            }
            for (const table of [...fragment.querySelectorAll('table')]) {
                const scroll = document.createElement('div');
                scroll.className = 'markdown-table-scroll';
                scroll.tabIndex = 0;
                scroll.setAttribute('role', 'region');
                scroll.setAttribute('aria-label', 'Markdown table; scroll horizontally if needed');
                table.replaceWith(scroll);
                scroll.append(table);
            }
            article.replaceChildren(fragment);
            for (const code of article.querySelectorAll('pre > code')) {
                const language = [...code.classList].find(name => name.startsWith('language-'))?.slice(9);
                if (language && window.hljs?.getLanguage(language)) window.hljs.highlightElement(code);
            }
            status.textContent = needsFolder
                ? 'Local images or links need their folder. Choose folder keeps files on this device.'
                : (state.source.trim() ? '' : 'This Markdown file is empty.');
            status.hidden = !status.textContent;
            folderButton.hidden = !needsFolder && !state.files.size;
            previewButton.disabled = false;
            return true;
        } catch (error) {
            console.error('[Markdown canvas]', error);
            const source = document.createElement('pre');
            source.textContent = state.source;
            article.replaceChildren(source);
            status.textContent = `${error.message} Select Source to read the file.`;
            status.hidden = false;
            return false;
        }
    }

    function open(name, source, file = null) {
        close();
        current = { name, source, file, id: ++serial, files: new Map(), base: '', urls: [] };
        toolbar.hidden = false;
        render();
        selectView(true);
        host.scrollTop = 0;
    }

    previewButton.addEventListener('click', () => selectView(true));
    sourceButton.addEventListener('click', () => selectView(false));
    folderButton.addEventListener('click', () => {
        const state = current;
        folderInput.value = '';
        folderInput.onchange = () => {
            if (current !== state || !folderInput.files.length) return;
            state.files = new Map([...folderInput.files].map(file => [
                file.webkitRelativePath.split('/').slice(1).join('/'), file,
            ]));
            const matches = [...state.files.keys()].filter(path => path.split('/').pop() === state.name.split(/[\\/]/).pop());
            state.base = matches.length === 1 ? matches[0].split('/').slice(0, -1).join('/') : '';
            render();
        };
        folderInput.click();
    });
    window.TlamatiniMarkdownCanvas = {
        open, close,
        // Refresh preserves the selected view, reading position and explicitly
        // selected local resources while rerendering the complete new source.
        snapshot: () => current ? { files: current.files, base: current.base,
            preview: !host.hidden, top: host.scrollTop, left: host.scrollLeft } : null,
        restore: state => {
            if (!current || !state) return;
            current.files = state.files;
            current.base = state.base;
            render();
            selectView(state.preview);
            host.scrollTop = state.top;
            host.scrollLeft = state.left;
        },
        updateFile: file => { if (current) current.file = file; },
        get active() { return current !== null; },
        get file() { return current?.file || null; },
        get name() { return current?.name || ''; },
    };
})();
