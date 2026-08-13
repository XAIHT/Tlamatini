/*
 * release_notes_renderer.js — renders GitHub RELEASE NOTES (Markdown + the raw
 * HTML GitHub itself injects) into real HTML for the "About ▸ Check for
 * updates" dialog.
 *
 * WHY THIS EXISTS (Angela, 2026-08-13): the dialog used to do
 *     notes.textContent = data.notes;
 * into a <pre>, so a release note arrived on screen as LITERAL SOURCE —
 * "## What's New", a full `<img width="1560" ... src="https://github.com/
 * user-attachments/assets/…" />` tag, and `[v1.42.0](https://…)` — instead of
 * a heading, the screenshot and a clickable link. The release notes are the
 * one place the user is told WHAT the update actually changes; showing them as
 * markup is the same as not showing them.
 *
 * CONTRACT (do NOT weaken):
 *  1. SANITIZE BY WHITELIST, never by blacklist. Everything is escaped first;
 *     only known-safe tags are then re-materialised, and each one is REBUILT
 *     from a whitelist of attributes — an attribute we do not know is dropped,
 *     so `onerror=`/`onload=` can never survive. <script>/<style> bodies are
 *     removed outright before anything else runs.
 *  2. URLs are validated: javascript:, vbscript: and non-image data: are
 *     rejected. A rejected URL yields no tag at all.
 *  3. FAIL-OPEN, never fail-blank: any exception in render() falls back to the
 *     plain escaped text, so a malformed release note still SHOWS something.
 *     A renderer that can blank the notes is worse than the raw markup it fixes.
 *  4. GitHub "user-attachments/assets/<uuid>" URLs carry NO extension and may
 *     be EITHER an image or a video. They are emitted as <img> tagged
 *     data-rn-fallback="video"; mount() swaps the element to <video controls>
 *     on the load error. That is what makes a release-note VIDEO play here.
 *  5. No inline event handlers are ever written into the HTML (CSP-safe) —
 *     mount() attaches every listener from JS after insertion.
 *
 * Self-contained IIFE: declares NO cross-file globals, exposes exactly one
 * namespace, window.TlamatiniReleaseNotes = { render, mount }.
 */
(function () {
    'use strict';

    // Tags we re-materialise. Value = whitelist of attributes kept.
    var ALLOWED = {
        a: ['href', 'title'],
        img: ['src', 'alt', 'title', 'width', 'height'],
        video: ['src', 'poster', 'width', 'height', 'controls', 'loop', 'muted', 'autoplay'],
        source: ['src', 'type'],
        p: [], br: [], hr: [], b: [], strong: [], i: [], em: [], u: [], s: [], del: [], ins: [],
        ul: [], ol: ['start'], li: [], dl: [], dt: [], dd: [],
        h1: [], h2: [], h3: [], h4: [], h5: [], h6: [],
        blockquote: [], pre: [], code: [], kbd: [], sub: [], sup: [], small: [], span: [],
        div: [], details: ['open'], summary: [],
        table: [], thead: [], tbody: [], tfoot: [], tr: [], th: ['colspan', 'rowspan'],
        td: ['colspan', 'rowspan'], caption: []
    };
    var BOOLEAN_ATTRS = ['controls', 'loop', 'muted', 'autoplay', 'open'];
    var VOID_TAGS = ['br', 'hr', 'img', 'source'];

    var VIDEO_EXT = /\.(mp4|webm|mov|m4v|ogv|ogg)(\?|#|$)/i;
    var IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg|bmp|avif|ico)(\?|#|$)/i;
    // GitHub-hosted media with no extension — could be a picture OR a clip.
    var GH_ASSET = /(user-attachments\/assets\/|githubusercontent\.com\/)/i;

    var MARK = '\u0000';           // placeholder sentinel — never present in real notes
    var TOKEN_RE = /\u0000(\d+)\u0000/g;

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function attrValue(value) {
        // The value already went through escapeHtml (so & is &amp;); only the
        // quote that would close the attribute still has to go.
        return String(value).replace(/"/g, '&quot;');
    }

    function safeUrl(url) {
        var raw = String(url || '').trim().replace(/\s+/g, '');
        if (!raw) return '';
        var probe = raw.replace(/&amp;/gi, '&').toLowerCase();
        if (/^javascript:/.test(probe) || /^vbscript:/.test(probe) || /^file:/.test(probe)) return '';
        if (/^data:/.test(probe) && !/^data:image\//.test(probe)) return '';
        return raw;
    }

    function isVideoUrl(url) {
        return VIDEO_EXT.test(String(url).replace(/&amp;/gi, '&'));
    }

    function isKnownImage(url) {
        return IMAGE_EXT.test(String(url).replace(/&amp;/gi, '&'));
    }

    /* Build the <img>/<video> for one media URL, honouring the GitHub
     * extensionless case (rule 4 above). */
    function mediaHtml(url, alt, extra) {
        var href = safeUrl(url);
        if (!href) return '';
        var altText = attrValue(alt || '');
        var size = extra || '';
        if (isVideoUrl(href)) {
            return '<video class="rn-media" controls preload="metadata" src="'
                + attrValue(href) + '"' + size + '></video>';
        }
        var fallback = (!isKnownImage(href) && GH_ASSET.test(href.replace(/&amp;/gi, '&')))
            ? ' data-rn-fallback="video"' : '';
        return '<img class="rn-media" src="' + attrValue(href) + '" alt="' + altText + '"'
            + size + fallback + ' loading="lazy">';
    }

    /* Rebuild ONE raw HTML tag from the whitelist. Anything unknown is dropped
     * (returns '') — never echoed back, never trusted. */
    function sanitizeTag(closing, name, attrText) {
        var tag = String(name).toLowerCase();
        if (!Object.prototype.hasOwnProperty.call(ALLOWED, tag)) return '';
        if (closing) return '</' + tag + '>';

        var allowed = ALLOWED[tag];
        var attrs = {};
        var re = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g;
        var match;
        while ((match = re.exec(attrText)) !== null) {
            var key = match[1].toLowerCase();
            if (allowed.indexOf(key) === -1) continue;      // <- drops every on* handler
            var value = match[2] !== undefined ? match[2]
                : match[3] !== undefined ? match[3]
                    : match[4] !== undefined ? match[4] : '';
            attrs[key] = value;
        }

        // An <img>/<video> whose src is extensionless GitHub media gets the
        // same image<->video fallback the markdown path gets.
        if (tag === 'img' || tag === 'video' || tag === 'source') {
            var src = safeUrl(attrs.src);
            if (!src) return '';
            attrs.src = src;
            if (tag === 'img' && isVideoUrl(src)) tag = 'video';
        }
        if (tag === 'a') {
            var href = safeUrl(attrs.href);
            if (!href) { attrs.href = ''; } else { attrs.href = href; }
        }

        var out = '<' + tag;
        Object.keys(attrs).forEach(function (key) {
            if (BOOLEAN_ATTRS.indexOf(key) !== -1) { out += ' ' + key; return; }
            if (!attrs[key]) return;
            out += ' ' + key + '="' + attrValue(attrs[key]) + '"';
        });
        if (tag === 'img' && !isKnownImage(attrs.src || '')
                && GH_ASSET.test(String(attrs.src).replace(/&amp;/gi, '&'))) {
            out += ' data-rn-fallback="video"';
        }
        if (tag === 'video' && attrs.controls === undefined) out += ' controls';
        if (tag === 'img' || tag === 'video') out += ' class="rn-media"';
        out += VOID_TAGS.indexOf(tag) !== -1 ? '>' : '>';
        return out;
    }

    function inline(text) {
        var out = text;
        // ![alt](url) BEFORE [text](url) — an image is a link with a bang.
        out = out.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, function (all, alt, url) {
            return mediaHtml(url, alt, '') || '';
        });
        out = out.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, function (all, label, url) {
            var href = safeUrl(url);
            if (!href) return label;
            return '<a href="' + attrValue(href) + '">' + label + '</a>';
        });
        // Bare URL on its own → clickable (GitHub autolinks these too).
        out = out.replace(/(^|[\s(])((?:https?:\/\/)[^\s<>()"]+)/g, function (all, lead, url) {
            var href = safeUrl(url);
            if (!href) return all;
            return lead + '<a href="' + attrValue(href) + '">' + href + '</a>';
        });
        out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        out = out.replace(/__([^_]+)__/g, '<strong>$1</strong>');
        out = out.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
        out = out.replace(/~~([^~]+)~~/g, '<del>$1</del>');
        return out;
    }

    function renderBlocks(lines) {
        var html = [];
        var paragraph = [];
        var listType = null;

        function flushParagraph() {
            if (!paragraph.length) return;
            html.push('<p>' + inline(paragraph.join('<br>')) + '</p>');
            paragraph = [];
        }
        function closeList() {
            if (listType) { html.push('</' + listType + '>'); listType = null; }
        }

        lines.forEach(function (rawLine) {
            var line = rawLine.replace(/\s+$/, '');
            if (!line.trim()) { flushParagraph(); closeList(); return; }

            var heading = /^(#{1,6})\s+(.*)$/.exec(line);
            if (heading) {
                flushParagraph(); closeList();
                var level = heading[1].length;
                html.push('<h' + level + '>' + inline(heading[2]) + '</h' + level + '>');
                return;
            }
            if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
                flushParagraph(); closeList(); html.push('<hr>'); return;
            }
            // '>' arrives escaped, because escapeHtml already ran.
            var quote = /^\s*&gt;\s?(.*)$/.exec(line);
            if (quote) {
                flushParagraph(); closeList();
                html.push('<blockquote>' + inline(quote[1]) + '</blockquote>');
                return;
            }
            var bullet = /^\s*[-*+]\s+(.*)$/.exec(line);
            var numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line);
            if (bullet || numbered) {
                flushParagraph();
                var want = bullet ? 'ul' : 'ol';
                if (listType !== want) { closeList(); html.push('<' + want + '>'); listType = want; }
                html.push('<li>' + inline((bullet || numbered)[1]) + '</li>');
                return;
            }
            closeList();
            paragraph.push(line);
        });

        flushParagraph();
        closeList();
        return html.join('\n');
    }

    function render(markdown) {
        var source = String(markdown == null ? '' : markdown);
        try {
            var store = [];
            function keep(html) { store.push(html); return MARK + (store.length - 1) + MARK; }

            var text = source.replace(/\r\n?/g, '\n');
            // Executable content is REMOVED, body and all, before anything else.
            text = text.replace(/<script[\s\S]*?<\/script\s*>/gi, '')
                .replace(/<style[\s\S]*?<\/style\s*>/gi, '')
                .replace(/<!--[\s\S]*?-->/g, '');

            // Code first, so nothing inside a code block is ever transformed.
            text = text.replace(/```[ \t]*([\w+-]*)\n([\s\S]*?)```/g, function (all, lang, body) {
                return keep('<pre class="rn-code"><code>' + escapeHtml(body.replace(/\n$/, '')) + '</code></pre>');
            });
            text = text.replace(/`([^`\n]+)`/g, function (all, body) {
                return keep('<code>' + escapeHtml(body) + '</code>');
            });

            text = escapeHtml(text);

            // Re-materialise the whitelisted raw HTML GitHub embeds, then park
            // each rebuilt tag so the markdown pass cannot touch its attributes.
            text = text.replace(/&lt;(\/?)([a-zA-Z][a-zA-Z0-9-]*)([\s\S]*?)&gt;/g,
                function (all, closing, name, attrText) {
                    var tag = sanitizeTag(closing, name, attrText.replace(/&quot;/g, '"'));
                    return tag ? keep(tag) : '';
                });

            var html = renderBlocks(text.split('\n'));

            // Restore placeholders (repeat: a kept tag may sit inside another).
            for (var pass = 0; pass < 4 && html.indexOf(MARK) !== -1; pass++) {
                html = html.replace(TOKEN_RE, function (all, index) {
                    var value = store[Number(index)];
                    return value === undefined ? '' : value;
                });
            }
            return html;
        } catch (err) {
            // FAIL-OPEN: show the notes as plain text rather than nothing.
            if (window.console && console.warn) console.warn('[release-notes] render failed:', err);
            return '<pre class="rn-code">' + escapeHtml(source) + '</pre>';
        }
    }

    /* Insert rendered notes into `el` and wire the runtime behaviour that must
     * NOT live in the HTML string (rule 5): the image→video fallback and
     * new-tab links. */
    function mount(el, markdown) {
        if (!el) return;
        el.innerHTML = render(markdown);
        el.classList.add('rn-rendered');

        Array.prototype.forEach.call(el.querySelectorAll('img[data-rn-fallback="video"]'), function (img) {
            img.addEventListener('error', function () {
                if (img.dataset.rnSwapped === '1') return;
                img.dataset.rnSwapped = '1';
                var video = document.createElement('video');
                video.className = 'rn-media';
                video.controls = true;
                video.preload = 'metadata';
                video.src = img.getAttribute('src');
                if (img.parentNode) img.parentNode.replaceChild(video, img);
            });
        });

        Array.prototype.forEach.call(el.querySelectorAll('a[href]'), function (link) {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        });
    }

    window.TlamatiniReleaseNotes = { render: render, mount: mount };
}());
