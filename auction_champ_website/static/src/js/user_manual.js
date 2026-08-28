/* AuctionChamp public User Manual page renderer */
(function () {
    'use strict';

    var MANUAL_URL = '/auction_champ_website/static/src/docs/AuctionChamp_User_Manual.md';
    var SCREENSHOT_BASE = '/auction_champ_website/static/src/docs/screenshots/';

    function slugify(text) {
        return String(text || '')
            .toLowerCase()
            .replace(/[^\w\s-]/g, '')
            .trim()
            .replace(/\s+/g, '-')
            .replace(/-+/g, '-');
    }

    function expandFigurePlaceholders(md) {
        // Convert ASCII figure boxes into markdown/HTML image blocks when filename is present
        return md.replace(
            /╔[=═]+╗\s*\n║\s*📷\s*FIGURE\s+([\d.]+)\s*[—\-]\s*(.+?)\s*║\s*\n║\s*File:\s*(.+?)\s*║[\s\S]*?╚[=═]+╝/gi,
            function (_m, figNo, title, fileLine) {
                var filename = String(fileLine || '').trim().split(/[\/\\]/).pop();
                if (!filename) {
                    return _m;
                }
                var url = SCREENSHOT_BASE + filename;
                return [
                    '',
                    '**Figure ' + figNo + ' — ' + title.trim() + '**',
                    '',
                    '<p class="ac-manual-figure">',
                    '  <img class="ac-manual-figure-img" src="' + url + '" alt="Figure ' + figNo + ' — ' + title.trim() + '" data-filename="' + filename + '" loading="lazy"/>',
                    '</p>',
                    '',
                ].join('\n');
            }
        );
    }

    function attachImageFallbacks(root) {
        root.querySelectorAll('img.ac-manual-figure-img').forEach(function (img) {
            img.addEventListener('error', function () {
                var missing = document.createElement('span');
                missing.className = 'ac-manual-figure-missing';
                missing.textContent = 'Screenshot not found: ' + (img.getAttribute('data-filename') || 'image');
                img.replaceWith(missing);
            });
        });
    }

    function buildToc(contentEl, tocEl) {
        tocEl.innerHTML = '';
        var headings = contentEl.querySelectorAll('h2, h3');
        headings.forEach(function (h) {
            if (!h.id) {
                h.id = slugify(h.textContent);
            }
            var li = document.createElement('li');
            li.className = 'ac-manual-toc-item' + (h.tagName === 'H3' ? ' ac-manual-toc-h3' : '');
            var a = document.createElement('a');
            a.href = '#' + h.id;
            a.textContent = h.textContent;
            li.appendChild(a);
            tocEl.appendChild(li);
        });
    }

    function render(md) {
        var content = document.getElementById('acManualContent');
        var toc = document.getElementById('acManualToc');
        if (!content) return;

        if (typeof marked === 'undefined') {
            content.innerHTML = '<p class="ac-manual-error">Markdown renderer failed to load.</p>';
            return;
        }

        try {
            if (marked.setOptions) {
                marked.setOptions({ gfm: true, breaks: false });
            }
            var prepared = expandFigurePlaceholders(md);
            content.innerHTML = marked.parse(prepared);
            // Skip the first H1 (page already has a title)
            var firstH1 = content.querySelector('h1');
            if (firstH1) firstH1.remove();
            attachImageFallbacks(content);
            if (toc) buildToc(content, toc);
        } catch (err) {
            content.innerHTML = '<p class="ac-manual-error">Could not render the user manual.</p>';
        }
    }

    function boot() {
        var content = document.getElementById('acManualContent');
        if (!content) return;
        fetch(MANUAL_URL, { credentials: 'same-origin' })
            .then(function (r) {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.text();
            })
            .then(render)
            .catch(function () {
                content.innerHTML = '<p class="ac-manual-error">User manual document could not be loaded.</p>';
            });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
