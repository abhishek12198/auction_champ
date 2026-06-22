/* Fixture Drag-and-Drop board for the Team Pool Wizard.
 * Reads fixture data from <textarea id="fixture-data"> (embedded by action_generate_fixture),
 * renders interactive match cards in #fixture_dnd_container, and handles
 * drag-to-reorder + png snapshot download.
 */
(function () {
    'use strict';

    var DARK   = '#0d0d2b';
    var GOLD   = '#FFD54F';
    var PANEL  = 'rgba(255,255,255,0.07)';
    var BORDER = 'rgba(255,213,79,0.22)';

    // ── Helpers ──────────────────────────────────────────────────────────────
    function esc(s) {
        return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function getPayload() {
        var el = document.getElementById('fixture-data');
        if (!el) return null;
        try { return JSON.parse(el.value || el.textContent); }
        catch (e) { return null; }
    }

    var SECTION_COLORS = ['#1565C0','#B71C1C','#2E7D32','#6A1B9A','#E65100','#006064','#880E4F','#37474F'];

    // ── Section header (non-draggable, spans full width) ─────────────────────
    function makeSectionHeader(label, color) {
        var hdr = document.createElement('div');
        hdr.style.cssText = [
            'grid-column:1/-1',
            'color:' + color,
            'font-size:.8rem',
            'font-weight:800',
            'letter-spacing:3px',
            'text-transform:uppercase',
            'padding:7px 12px',
            'border-left:4px solid ' + color,
            'background:rgba(255,255,255,0.04)',
            'border-radius:0 6px 6px 0',
            'margin-top:10px',
        ].join(';');
        hdr.textContent = label;
        return hdr;
    }
    function logoEl(team, size) {
        size = size || 26;
        var el;
        if (team.logo) {
            el = document.createElement('img');
            el.src = 'data:image/png;base64,' + team.logo;
            el.style.cssText = 'height:' + size + 'px;width:' + size + 'px;object-fit:contain;border-radius:4px;flex-shrink:0;display:block;';
        } else {
            el = document.createElement('span');
            el.textContent = team.initials || '??';
            el.style.cssText = 'display:inline-flex;height:' + size + 'px;width:' + size + 'px;background:#ffffff28;border-radius:4px;font-size:9px;font-weight:800;color:#fff;align-items:center;justify-content:center;flex-shrink:0;';
        }
        return el;
    }

    // ── Build a card using CSS Grid for perfect column alignment ─────────────
    //
    //  Grid columns:  [M#] [logo] [name-a ......] [VS] [......name-b] [logo] [⠿]
    //                  42px  30px     1fr          36px      1fr        30px  20px
    //  Row 2:          span 2-6  →  group label (dimmed, small)
    //
    function makeCard(match, idx) {
        var card = document.createElement('div');
        card.className = 'fmc';
        card.draggable = true;
        card.style.cssText = [
            'display:grid',
            'grid-template-columns:42px 30px 1fr 36px 1fr 30px 20px',
            'grid-template-rows:28px 16px',
            'align-items:center',
            'column-gap:6px',
            'row-gap:2px',
            'background:' + PANEL,
            'border:1px solid ' + BORDER,
            'border-radius:10px',
            'padding:10px 12px',
            'cursor:grab',
            'user-select:none',
            'box-sizing:border-box',
            'transition:box-shadow .12s,opacity .12s',
            'min-width:0',
        ].join(';');

        // Col 1 row 1 — Match number badge
        var num = document.createElement('span');
        num.className = 'fmc-n';
        num.textContent = 'M' + (idx + 1);
        num.style.cssText = 'color:' + GOLD + ';font-size:.65rem;font-weight:800;text-align:center;background:rgba(255,213,79,0.13);border-radius:4px;padding:2px 4px;grid-area:1/1;align-self:center;white-space:nowrap;';

        // Col 2 row 1 — Team A logo
        var logoA = logoEl(match.team_a);
        logoA.style.cssText += 'grid-area:1/2;align-self:center;justify-self:center;';

        // Col 3 row 1 — Team A name
        var nameA = document.createElement('span');
        nameA.textContent = match.team_a.name;
        nameA.style.cssText = 'color:#fff;font-size:.8rem;font-weight:600;grid-area:1/3;align-self:center;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';

        // Col 4 row 1 — VS
        var vs = document.createElement('span');
        vs.textContent = 'VS';
        vs.style.cssText = 'color:' + GOLD + ';font-weight:900;font-size:.82rem;grid-area:1/4;text-align:center;align-self:center;';

        // Col 5 row 1 — Team B name (right-aligned)
        var nameB = document.createElement('span');
        nameB.textContent = match.team_b.name;
        nameB.style.cssText = 'color:#fff;font-size:.8rem;font-weight:600;grid-area:1/5;align-self:center;text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';

        // Col 6 row 1 — Team B logo
        var logoB = logoEl(match.team_b);
        logoB.style.cssText += 'grid-area:1/6;align-self:center;justify-self:center;';

        // Col 7 row 1 — Drag handle
        var handle = document.createElement('span');
        handle.textContent = '⠿';
        handle.style.cssText = 'color:#555;font-size:.85rem;text-align:center;grid-area:1/7;align-self:center;cursor:grab;';

        // Col 2-7 row 2 — Group label
        var grp = document.createElement('span');
        grp.textContent = match.group || '';
        grp.style.cssText = 'color:#555;font-size:.6rem;letter-spacing:.5px;grid-area:2/2/3/8;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;align-self:center;';

        card.appendChild(num);
        card.appendChild(logoA);
        card.appendChild(nameA);
        card.appendChild(vs);
        card.appendChild(nameB);
        card.appendChild(logoB);
        card.appendChild(handle);
        card.appendChild(grp);
        return card;
    }

    // ── Renumber all cards sequentially ──────────────────────────────────────
    function renumber(container) {
        container.querySelectorAll('.fmc').forEach(function (c, i) {
            var n = c.querySelector('.fmc-n');
            if (n) n.textContent = 'M' + (i + 1);
        });
    }

    // ── Drag-and-drop ─────────────────────────────────────────────────────────
    function setupDnD(container) {
        var dragging = null;
        var ph = null;

        function makePh(ref) {
            var p = document.createElement('div');
            p.style.cssText = 'border:2px dashed ' + GOLD + ';border-radius:10px;background:rgba(255,213,79,0.05);box-sizing:border-box;height:' + ref.offsetHeight + 'px;';
            return p;
        }

        container.addEventListener('dragstart', function (e) {
            var card = e.target.closest('.fmc');
            if (!card) return;
            dragging = card;
            dragging.style.opacity = '0.3';
            dragging.style.boxShadow = '0 0 0 2px ' + GOLD;
            ph = makePh(dragging);
            e.dataTransfer.effectAllowed = 'move';
        });

        container.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            if (!dragging || !ph) return;
            var target = e.target.closest('.fmc');
            if (!target || target === dragging) return;
            var rect = target.getBoundingClientRect();
            container.insertBefore(ph, e.clientX < rect.left + rect.width / 2 ? target : target.nextSibling);
        });

        container.addEventListener('drop', function (e) {
            e.preventDefault();
            if (!dragging || !ph || !ph.parentNode) return;
            container.insertBefore(dragging, ph);
            cleanup(); renumber(container);
        });

        container.addEventListener('dragend', cleanup);

        function cleanup() {
            if (dragging) { dragging.style.opacity = ''; dragging.style.boxShadow = ''; }
            if (ph && ph.parentNode) ph.parentNode.removeChild(ph);
            dragging = null; ph = null;
        }
    }

    // ── Full render ───────────────────────────────────────────────────────────
    function render() {
        var container = document.getElementById('fixture_dnd_container');
        if (!container) return;
        if (container.querySelector('.fmc')) return; // already rendered

        var payload = getPayload();
        if (!payload || !payload.matches || !payload.matches.length) return;

        container.innerHTML = '';
        container.style.cssText = [
            'background:' + DARK,
            'border-radius:14px',
            'padding:20px',
            'display:grid',
            'grid-template-columns:repeat(auto-fill,minmax(360px,1fr))',
            'gap:8px',
            'min-height:80px',
            'font-family:Segoe UI,Arial,sans-serif',
        ].join(';');

        // Header spanning all columns
        var hdr = document.createElement('div');
        hdr.style.cssText = 'grid-column:1/-1;text-align:center;margin-bottom:8px;';
        hdr.innerHTML = (
            '<div style="color:' + GOLD + ';font-size:1.1rem;font-weight:800;letter-spacing:5px;text-transform:uppercase;">' + esc(payload.tournament || '') + '</div>' +
            '<div style="color:#888;font-size:.72rem;letter-spacing:2px;margin-top:3px;text-transform:uppercase;">' + esc(payload.subtitle || '') + '</div>' +
            '<div style="width:60px;height:3px;background:' + GOLD + ';margin:8px auto 0;border-radius:2px;"></div>'
        );
        container.appendChild(hdr);

        // Group matches by section (preserving order)
        var sections = [];
        var sectionMap = {};
        payload.matches.forEach(function (match) {
            var sec = match.section || match.group;
            if (!sectionMap[sec]) { sectionMap[sec] = []; sections.push(sec); }
            sectionMap[sec].push(match);
        });

        // Render section header → cards per section
        var matchIdx = 0;
        sections.forEach(function (sec, si) {
            var color = SECTION_COLORS[si % SECTION_COLORS.length];
            container.appendChild(makeSectionHeader(sec, color));
            sectionMap[sec].forEach(function (match) {
                container.appendChild(makeCard(match, matchIdx++));
            });
        });

        // Footer spanning all columns
        var footer = document.createElement('div');
        footer.style.cssText = 'grid-column:1/-1;text-align:right;color:#444;font-size:.68rem;margin-top:4px;letter-spacing:.5px;';
        footer.textContent = 'Total: ' + payload.matches.length + ' matches  •  drag cards to reorder';
        container.appendChild(footer);

        setupDnD(container);
    }

    // ── Snapshot / download ───────────────────────────────────────────────────
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('.o_take_fixture_snapshot');
        if (!btn) return;
        e.preventDefault();

        var container = document.getElementById('fixture_dnd_container');
        if (!container || !container.querySelector('.fmc')) {
            alert('Generate a fixture first.');
            return;
        }

        var clone = document.createElement('div');
        clone.style.cssText = 'position:fixed;top:0;left:-99999px;width:980px;padding:28px;background:' + DARK + ';display:block;z-index:-9999;box-sizing:border-box;font-family:Segoe UI,Arial,sans-serif;';
        clone.innerHTML = container.outerHTML;
        clone.querySelectorAll('[draggable]').forEach(function (el) { el.removeAttribute('draggable'); });
        document.body.appendChild(clone);
        void clone.offsetHeight;

        var orig = btn.innerHTML;
        btn.innerHTML = '⏳ Generating...';
        btn.style.pointerEvents = 'none';

        html2canvas(clone, {
            scale: 2, backgroundColor: DARK,
            useCORS: true, allowTaint: true,
            logging: false, imageTimeout: 0,
        }).then(function (canvas) {
            document.body.removeChild(clone);
            btn.innerHTML = orig; btn.style.pointerEvents = '';
            var a = document.createElement('a');
            a.href = canvas.toDataURL('image/png');
            a.download = 'fixture_schedule.png';
            document.body.appendChild(a); a.click(); document.body.removeChild(a);
        }).catch(function (err) {
            if (document.body.contains(clone)) document.body.removeChild(clone);
            btn.innerHTML = orig; btn.style.pointerEvents = '';
            console.error('Fixture snapshot error:', err);
            alert('Snapshot failed — see browser console for details.');
        });
    });

    // ── Auto-init ─────────────────────────────────────────────────────────────
    var observer = new MutationObserver(function () {
        if (document.getElementById('fixture-data') && document.getElementById('fixture_dnd_container')) {
            render();
        }
    });

    function startObserver() {
        if (document.body) {
            observer.observe(document.body, { childList: true, subtree: true });
        }
        render();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startObserver);
    } else {
        startObserver();
    }
})();

