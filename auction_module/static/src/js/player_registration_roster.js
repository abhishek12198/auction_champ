/* Registered-players popup on /player/register — vanilla JS, no Odoo webclient. */
(function () {
    var openBtn = document.getElementById('regRosterOpen');
    var overlay = document.getElementById('regRosterOverlay');
    var dialog = overlay && overlay.querySelector('.reg-roster-dialog');
    var closeBtn = document.getElementById('regRosterClose');
    var bodyEl = document.getElementById('regRosterBody');
    var searchEl = document.getElementById('regRosterSearch');
    var filtersEl = document.getElementById('regRosterFilters');
    var countEl = document.getElementById('regRosterCount');
    if (!openBtn || !overlay || !bodyEl) {
        return;
    }

    var sseCtl = null;
    var pollTimer = null;
    var popupOpen = false;

    function sseOn() {
        return window.AuctionChampSSE && window.AuctionChampSSE.enabled(document.documentElement);
    }

    function sseUrl() {
        return (document.documentElement.getAttribute('data-sse-url') || '').trim();
    }

    function stopFallbackPoll() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function startFallbackPoll() {
        if (!popupOpen || pollTimer) {
            return;
        }
        pollTimer = setInterval(function () {
            if (!popupOpen) {
                stopFallbackPoll();
                return;
            }
            silentReload();
        }, 12000);
    }

    function stopRosterSse() {
        if (sseCtl && sseCtl.close) {
            try { sseCtl.close(); } catch (e) {}
        }
        sseCtl = null;
        // bind().close() starts poll; kill it after the popup is done.
        stopFallbackPoll();
    }

    function startRosterSse() {
        if (!sseOn() || !window.AuctionChampSSE || sseCtl) {
            return;
        }
        var url = sseUrl();
        if (!url) {
            return;
        }
        sseCtl = window.AuctionChampSSE.bind({
            url: url,
            apply: applyData,
            startPoll: startFallbackPoll,
            stopPoll: stopFallbackPoll,
        });
    }

    var cache = null;
    var loading = false;
    var activeFilter = '';
    var lastFocus = null;
    var lastSig = '';
    var lockY = 0;

    function payloadSig(data) {
        if (!data) {
            return '';
        }
        if (data.seq != null) {
            return 's:' + data.seq + ':' + (data.count || 0);
        }
        var players = data.players || [];
        var bits = [String(data.count || 0)];
        for (var i = 0; i < players.length; i++) {
            bits.push(
                (players[i].id || '') + ':' +
                (players[i].sl_no || '') + ':' +
                (players[i].name || '')
            );
        }
        return bits.join('|');
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function chip(text) {
        if (!text) {
            return '';
        }
        return '<span class="reg-roster-chip">' + esc(text) + '</span>';
    }

    function setStatus(message) {
        bodyEl.innerHTML = '<div class="reg-roster-status">' + esc(message) + '</div>';
    }

    function playerHaystack(player) {
        var parts = [
            player.name, player.current_team, player.tier, player.org_id,
            player.address, player.role, player.batting_style, player.bowling_style,
            player.position, player.position_code, player.preferred_foot,
            player.height, player.weight, player.work_rate,
            String(player.sl_no || ''),
        ];
        if (player.secondary_positions) {
            parts = parts.concat(player.secondary_positions);
        }
        if (player.styles) {
            parts = parts.concat(player.styles);
        }
        if (player.strengths) {
            parts = parts.concat(player.strengths);
        }
        if (player.other_attributes) {
            player.other_attributes.forEach(function (row) {
                parts.push(row.label, row.value);
            });
        }
        return parts.join(' ').toLowerCase();
    }

    function matches(player, query, filter) {
        if (filter) {
            var sportFilter = (player.role || player.position || '');
            if (sportFilter !== filter) {
                return false;
            }
        }
        if (!query) {
            return true;
        }
        return playerHaystack(player).indexOf(query) !== -1;
    }

    function metaRow(label, value) {
        if (!value) {
            return '';
        }
        return '<div class="reg-roster-kv"><span>' + esc(label) + '</span><b>' + esc(value) + '</b></div>';
    }

    function renderCard(player, sport, showOrg, showAddress) {
        var mainAttr = sport === 'football'
            ? (player.position || player.position_code || '')
            : (player.role || '');
        var html = '<article class="reg-roster-card">';
        html += '<div class="reg-roster-photo-wrap">';
        html += '<img class="reg-roster-photo" src="' + esc(player.photo_url) + '" alt="" loading="lazy"/>';
        if (player.sl_no) {
            html += '<span class="reg-roster-no">#' + esc(player.sl_no) + '</span>';
        }
        html += '</div>';
        html += '<div class="reg-roster-info">';
        html += '<div class="reg-roster-title">';
        html += '<h3 class="reg-roster-name">' + esc(player.name) + '</h3>';
        if (player.tier) {
            html += '<span class="reg-roster-tier">' + esc(player.tier) + '</span>';
        }
        html += '</div>';
        if (mainAttr) {
            html += '<div class="reg-roster-main">' + esc(mainAttr) + '</div>';
        }
        html += '<div class="reg-roster-chips">';
        if (sport === 'football') {
            html += chip(player.preferred_foot ? player.preferred_foot + ' foot' : '');
            if (player.age) {
                html += chip('Age ' + player.age);
            }
        } else {
            html += chip(player.batting_style);
            html += chip(player.bowling_style);
        }
        html += chip(player.current_team);
        html += '</div>';
        html += '<div class="reg-roster-meta">';
        if (sport === 'football') {
            if (player.secondary_positions && player.secondary_positions.length) {
                html += metaRow('Secondary', player.secondary_positions.join(', '));
            }
            html += metaRow('Height', player.height);
            html += metaRow('Weight', player.weight);
            html += metaRow('Work rate', player.work_rate);
            if (player.styles && player.styles.length) {
                html += metaRow('Style', player.styles.join(', '));
            }
            if (player.strengths && player.strengths.length) {
                html += metaRow('Strengths', player.strengths.join(', '));
            }
            if (player.other_attributes) {
                player.other_attributes.forEach(function (row) {
                    html += metaRow(row.label, row.value);
                });
            }
        }
        if (showOrg && player.org_id) {
            html += metaRow('Org ID', player.org_id);
        }
        if (showAddress && player.address) {
            html += metaRow('Address', player.address);
        }
        html += '</div></div></article>';
        return html;
    }

    function renderFilters(filters) {
        if (!filtersEl) {
            return;
        }
        if (!filters || !filters.length) {
            filtersEl.hidden = true;
            filtersEl.innerHTML = '';
            return;
        }
        var html = '<button type="button" class="reg-roster-filter' + (activeFilter ? '' : ' is-on') + '" data-filter="">All</button>';
        filters.forEach(function (name) {
            html += '<button type="button" class="reg-roster-filter' + (activeFilter === name ? ' is-on' : '') + '" data-filter="' + esc(name) + '">' + esc(name) + '</button>';
        });
        filtersEl.innerHTML = html;
        filtersEl.hidden = false;
    }

    function renderList() {
        if (!cache) {
            return;
        }
        var query = ((searchEl && searchEl.value) || '').trim().toLowerCase();
        var sport = cache.sport || 'cricket';
        var showOrg = !!cache.show_org_id;
        var showAddress = !!cache.show_address;
        var matched = cache.players.filter(function (player) {
            return matches(player, query, activeFilter);
        });
        if (!matched.length) {
            setStatus(cache.players.length ? 'No players match that search.' : 'No players registered yet.');
            return;
        }
        var html = '<div class="reg-roster-grid">';
        matched.forEach(function (player) {
            html += renderCard(player, sport, showOrg, showAddress);
        });
        html += '</div>';
        bodyEl.innerHTML = html;
        bodyEl.scrollTop = 0;
    }

    function applyData(data) {
        cache = data || { count: 0, players: [], filters: [], sport: 'cricket' };
        if (countEl) {
            countEl.textContent = String(cache.count || 0);
        }
        if (searchEl) {
            searchEl.placeholder = cache.show_address
                ? 'Search by name, team or address…'
                : 'Search by name or team…';
        }
        var sig = payloadSig(cache);
        if (sig && sig === lastSig) {
            return;
        }
        lastSig = sig;
        var scroll = bodyEl.scrollTop;
        renderFilters(cache.filters || []);
        renderList();
        bodyEl.scrollTop = scroll;
    }

    function fetchRoster(showLoading) {
        var url = openBtn.getAttribute('data-url');
        if (!url) {
            if (showLoading) {
                setStatus('Unable to load players.');
            }
            return;
        }
        if (showLoading) {
            loading = true;
            setStatus('Loading registered players…');
        }
        fetch(url, { headers: { 'Accept': 'application/json' } })
            .then(function (res) { return res.json(); })
            .then(function (data) {
                loading = false;
                applyData(data);
            })
            .catch(function () {
                loading = false;
                if (showLoading) {
                    setStatus('Could not load players. Please try again.');
                }
            });
    }

    function silentReload() {
        if (!popupOpen) {
            return;
        }
        fetchRoster(false);
    }

    function loadRoster() {
        if (cache) {
            renderList();
            return;
        }
        if (loading) {
            return;
        }
        fetchRoster(true);
    }

    function isNarrowScreen() {
        return window.matchMedia && window.matchMedia('(max-width: 640px)').matches;
    }

    function fitOverlayToViewport() {
        if (!popupOpen) {
            return;
        }
        var vv = window.visualViewport;
        var height = Math.round((vv && vv.height) ? vv.height : (window.innerHeight || document.documentElement.clientHeight));
        var top = Math.round((vv && vv.offsetTop) ? vv.offsetTop : 0);
        overlay.style.top = top + 'px';
        overlay.style.bottom = 'auto';
        overlay.style.height = height + 'px';
        overlay.style.maxHeight = height + 'px';
    }

    function clearOverlayViewport() {
        overlay.style.top = '';
        overlay.style.bottom = '';
        overlay.style.height = '';
        overlay.style.maxHeight = '';
    }

    function onViewportChange() {
        fitOverlayToViewport();
    }

    function bindViewport() {
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', onViewportChange);
            window.visualViewport.addEventListener('scroll', onViewportChange);
        }
        window.addEventListener('resize', onViewportChange);
    }

    function unbindViewport() {
        if (window.visualViewport) {
            window.visualViewport.removeEventListener('resize', onViewportChange);
            window.visualViewport.removeEventListener('scroll', onViewportChange);
        }
        window.removeEventListener('resize', onViewportChange);
    }

    function openRoster() {
        lastFocus = document.activeElement;
        lockY = window.scrollY || window.pageYOffset || 0;
        overlay.classList.add('open');
        overlay.setAttribute('aria-hidden', 'false');
        document.body.style.top = '-' + lockY + 'px';
        document.body.classList.add('reg-roster-lock');
        popupOpen = true;
        bindViewport();
        fitOverlayToViewport();
        loadRoster();
        startRosterSse();
        if (searchEl && !isNarrowScreen()) {
            setTimeout(function () { searchEl.focus(); }, 40);
        }
    }

    function closeRoster() {
        overlay.classList.remove('open');
        overlay.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('reg-roster-lock');
        document.body.style.top = '';
        popupOpen = false;
        unbindViewport();
        clearOverlayViewport();
        stopRosterSse();
        window.scrollTo(0, lockY);
        if (lastFocus && lastFocus.focus && !isNarrowScreen()) {
            lastFocus.focus();
        }
    }

    openBtn.addEventListener('click', openRoster);
    document.querySelectorAll('[data-reg-roster-open]').forEach(function (el) {
        el.addEventListener('click', openRoster);
    });
    if (closeBtn) {
        closeBtn.addEventListener('click', closeRoster);
    }
    overlay.addEventListener('click', function (ev) {
        if (ev.target === overlay) {
            closeRoster();
        }
    });
    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' && overlay.classList.contains('open')) {
            closeRoster();
        }
    });
    if (searchEl) {
        searchEl.addEventListener('input', renderList);
        searchEl.addEventListener('focus', function () {
            fitOverlayToViewport();
            setTimeout(fitOverlayToViewport, 80);
            setTimeout(function () {
                fitOverlayToViewport();
                if (bodyEl) {
                    bodyEl.scrollTop = 0;
                }
            }, 280);
        });
    }
    if (filtersEl) {
        filtersEl.addEventListener('click', function (ev) {
            var btn = ev.target.closest('[data-filter]');
            if (!btn) {
                return;
            }
            activeFilter = btn.getAttribute('data-filter') || '';
            renderFilters(cache && cache.filters);
            renderList();
        });
    }
    if (dialog) {
        dialog.addEventListener('click', function (ev) {
            ev.stopPropagation();
        });
    }
})();
