/* AuctionChamp organiser manual reader. Logged-in users only. */
(function () {
    'use strict';

    var MANUAL_URL = '/user-manual/document';
    var SCREENSHOT_BASE = '/user-manual/screenshot/';
    var APPENDIX = {
        'revision history': true,
        'copyright': true
    };

    function slugify(text) {
        return String(text || '')
            .toLowerCase()
            .replace(/[^\w\s-]/g, '')
            .trim()
            .replace(/\s+/g, '-')
            .replace(/-+/g, '-');
    }

    function expandFigurePlaceholders(md) {
        return md.replace(
            /╔[=═]+╗\s*\n║\s*📷\s*FIGURE\s+([\d.]+)\s*[—\-]\s*(.+?)\s*║\s*\n║\s*File:\s*(.+?)\s*║[\s\S]*?╚[=═]+╝/gi,
            function (_m, figNo, title, fileLine) {
                var filename = String(fileLine || '').trim().split(/[\/\\]/).pop();
                var caption = String(title || '').trim();
                if (!filename) {
                    return _m;
                }
                var url = SCREENSHOT_BASE + filename;
                return [
                    '',
                    '<figure class="ac-manual-figure">',
                    '  <img src="' + url + '" alt="Figure ' + figNo + ' — ' + caption + '" data-filename="' + filename + '" loading="lazy"/>',
                    '  <figcaption><span>Figure ' + figNo + '</span> ' + caption + '</figcaption>',
                    '</figure>',
                    '',
                ].join('\n');
            }
        );
    }

    function attachImageFallbacks(root) {
        root.querySelectorAll('.ac-manual-figure img').forEach(function (img) {
            img.addEventListener('error', function () {
                var missing = document.createElement('span');
                missing.className = 'ac-manual-figure-missing';
                missing.textContent = 'Screenshot not found: ' + (img.getAttribute('data-filename') || 'image');
                img.replaceWith(missing);
            });
        });
    }

    function takeVersion(content) {
        var chip = document.getElementById('acManualVersion');
        var node = content.firstElementChild;
        while (node && node.tagName !== 'H2') {
            var next = node.nextElementSibling;
            if (node.tagName === 'P' && /version/i.test(node.textContent || '')) {
                var ver = String(node.textContent || '').replace(/.*version:\s*/i, '').trim();
                if (chip && ver) {
                    chip.textContent = 'Version ' + ver;
                }
                node.remove();
            } else if (node.tagName === 'HR') {
                node.remove();
            }
            node = next;
        }
    }

    function decorateHeading(h2) {
        var text = (h2.textContent || '').trim();
        var match = text.match(/^(\d+)\.\s+(.+)$/);
        var label = match ? match[2] : text;
        var num = match ? match[1] : '';
        h2.textContent = '';
        if (num) {
            var badge = document.createElement('span');
            badge.className = 'ac-manual-num';
            badge.textContent = num;
            h2.appendChild(badge);
        }
        if (num) {
            h2.appendChild(document.createTextNode(' '));
        }
        h2.appendChild(document.createTextNode(label));
        return { num: num, label: label, appendix: !!APPENDIX[label.toLowerCase()] };
    }

    function wrapChapters(content) {
        var nodes = Array.prototype.slice.call(content.childNodes);
        var frag = document.createDocumentFragment();
        var chapter = null;
        nodes.forEach(function (node) {
            if (node.nodeType === 1 && node.tagName === 'H2') {
                if (!node.id) {
                    node.id = slugify(node.textContent);
                }
                var info = decorateHeading(node);
                chapter = document.createElement('section');
                chapter.className = 'ac-manual-chapter' + (info.appendix ? ' is-appendix' : '');
                chapter.dataset.label = info.label;
                chapter.dataset.num = info.num;
                chapter.dataset.appendix = info.appendix ? '1' : '0';
                node.id = slugify(info.label);
                chapter.id = 'chapter-' + node.id;
                chapter.appendChild(node);
                frag.appendChild(chapter);
            } else if (chapter) {
                chapter.appendChild(node);
            } else if (node.nodeType === 1 || (node.textContent || '').trim()) {
                frag.appendChild(node);
            }
        });
        content.innerHTML = '';
        content.appendChild(frag);
    }

    function wrapTables(content) {
        content.querySelectorAll('table').forEach(function (table) {
            if (table.parentElement && table.parentElement.classList.contains('ac-manual-table-wrap')) {
                return;
            }
            var wrap = document.createElement('div');
            wrap.className = 'ac-manual-table-wrap';
            table.parentNode.insertBefore(wrap, table);
            wrap.appendChild(table);
        });
    }

    function buildToc(content, tocEl) {
        tocEl.innerHTML = '';
        var chapters = content.querySelectorAll('.ac-manual-chapter');
        var notesTitle = null;
        chapters.forEach(function (chapter) {
            var heading = chapter.querySelector('h2');
            if (!heading) return;
            if (chapter.dataset.appendix === '1' && !notesTitle) {
                notesTitle = document.createElement('div');
                notesTitle.className = 'ac-manual-toc-notes';
                notesTitle.textContent = 'Notes';
                tocEl.appendChild(notesTitle);
            }
            var li = document.createElement('li');
            li.className = 'ac-manual-toc-item';
            var a = document.createElement('a');
            a.href = '#' + heading.id;
            var num = document.createElement('span');
            num.className = 'num';
            num.textContent = chapter.dataset.num || '·';
            var label = document.createElement('span');
            label.textContent = chapter.dataset.label || heading.textContent;
            a.appendChild(num);
            a.appendChild(label);
            a.addEventListener('click', function () {
                document.body.classList.remove('ac-manual-toc-open');
            });
            li.appendChild(a);
            tocEl.appendChild(li);
        });
    }

    function watchChapters(content) {
        var links = document.querySelectorAll('#acManualToc a');
        if (!links.length || !('IntersectionObserver' in window)) return;
        var byId = {};
        links.forEach(function (a) {
            byId[a.getAttribute('href').slice(1)] = a;
        });
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (!entry.isIntersecting) return;
                links.forEach(function (a) { a.classList.remove('is-active'); });
                var link = byId[entry.target.id];
                if (link) {
                    link.classList.add('is-active');
                    if (link.scrollIntoView) {
                        var list = link.closest('.ac-manual-toc');
                        if (list) {
                            var top = link.offsetTop - list.clientHeight / 3;
                            if (top > 0) list.scrollTop = top;
                        }
                    }
                }
            });
        }, { rootMargin: '-15% 0px -70% 0px', threshold: 0.01 });
        content.querySelectorAll('h2').forEach(function (h) { observer.observe(h); });
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
            content.innerHTML = marked.parse(expandFigurePlaceholders(md));
            var firstH1 = content.querySelector('h1');
            if (firstH1) firstH1.remove();
            takeVersion(content);
            wrapChapters(content);
            wrapTables(content);
            attachImageFallbacks(content);
            if (toc) {
                buildToc(content, toc);
                watchChapters(content);
            }
        } catch (err) {
            content.innerHTML = '<p class="ac-manual-error">Could not render the user manual.</p>';
        }
    }

    function boot() {
        var content = document.getElementById('acManualContent');
        var toggle = document.getElementById('acManualChapters');
        var backdrop = document.getElementById('acManualBackdrop');
        if (toggle) {
            toggle.addEventListener('click', function () {
                document.body.classList.toggle('ac-manual-toc-open');
            });
        }
        if (backdrop) {
            backdrop.addEventListener('click', function () {
                document.body.classList.remove('ac-manual-toc-open');
            });
        }
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
