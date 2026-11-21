/* AuctionChamp YouTube / OBS overlay — presentation client of projector (pj) snapshot. */
(function () {
    'use strict';

    var dataUrl = window.YTOV_DATA_URL;
    var eventsUrl = window.YTOV_EVENTS_URL;
    var sseOn = window.YTOV_SSE_ENABLED === '1';
    var debug = /(?:^|[?&])debug=1(?:&|$)/.test(String(location.search || ''));
    if (!dataUrl) {
        return;
    }

    var root = document.getElementById('ytov-root');
    var waitEl = document.getElementById('ytovWait');
    var playerEl = document.getElementById('ytovPlayer');
    var nextEl = document.getElementById('ytovNext');
    var nextNumEl = document.getElementById('ytovNextNum');
    var nextUnitEl = document.getElementById('ytovNextUnit');
    var cardEl = playerEl ? playerEl.querySelector('.ipl-player-card') : null;
    var photoEl = document.getElementById('ytovPhoto');
    var photoPhEl = document.getElementById('ytovPhotoPh');
    var nameEl = document.getElementById('ytovName');
    var chipsEl = document.getElementById('ytovChips');
    var metaEl = document.getElementById('ytovMeta');
    var kickerEl = document.getElementById('ytovKicker');
    var iconEl = document.getElementById('ytovIcon');
    var lotEl = document.getElementById('ytovLot');
    var orderEl = document.getElementById('ytovOrder');
    var baseWrapEl = document.getElementById('ytovBase');
    var baseValEl = document.getElementById('ytovBaseVal');
    var liveBoxEl = document.getElementById('ytovLiveBox');
    var liveLabelEl = document.getElementById('ytovLiveLabel');
    var bidValEl = document.getElementById('ytovBidVal');
    var bidTeamEl = document.getElementById('ytovBidTeam');
    var bidTeamLogoEl = document.getElementById('ytovBidTeamLogo');
    var bidTeamLogoPhEl = document.getElementById('ytovBidTeamLogoPh');
    var bidTeamNameEl = document.getElementById('ytovBidTeamName');
    var teamLabelEl = document.getElementById('ytovTeamLabel');
    var stampEl = document.getElementById('ytovStamp');
    var soldHeadEl = document.getElementById('ytovSoldHead');
    var incEl = document.getElementById('ytovInc');
    var pausedEl = document.getElementById('ytovPaused');
    var completeEl = document.getElementById('ytovCompleted');
    var completeStatsEl = document.getElementById('ytovCompleteStats');
    var tickerEl = document.getElementById('ytovTicker');
    var soldEl = document.getElementById('ytovSold');
    var inAuctionEl = document.getElementById('ytovInAuction');
    var unsoldCountEl = document.getElementById('ytovUnsold');
    var spendEl = document.getElementById('ytovSpend');
    var recentEl = document.getElementById('ytovRecent');
    var sponsorEl = document.getElementById('ytovSponsor');
    var sponsorTrackEl = document.getElementById('ytovSponsorTrack');
    var timerEl = document.getElementById('ytovTimer');
    var timerValEl = document.getElementById('ytovTimerVal');
    var teamRowEl = document.getElementById('ytovTeamRow');
    var punchEl = document.getElementById('ytovPunch');

    var INTRO_MS = 1100;
    var animKey = '';
    var enterUntil = 0;
    var amountFrame = 0;
    var POLL_MIN = 250;
    var POLL_MAX = 400;

    var pollTimer = null;
    var pollAllowed = false;
    var inFlight = false;
    var failStreak = 0;
    var lastSeq = -1;
    var lastPlayerId = null;
    var lastBid = null;
    var lastState = '';
    var lastKnown = null;
    var introTimer = null;
    var holdTimer = null;
    var holdPlayerId = null;
    var holdKind = '';
    var holdUntil = 0;
    var statusEl = document.getElementById('ytovStatus');
    var statusCardEl = document.getElementById('ytovStatusCard');
    var statusTitleEl = document.getElementById('ytovStatusTitle');
    var tickTimer = null;
    var clockTimer = null;
    var timerPoll = null;
    var preloaded = {};
    var photoReady = {};
    var sponsorKey = '';
    var recentKey = '';
    var connState = 'CONNECTING';
    var overlayStatus = (document.documentElement.getAttribute('data-overlay-status') || 'ok');
    var clock = {enabled: false, running: false, held: false, frozen: false, remainUntil: 0, heldLeft: 0, epoch: 0};
    var timerOn = false;

    function log() {
        if (!debug) {
            return;
        }
        var args = ['[AUCTION OVERLAY]'];
        for (var i = 0; i < arguments.length; i++) {
            args.push(arguments[i]);
        }
        try {
            console.log.apply(console, args);
        } catch (e) { /* ignore */ }
    }

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function pts(n) {
        if (typeof window.fmtUnit === 'function') {
            return window.fmtUnit(n);
        }
        var num = Math.trunc(Number(n) || 0);
        try {
            return num.toLocaleString() + ' PTS';
        } catch (e2) {
            return String(num) + ' PTS';
        }
    }

    function two(n) {
        n = Math.max(0, n | 0);
        return (n < 10 ? '0' : '') + n;
    }

    function show(el, on) {
        if (!el) {
            return;
        }
        if (on) {
            el.removeAttribute('hidden');
        } else {
            el.setAttribute('hidden', 'hidden');
        }
    }

    function setConn(state) {
        connState = state;
        if (root) {
            root.setAttribute('data-conn', String(state || '').toLowerCase());
        }
        log(state);
    }

    function setUiState(name) {
        if (root) {
            root.setAttribute('data-state', String(name || 'idle').toLowerCase());
        }
    }

    function tierInk(color) {
        var light = {
            '#ffffff': 1,
            '#f39c12': 1,
            '#2ecc71': 1,
            '#e67e22': 1,
            '#1abc9c': 1,
            '#f1c40f': 1
        };
        return light[String(color || '').trim().toLowerCase()] ? '#12243f' : '#ffffff';
    }

    function styleLabel(value) {
        var s = String(value == null ? '' : value).trim();
        if (!s) {
            return '';
        }
        var n = s.replace(/[.\s/_-]/g, '').toUpperCase();
        if (n === 'NA' || n === 'NILL' || n === 'NIL' || n === 'NONE') {
            return '';
        }
        return s;
    }

    function roleText(p) {
        var sport = p.tournament_type || '';
        if (sport === 'football') {
            return p.dominant_position || '';
        }
        if (sport === 'kabaddi') {
            return p.kabaddi_role || p.role || '';
        }
        if (sport === 'badminton') {
            return [p.badminton_category, p.badminton_style].filter(Boolean).join(' · ');
        }
        return p.role || '';
    }

    function identityLine(p) {
        var html = '';
        if (p.tier_name) {
            var bg = p.tier_color || '#3498db';
            html += '<span class="ipl-tier" style="background:' + esc(bg) +
                ';color:' + tierInk(bg) + '">' + esc(p.tier_name) + '</span>';
        }
        var role = roleText(p);
        if (role) {
            html += '<span class="ipl-role">' + esc(role) + '</span>';
        }
        return html;
    }

    function metaLine(p) {
        var bits = [];
        function add(k, v) {
            v = styleLabel(v);
            if (v) {
                bits.push('<span>' + esc(k) + '<b>' + esc(v) + '</b></span>');
            }
        }
        add('Age', p.age);
        var sport = p.tournament_type || '';
        if (sport === 'football') {
            add('Foot', p.preferred_foot);
        } else if (sport === 'badminton') {
            add('Hand', p.preferred_hand || p.preferred_foot);
        } else if (sport === 'kabaddi') {
            add('Club', p.previous_club);
        } else {
            add('Bat', p.batting_style);
            add('Bowl', p.bowling_style);
        }
        add('Location', p.location || p.current_team);
        (p.other_attributes || p.extra_attributes || []).forEach(function (row) {
            if (!row) {
                return;
            }
            add(row.label, row.value);
        });
        return bits.slice(0, 6).join('');
    }

    function splitName(name) {
        var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
        if (!parts.length) {
            return {first: '', last: ''};
        }
        if (parts.length === 1) {
            return {first: '', last: parts[0]};
        }
        return {first: parts.slice(0, -1).join(' '), last: parts[parts.length - 1]};
    }

    function teamInitials(name) {
        var words = String(name || '').trim().split(/\s+/).filter(Boolean);
        if (!words.length) {
            return '';
        }
        var first = words[0].replace(/[^A-Za-z0-9]/g, '');
        if (first.length >= 2 && first.length <= 4 && first === first.toUpperCase()) {
            return first;
        }
        if (words.length === 1) {
            return first.slice(0, 3).toUpperCase();
        }
        return words.map(function (word) {
            return word.charAt(0);
        }).join('').slice(0, 4).toUpperCase();
    }

    function ceremonyPills(p) {
        var items = [];
        var role = roleText(p);
        if (role) {
            items.push({text: role, kind: 'fill'});
        }
        if (p.tier_name) {
            items.push({text: p.tier_name, kind: items.length ? 'line' : 'fill'});
        }
        return items.map(function (item) {
            return '<span class="ytov-pill ytov-pill-' + item.kind + '"><i>' + esc(item.text) + '</i></span>';
        }).join('');
    }

    function ceremonyStats(p) {
        var bits = [];
        function add(k, v) {
            v = styleLabel(v);
            if (v) {
                bits.push('<div class="ytov-stat"><em>' + esc(k) + '</em><b>' + esc(v) + '</b></div>');
            }
        }
        add('Age', p.age);
        var sport = p.tournament_type || '';
        if (sport === 'football') {
            add('Foot', p.preferred_foot);
        } else if (sport === 'badminton') {
            add('Hand', p.preferred_hand || p.preferred_foot);
        } else if (sport === 'kabaddi') {
            add('Club', p.previous_club);
        } else {
            add('Batting', p.batting_style);
            add('Bowling', p.bowling_style);
        }
        add('Location', p.location || p.current_team);
        (p.other_attributes || p.extra_attributes || []).forEach(function (row) {
            if (!row) {
                return;
            }
            add(row.label, row.value);
        });
        return bits.slice(0, 5).join('');
    }

    function preload(url) {
        if (!url || preloaded[url]) {
            return;
        }
        preloaded[url] = true;
        try {
            var im = new Image();
            im.onload = function () {
                photoReady[url] = true;
            };
            im.src = url;
        } catch (e) { /* ignore */ }
    }

    function readInset(name) {
        var raw = '';
        try {
            raw = getComputedStyle(document.documentElement).getPropertyValue(name) || '';
        } catch (e) {
            raw = '';
        }
        var n = parseFloat(raw);
        return isNaN(n) ? 0 : n;
    }

    function fitCanvas() {
        if (!root) {
            return;
        }
        var vv = window.visualViewport;
        var w = (vv && vv.width) || window.innerWidth || 1920;
        var h = (vv && vv.height) || window.innerHeight || 1080;
        var left = readInset('--ytov-sal');
        var right = readInset('--ytov-sar');
        var top = readInset('--ytov-sat');
        var bottom = readInset('--ytov-sab');
        var boxW = Math.max(1, w - left - right);
        var boxH = Math.max(1, h - top - bottom);
        var s = Math.min(boxW / 1920, boxH / 1080);
        var x = ((vv && vv.offsetLeft) || 0) + left + Math.max(0, (boxW - 1920 * s) / 2);
        var y = ((vv && vv.offsetTop) || 0) + top + Math.max(0, (boxH - 1080 * s) / 2);
        root.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(' + s + ')';
    }

    function scheduleFit() {
        fitCanvas();
        setTimeout(fitCanvas, 60);
        setTimeout(fitCanvas, 280);
    }

    function initialOf(name) {
        var text = String(name || '').trim();
        return text ? text.charAt(0).toUpperCase() : '\u2605';
    }

    function setPhoto(url, name) {
        if (photoPhEl) {
            photoPhEl.textContent = initialOf(name);
        }
        if (!photoEl) {
            return;
        }
        photoEl.alt = name || '';
        if (!url) {
            photoEl.removeAttribute('src');
            photoEl.removeAttribute('data-src-set');
            photoEl.classList.remove('is-on');
            show(photoPhEl, true);
            return;
        }
        photoEl.onerror = function () {
            photoEl.removeAttribute('src');
            photoEl.classList.remove('is-on');
            show(photoPhEl, true);
        };
        if (photoEl.getAttribute('data-src-set') !== url) {
            photoEl.setAttribute('data-src-set', url);
            photoEl.src = url;
        }
        photoEl.classList.add('is-on');
        show(photoPhEl, false);
        preload(url);
    }

    function setStageLabel(word, teamWord) {
        if (liveLabelEl) {
            liveLabelEl.textContent = word || '';
            if (word) {
                liveLabelEl.removeAttribute('hidden');
            } else {
                liveLabelEl.setAttribute('hidden', 'hidden');
            }
        }
        if (teamLabelEl) {
            teamLabelEl.textContent = teamWord || word || '';
        }
    }

    function setTeam(name, logoUrl, label, teamLabel) {
        if (label || teamLabel) {
            setStageLabel(label || '', teamLabel);
        }
        if (bidTeamNameEl) {
            bidTeamNameEl.textContent = name || '';
        }
        if (bidTeamLogoEl) {
            if (logoUrl) {
                bidTeamLogoEl.onerror = function () {
                    bidTeamLogoEl.setAttribute('hidden', 'hidden');
                    show(bidTeamLogoPhEl, true);
                };
                if (bidTeamLogoEl.getAttribute('data-src-set') !== logoUrl) {
                    bidTeamLogoEl.setAttribute('data-src-set', logoUrl);
                    bidTeamLogoEl.src = logoUrl;
                }
                bidTeamLogoEl.removeAttribute('hidden');
                show(bidTeamLogoPhEl, false);
                preload(logoUrl);
            } else {
                bidTeamLogoEl.setAttribute('hidden', 'hidden');
                bidTeamLogoEl.removeAttribute('data-src-set');
                show(bidTeamLogoPhEl, !!name);
            }
        }
        if (bidTeamLogoPhEl && name && !logoUrl) {
            bidTeamLogoPhEl.textContent = String(name).charAt(0).toUpperCase();
        }
        show(teamRowEl, !!(name || logoUrl));
        show(bidTeamEl, true);
        fitTeamName();
    }

    function fitTeamName() {
        var el = bidTeamNameEl;
        if (!el) {
            return;
        }
        var len = String(el.textContent || '').length;
        var size = 32;
        if (len > 12) size = 28;
        if (len > 16) size = 24;
        if (len > 20) size = 20;
        if (len > 26) size = 17;
        if (len > 32) size = 14;
        el.style.letterSpacing = size >= 28 ? '.04em' : '0';
        el.style.fontSize = size + 'px';
        var guard = 0;
        while (guard < 22 && size > 11 && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1) {
            size -= 1;
            el.style.fontSize = size + 'px';
            guard += 1;
        }
    }

    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(function () { fitTeamName(); });
    }

    function setSealArc(id, value) {
        var el = document.getElementById(id);
        if (!el) {
            return null;
        }
        var path = el.querySelector('textPath');
        if (path) {
            path.textContent = value || '';
            path.removeAttribute('textLength');
        }
        return path;
    }

    function fitSealTeam(teamName, textId) {
        textId = textId || 'ytovSealArcBotText';
        var arc = document.getElementById(textId);
        var path = setSealArc(textId, teamName);
        if (!arc) {
            return;
        }
        var len = String(teamName || '').length || 1;
        var size = 15;
        if (len > 12) { size = 13; }
        if (len > 16) { size = 11.5; }
        if (len > 20) { size = 10; }
        if (len > 26) { size = 8.5; }
        arc.setAttribute('font-size', String(size));
        arc.setAttribute('letter-spacing', len > 18 ? '0' : '0.8');
        if (path && len > 16) {
            path.setAttribute('textLength', '250');
            path.setAttribute('lengthAdjust', 'spacingAndGlyphs');
        }
    }

    function setCeremonyPhoto(photo, ph, player) {
        var url = player && player.photo_url ? player.photo_url : '';
        if (!photo) {
            return;
        }
        if (!url) {
            photo.onload = null;
            photo.onerror = null;
            photo.removeAttribute('src');
            photo.removeAttribute('data-src-set');
            photo.classList.remove('is-on');
            show(ph, true);
            return;
        }
        if (photo.getAttribute('data-src-set') === url && photo.classList.contains('is-on') && photo.complete && photo.naturalWidth) {
            show(ph, false);
            return;
        }
        photo.classList.remove('is-on');
        show(ph, true);
        photo.onload = function () {
            if (photo.getAttribute('data-src-set') !== url) {
                return;
            }
            photoReady[url] = true;
            photo.classList.add('is-on');
            show(ph, false);
        };
        photo.onerror = function () {
            if (photo.getAttribute('data-src-set') !== url) {
                return;
            }
            photo.classList.remove('is-on');
            show(ph, true);
        };
        photo.setAttribute('data-src-set', url);
        if (!photoReady[url]) {
            preload(url);
        }
        photo.src = url;
        if (photo.complete && photo.naturalWidth) {
            photoReady[url] = true;
            photo.classList.add('is-on');
            show(ph, false);
        }
    }

    function hideCeremony() {
        var el = document.getElementById('ytovCeremony');
        if (!el) {
            return;
        }
        el.classList.remove('is-on');
        show(el, false);
    }

    function showCeremony(player, amount, teamName, logoUrl, fresh, kind) {
        var el = document.getElementById('ytovCeremony');
        if (!el || !player) {
            return;
        }
        var photo = document.getElementById('ytovCerPhoto');
        var ph = document.getElementById('ytovCerPh');
        var first = document.getElementById('ytovCerFirst');
        var last = document.getElementById('ytovCerLast');
        var role = document.getElementById('ytovCerRole');
        var attrs = document.getElementById('ytovCerAttrs');
        var team = document.getElementById('ytovCerTeam');
        var ptsEl = document.getElementById('ytovCerPts');
        var logo = document.getElementById('ytovCerLogo');
        var logoPh = document.getElementById('ytovCerLogoPh');
        var crest = document.getElementById('ytovCerCrest');
        var card = document.getElementById('ytovCerCard');
        var seal = document.getElementById('ytovCerSeal');
        kind = kind || 'sold';
        var sold = kind === 'sold';
        var parts = splitName(player.name);
        if (first) {
            first.textContent = parts.first;
        }
        if (last) {
            last.textContent = parts.last;
        }
        if (role) {
            role.innerHTML = ceremonyPills(player);
        }
        var line = document.getElementById('ytovCerLine');
        if (line) {
            var roleName = roleText(player);
            var tierName = styleLabel(player.tier_name);
            line.innerHTML =
                (roleName ? '<span class="ytov-fact"><em>ROLE</em><b>' + esc(roleName) + '</b></span>' : '') +
                (tierName ? '<span class="ytov-fact"><em>TIER</em><b>' + esc(tierName) + '</b></span>' : '');
        }
        if (attrs) {
            attrs.innerHTML = '';
        }
        if (team) {
            team.textContent = teamName || '';
        }
        if (ptsEl) {
            if (sold) {
                ptsEl.textContent = pts(amount);
                show(ptsEl, true);
            } else {
                ptsEl.textContent = '';
                show(ptsEl, false);
            }
        }
        if (card) {
            card.classList.toggle('is-unsold', kind === 'unsold');
            card.classList.toggle('is-withdrawn', kind === 'withdrawn');
        }
        if (seal) {
            seal.setAttribute('data-kind', sold ? 'sold' : (kind === 'withdrawn' ? 'withdrawn' : 'unsold'));
        }
        var sealWord = document.getElementById('ytovCerSealWord');
        if (sealWord) {
            sealWord.textContent = sold ? 'SOLD' : (kind === 'withdrawn' ? 'WITHDRAWN' : 'UNSOLD');
        }
        if (ph) {
            ph.textContent = initialOf(player.name);
        }
        setCeremonyPhoto(photo, ph, player);
        if (logo) {
            if (logoUrl) {
                logo.src = logoUrl;
                logo.removeAttribute('hidden');
                show(logoPh, false);
            } else {
                logo.setAttribute('hidden', 'hidden');
                if (logoPh) {
                    logoPh.textContent = teamInitials(teamName);
                }
                show(logoPh, !!teamName);
            }
        }
        if (team) {
            show(team, sold && !!teamName);
        }
        show(crest, sold && !!teamName);
        show(document.getElementById('ytovCerTo'), sold && !!teamName);
        show(el, true);
        if (fresh || !el.classList.contains('is-on')) {
            el.classList.remove('is-on');
            void el.offsetWidth;
            el.classList.add('is-on');
        }
    }

    function hidePunch() {
        show(stampEl, false);
        hideCeremony();
        if (punchEl) {
            punchEl.classList.remove('is-on');
            punchEl.setAttribute('hidden', 'hidden');
        }
    }

    function showPunch(kind) {
        if (!stampEl) {
            return;
        }
        var sold = kind === 'sold';
        stampEl.setAttribute('data-kind', sold ? 'sold' : (kind === 'withdrawn' ? 'withdrawn' : 'unsold'));
        setSealArc('ytovSealArcTopText', sold ? 'SOLD TO' : 'NO BID');
        var team = '';
        if (sold && bidTeamNameEl) {
            team = bidTeamNameEl.textContent || '';
        }
        fitSealTeam(sold ? (String(team || 'TEAM').toUpperCase()) : (kind === 'withdrawn' ? 'WITHDRAWN' : 'UNSOLD'));
        var logo = document.getElementById('ytovSealLogo');
        var logoSrc = sold && bidTeamLogoEl && !bidTeamLogoEl.hasAttribute('hidden') ? bidTeamLogoEl.getAttribute('src') : '';
        if (logo) {
            if (logoSrc) {
                logo.src = logoSrc;
                logo.classList.add('is-on');
                logo.removeAttribute('hidden');
            } else {
                logo.classList.remove('is-on');
                logo.setAttribute('hidden', 'hidden');
            }
        }
        show(stampEl, true);
        if (punchEl) {
            punchEl.setAttribute('hidden', 'hidden');
        }
    }

    function setSoldHead(text) {
        if (!soldHeadEl) {
            return;
        }
        if (!text) {
            show(soldHeadEl, false);
            return;
        }
        soldHeadEl.textContent = text;
        show(soldHeadEl, true);
    }

    function reduceMotion() {
        try {
            return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        } catch (e) {
            return false;
        }
    }

    function teamAccent(team) {
        if (team && team.color) {
            return String(team.color);
        }
        var key = String((team && (team.id || team.name)) || '0');
        var n = 0;
        var i;
        for (i = 0; i < key.length; i++) {
            n = (n + key.charCodeAt(i) * (i + 1)) % 6;
        }
        return ['#C91E32', '#1D4ED8', '#0F766E', '#B45309', '#6D28D9', '#0369A1'][n];
    }

    function paintAmount(el, target, animate) {
        target = Math.round(Number(target) || 0);
        if (!el) {
            return;
        }
        var prev = Number(el.getAttribute('data-n'));
        if (amountFrame) {
            cancelAnimationFrame(amountFrame);
            amountFrame = 0;
        }
        if (!animate || reduceMotion() || !isFinite(prev) || prev === target) {
            el.textContent = pts(target);
            el.setAttribute('data-n', String(target));
            return;
        }
        var t0 = (window.performance && performance.now) ? performance.now() : Date.now();
        function step(now) {
            var k = Math.min(1, (now - t0) / 520);
            var eased = 1 - Math.pow(1 - k, 3);
            el.textContent = pts(Math.round(prev + (target - prev) * eased));
            if (k < 1) {
                amountFrame = requestAnimationFrame(step);
            } else {
                amountFrame = 0;
            }
        }
        el.setAttribute('data-n', String(target));
        amountFrame = requestAnimationFrame(step);
    }

    function paintIncrement(amount, base) {
        if (!incEl) {
            return;
        }
        var prev = Number(lastBid || 0);
        var delta = 0;
        if (prev > 0 && amount > prev) {
            delta = amount - prev;
        } else if (!prev && base > 0 && amount > base) {
            delta = amount - base;
        }
        if (delta > 0) {
            incEl.textContent = '+' + pts(delta);
            show(incEl, true);
        } else {
            show(incEl, false);
        }
    }

    function armCard(uiState, playerId) {
        if (!cardEl) {
            return false;
        }
        var sealed = uiState === 'SOLD' || uiState === 'UNSOLD' || uiState === 'WITHDRAWN';
        if (uiState === 'PLAYER_INTRO') {
            cardEl.classList.add('is-enter');
            enterUntil = Date.now() + INTRO_MS;
        } else if (Date.now() >= enterUntil) {
            cardEl.classList.remove('is-enter');
        }
        if (!sealed) {
            animKey = '';
            cardEl.classList.remove('is-play');
            return false;
        }
        var key = uiState + ':' + playerId;
        if (key === animKey) {
            return false;
        }
        animKey = key;
        cardEl.classList.remove('is-play');
        void cardEl.offsetWidth;
        cardEl.classList.add('is-play');
        return true;
    }

    function paintRecent(list) {
        var rows = (list || []).filter(function (row) { return row && row.kind !== 'unsold'; }).slice(0, 5);
        var key = rows.map(function (row) {
            return (row.player_name || '') + '|' + (row.points || 0);
        }).join(',');
        if (!recentEl || key === recentKey) {
            return;
        }
        recentKey = key;
        recentEl.innerHTML = '';
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            var el = document.createElement('div');
            el.className = 'bc-sale';
            var photo = row.player_photo_url
                ? '<img alt="" src="' + esc(row.player_photo_url) + '"/>'
                : '<span class="bc-sale-ph">&#9733;</span>';
            el.innerHTML = photo +
                '<span class="bc-sale-copy"><span class="bc-sale-name">' + esc(String(row.player_name || '').toUpperCase()) + '</span>' +
                '<span class="bc-sale-team">' + esc(String(row.team_name || '').toUpperCase()) + '</span>' +
                '<span class="bc-sale-pts">' + esc(pts(row.points)) + '</span></span>';
            recentEl.appendChild(el);
            if (row.player_photo_url) {
                preload(row.player_photo_url);
            }
        }
    }

    function paintTicker(result) {
        var prog = (result && result.progress) || {};
        var total = Number(prog.total || 0);
        var sold = Number(prog.sold || 0);
        var unsold = prog.unsold != null ? Number(prog.unsold) : 0;
        var inAuction = prog.in_auction != null ? Number(prog.in_auction) : Number(prog.auction || 0);
        var spend = 0;
        var teams = (result && result.teams) || [];
        for (var i = 0; i < teams.length; i++) {
            var purse = Number(teams[i].total_point || 0);
            var left = Number(teams[i].remaining_points || 0);
            if (purse > left) {
                spend += purse - left;
            }
        }
        if (soldEl) {
            soldEl.textContent = String(sold);
        }
        if (inAuctionEl) {
            inAuctionEl.textContent = String(inAuction);
        }
        if (unsoldCountEl) {
            unsoldCountEl.textContent = String(unsold);
        }
        if (spendEl) {
            spendEl.textContent = pts(spend);
        }
        paintRecent(result && result.recent_bids);
        show(tickerEl, total > 0 || sold > 0);
        if (completeStatsEl) {
            completeStatsEl.textContent = inAuction + ' IN AUCTION  ·  ' + sold + ' SOLD  ·  ' + unsold + ' UNSOLD  ·  SPEND ' + pts(spend);
        }
    }

    function paintOrder(result, state) {
        if (!orderEl) {
            return;
        }
        var prog = (result && result.progress) || {};
        var current = Number(prog.current || 0);
        var total = Number(prog.total || 0);
        if (!current || !total) {
            orderEl.textContent = '';
            show(orderEl, false);
            return;
        }
        var word = 'NOW AUCTIONING';
        if (state === 'sold') {
            word = 'SOLD';
        } else if (state === 'unsold') {
            word = 'UNSOLD';
        }
        orderEl.textContent = word + ' ' + current + '/' + total;
        show(orderEl, true);
    }

    function rotateSponsors(list) {
        var ads = list || [];
        if (!sponsorEl || !sponsorTrackEl) {
            return;
        }
        var key = ads.map(function (ad) { return ad.id || ad.image_url || ''; }).join(',');
        if (key === sponsorKey) {
            return;
        }
        sponsorKey = key;
        sponsorTrackEl.innerHTML = '';
        var shown = 0;
        for (var i = 0; i < ads.length && shown < 3; i++) {
            var ad = ads[i];
            if (!ad || !ad.image_url) {
                continue;
            }
            var img = document.createElement('img');
            img.className = 'sponsor-logo';
            img.src = ad.image_url;
            img.alt = ad.name || '';
            sponsorTrackEl.appendChild(img);
            preload(ad.image_url);
            shown += 1;
        }
        show(sponsorEl, shown > 0);
    }

    function pulseBid() {
        if (!liveBoxEl) {
            return;
        }
        liveBoxEl.classList.remove('is-tick');
        void liveBoxEl.offsetWidth;
        liveBoxEl.classList.add('is-tick');
        if (tickTimer) {
            clearTimeout(tickTimer);
        }
        tickTimer = setTimeout(function () {
            liveBoxEl.classList.remove('is-tick');
        }, 450);
    }

    function paintClock() {
        if (!timerEl || !timerValEl) {
            return;
        }
        if (!timerOn || !clock.enabled || (!clock.running && !clock.held && !clock.frozen)) {
            show(timerEl, false);
            return;
        }
        var left = clock.held
            ? Math.max(0, clock.heldLeft)
            : (clock.frozen ? 0 : Math.max(0, (clock.remainUntil - Date.now()) / 1000));
        if (!clock.held && left <= 0) {
            clock.frozen = true;
            clock.running = false;
            left = 0;
        }
        var secs = Math.ceil(left);
        timerValEl.textContent = two(Math.floor(secs / 60)) + ':' + two(secs % 60);
        timerEl.classList.toggle('is-low', !clock.held && secs > 0 && secs <= 10);
        timerEl.classList.toggle('is-held', !!clock.held || !!clock.frozen);
        show(timerEl, true);
    }

    function syncClock(timer) {
        timer = timer || {};
        var epoch = Number(timer.epoch || 0);
        if (epoch && clock.epoch && epoch + 0.0001 < clock.epoch) {
            return;
        }
        if (epoch) {
            clock.epoch = epoch;
        }
        if (!timer.enabled) {
            clock.enabled = false;
            clock.running = false;
            clock.held = false;
            clock.frozen = false;
        } else if (timer.held) {
            clock.enabled = true;
            clock.running = false;
            clock.held = true;
            clock.frozen = false;
            clock.heldLeft = Math.max(0, Number(timer.remaining) || 0);
        } else if (timer.frozen) {
            clock.enabled = true;
            clock.running = false;
            clock.held = false;
            clock.frozen = true;
        } else if (timer.running) {
            clock.enabled = true;
            clock.running = true;
            clock.held = false;
            clock.frozen = false;
            clock.remainUntil = Date.now() + Math.max(0, (Number(timer.remaining) || 0) * 1000);
        } else {
            clock.enabled = !!timer.enabled;
            clock.running = false;
        }
        paintClock();
    }

    function timerUrl() {
        var db = window.YTOV_DB || '';
        var tid = window.YTOV_TOURNAMENT_ID || '';
        var path = (db ? '/' + db : '') + '/auction/bid_timer';
        return tid ? path + '?tournament_id=' + encodeURIComponent(tid) : path;
    }

    function pollTimerOnce() {
        if (!timerOn) {
            return;
        }
        fetch(timerUrl(), {cache: 'no-store'})
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (timer) {
                if (timer) {
                    syncClock(timer);
                }
            })
            .catch(function () { /* keep the last tick */ });
    }

    function setTimerActive(on) {
        timerOn = !!on;
        if (!timerOn) {
            show(timerEl, false);
            if (timerPoll) {
                clearInterval(timerPoll);
                timerPoll = null;
            }
            return;
        }
        pollTimerOnce();
        if (!timerPoll) {
            timerPoll = setInterval(pollTimerOnce, 1000);
        }
        if (!clockTimer) {
            clockTimer = setInterval(paintClock, 250);
        }
    }

    function mapEvent(p, bidAmt, uiState) {
        var pid = p && p.id;
        if (uiState === 'COMPLETED') {
            return 'auction_completed';
        }
        if (uiState === 'PAUSED' && lastState !== 'PAUSED') {
            return 'auction_paused';
        }
        if (uiState === 'IDLE' && lastState && lastState !== 'IDLE') {
            return 'next_player';
        }
        if (pid && pid !== lastPlayerId) {
            return 'player_started';
        }
        if (uiState === 'SOLD' && lastState !== 'SOLD') {
            return 'player_sold';
        }
        if (uiState === 'UNSOLD' && lastState !== 'UNSOLD') {
            return 'player_unsold';
        }
        if (uiState === 'WITHDRAWN' && lastState !== 'WITHDRAWN') {
            return 'player_withdrawn';
        }
        if (bidAmt && bidAmt !== lastBid) {
            return 'bid_updated';
        }
        return '';
    }

    function soldHoldMs(result) {
        var meta = (result && result.auction_meta) || {};
        var n = meta.sold_display_seconds;
        if (n == null || n === '') {
            n = window.YTOV_SOLD_SECONDS;
        }
        n = Number(n);
        if (isNaN(n) || n < 0) {
            n = 5;
        }
        return n * 1000;
    }

    function clearHoldTimer() {
        if (holdTimer) {
            clearTimeout(holdTimer);
            holdTimer = null;
        }
    }

    function parseServerTime(raw) {
        if (!raw) {
            return 0;
        }
        var text = String(raw).replace(' ', 'T');
        var exp = Date.parse(text + 'Z');
        if (isNaN(exp)) {
            exp = Date.parse(text + '+00:00');
        }
        return isNaN(exp) ? 0 : exp;
    }

    function celebrationDeadline(p, result) {
        var fromSnapshot = parseServerTime(result && result.celebration_until);
        if (fromSnapshot) {
            return fromSnapshot;
        }
        if (holdPlayerId === p.id && holdKind === p.state && holdUntil) {
            return holdUntil;
        }
        return Date.now() + soldHoldMs(result);
    }

    function syncCelebration(p, result, resultHold) {
        if (!resultHold || !p) {
            if (!p || p.id !== holdPlayerId) {
                holdPlayerId = null;
                holdKind = '';
                holdUntil = 0;
                clearHoldTimer();
            }
            return;
        }
        var deadline = celebrationDeadline(p, result);
        if (holdPlayerId === p.id && holdKind === p.state && holdUntil === deadline) {
            return;
        }
        holdPlayerId = p.id;
        holdKind = p.state;
        holdUntil = deadline;
        clearHoldTimer();
        var delay = holdUntil - Date.now();
        if (delay <= 0) {
            return;
        }
        holdTimer = setTimeout(function () {
            holdTimer = null;
            if (lastKnown) {
                apply(lastKnown);
            }
        }, delay + 40);
    }

    var nextTimer = null;

    function nextSecondsLeft() {
        if (!holdUntil) {
            return 0;
        }
        return Math.max(0, Math.ceil((holdUntil - Date.now()) / 1000));
    }

    function paintNextLoad() {
        var n = nextSecondsLeft();
        if (nextNumEl) {
            nextNumEl.textContent = String(n);
        }
        if (nextUnitEl) {
            nextUnitEl.textContent = n === 1 ? 'second' : 'seconds';
        }
    }

    function setNextLoad(on) {
        show(nextEl, !!on);
        if (!on) {
            if (nextTimer) {
                clearInterval(nextTimer);
                nextTimer = null;
            }
            return;
        }
        paintNextLoad();
        if (!nextTimer) {
            nextTimer = setInterval(paintNextLoad, 250);
        }
    }

    function bridgeTitle(result) {
        var phase = ((result && result.wait_phase) || {}).phase || '';
        if (phase === 'loading_unsold') {
            return 'LOADING FROM UNSOLD';
        }
        if (phase === 'draft_soon') {
            return 'PLAYERS WILL ENTER THE AUCTION SOON';
        }
        if (phase === 'about_to_begin') {
            return 'COMING UP NEXT';
        }
        return 'NEXT PLAYER COMING UP';
    }

    function showStatus(title, kind) {
        if (statusTitleEl) {
            statusTitleEl.textContent = title;
            statusTitleEl.classList.toggle('is-compact', String(title || '').length > 22);
        }
        if (statusCardEl) {
            statusCardEl.classList.toggle('is-break', kind === 'break');
        }
        show(statusEl, true);
    }

    function idleCopy(result) {
        var wait = (result && result.wait_phase) || {};
        if (overlayStatus === 'missing') {
            return 'AUCTION NOT LIVE';
        }
        if (wait.phase === 'waiting' || wait.phase === 'draft_soon' || wait.phase === 'loading_unsold') {
            return 'COMING UP NEXT';
        }
        return wait.idle_headline || 'COMING UP NEXT';
    }

    function apply(result) {
        result = result || {};
        if (result.seq != null) {
            var seq = Number(result.seq);
            if (!isNaN(seq) && lastSeq >= 0 && seq < lastSeq) {
                return;
            }
            if (!isNaN(seq)) {
                lastSeq = seq;
            }
        }
        lastKnown = result;

        var p = result.player;
        var wait = result.wait_phase || {};
        var paused = !!result.break_time;
        var completed = wait.phase === 'completed';
        var bidAmt = p ? Number(p.current_bid || 0) : 0;
        var soldAmt = p ? Number(p.sold_points || 0) : 0;
        var baseAmt = p ? Number(p.base_price || 0) : 0;
        var pState = p ? (p.state || 'auction') : '';
        var resultHold = pState === 'sold' || pState === 'unsold' || pState === 'withdrawn';
        syncCelebration(p, result, resultHold);
        var celebrating = resultHold && !!p;
        var uiState = 'IDLE';

        if (paused && !completed) {
            uiState = 'PAUSED';
        } else if (celebrating) {
            uiState = pState === 'unsold' ? 'UNSOLD' : (pState === 'withdrawn' ? 'WITHDRAWN' : 'SOLD');
        } else if (completed) {
            uiState = 'COMPLETED';
        } else if (resultHold) {
            uiState = 'BRIDGE';
        } else if (!p) {
            uiState = 'IDLE';
        } else if (p && p.id && p.id !== lastPlayerId) {
            uiState = 'PLAYER_INTRO';
        } else if (bidAmt && bidAmt !== lastBid) {
            uiState = 'BID_UPDATE';
        } else {
            uiState = 'BIDDING';
        }

        var evt = mapEvent(p, bidAmt, uiState);
        if (evt) {
            log('Event: ' + evt, p ? ('Player: ' + p.id) : '', bidAmt ? ('Amount: ' + bidAmt) : '');
        }

        setUiState(uiState);
        setNextLoad(uiState === 'SOLD' || uiState === 'UNSOLD' || uiState === 'WITHDRAWN');
        paintTicker(result);
        rotateSponsors(result.advertisers || []);
        show(completeEl, uiState === 'COMPLETED');
        show(pausedEl, false);

        if (uiState === 'PAUSED' || uiState === 'BRIDGE') {
            show(playerEl, false);
            animKey = '';
            hidePunch();
            setTimerActive(false);
            show(waitEl, false);
            showStatus(
                uiState === 'PAUSED' ? 'BREAK' : bridgeTitle(result),
                uiState === 'PAUSED' ? 'break' : 'bridge'
            );
            show(orderEl, false);
            lastPlayerId = p ? p.id : null;
            lastBid = bidAmt || null;
            lastState = uiState;
            return;
        }

        show(statusEl, false);

        if (uiState === 'COMPLETED' || !p) {
            show(playerEl, false);
            animKey = '';
            hidePunch();
            setTimerActive(false);
            if (waitEl) {
                waitEl.textContent = uiState === 'COMPLETED'
                    ? (wait.message || 'AUCTION COMPLETED')
                    : idleCopy(result);
            }
            show(waitEl, uiState !== 'COMPLETED');
            show(orderEl, false);
            lastPlayerId = p ? p.id : null;
            lastBid = bidAmt || null;
            lastState = uiState;
            return;
        }

        show(waitEl, false);
        show(playerEl, uiState !== 'SOLD' && uiState !== 'UNSOLD' && uiState !== 'WITHDRAWN');
        if (cardEl) {
            cardEl.classList.remove('is-sold', 'is-unsold', 'is-withdrawn', 'has-live-bid');
            cardEl.style.setProperty('--team', teamAccent(
                (p.current_bid_team && (p.current_bid_team.id || p.current_bid_team.name))
                    ? p.current_bid_team
                    : {name: p.team_name || ''}
            ));
        }
        var sealFresh = (uiState === 'SOLD' || uiState === 'UNSOLD' || uiState === 'WITHDRAWN')
            && ((uiState + ':' + p.id) !== animKey);

        if (nameEl) {
            nameEl.textContent = p.name || '';
        }
        if (lotEl) {
            var serial = (p.sl_no && p.sl_no !== '?' && p.sl_no !== '0') ? String(p.sl_no) : '';
            lotEl.textContent = serial ? ('#' + serial) : '';
            show(lotEl, !!serial);
        }
        paintOrder(result, pState);
        show(iconEl, !!p.icon_player);
        setPhoto(p.photo_url, p.name);
        if (chipsEl) {
            chipsEl.innerHTML = identityLine(p);
        }
        if (metaEl) {
            metaEl.innerHTML = metaLine(p);
        }
        if (baseValEl) {
            baseValEl.textContent = pts(baseAmt);
        }

        var team = p.current_bid_team || {};
        var soldTeamName = p.team_name || (team.name || '');
        var soldLogo = p.team_logo_url || team.logo_url || '';

        if (uiState === 'SOLD') {
            if (cardEl) {
                cardEl.classList.add('is-sold');
            }
            setSoldHead('PLAYER SOLD');
            if (kickerEl) {
                kickerEl.textContent = '';
            }
            paintAmount(bidValEl, soldAmt || bidAmt || baseAmt, false);
            show(incEl, false);
            show(liveBoxEl, true);
            show(baseWrapEl, false);
            setTeam(soldTeamName, soldLogo, 'SOLD FOR', 'Sold to');
            showCeremony(p, soldAmt || bidAmt || baseAmt, soldTeamName, soldLogo, sealFresh, 'sold');
            setTimerActive(false);
        } else if (uiState === 'UNSOLD' || uiState === 'WITHDRAWN') {
            var withdrawn = uiState === 'WITHDRAWN';
            if (cardEl) {
                cardEl.classList.add(withdrawn ? 'is-withdrawn' : 'is-unsold');
            }
            setSoldHead(withdrawn ? 'PLAYER WITHDRAWN' : 'PLAYER UNSOLD');
            if (kickerEl) {
                kickerEl.textContent = '';
            }
            if (bidValEl) {
                bidValEl.textContent = '\u2014';
                bidValEl.removeAttribute('data-n');
            }
            show(incEl, false);
            show(liveBoxEl, true);
            show(baseWrapEl, false);
            setTeam('', '', withdrawn ? 'WITHDRAWN' : 'UNSOLD', withdrawn ? 'Withdrawn' : 'Unsold');
            showCeremony(p, 0, '', '', sealFresh, withdrawn ? 'withdrawn' : 'unsold');
            setTimerActive(false);
        } else if (bidAmt) {
            if (cardEl) {
                cardEl.classList.add('has-live-bid');
            }
            setSoldHead('');
            if (kickerEl) {
                kickerEl.textContent = 'ON AUCTION';
            }
            paintIncrement(bidAmt, baseAmt);
            paintAmount(bidValEl, bidAmt, false);
            show(liveBoxEl, true);
            show(baseWrapEl, baseAmt > 0);
            hidePunch();
            setTeam(team.name, team.logo_url, 'CURRENT BID', 'Top Bidder');
            setTimerActive(true);
            if (uiState === 'BID_UPDATE') {
                pulseBid();
            }
        } else {
            setSoldHead('');
            if (kickerEl) {
                kickerEl.textContent = 'ON AUCTION';
            }
            paintAmount(bidValEl, baseAmt, false);
            show(incEl, false);
            show(liveBoxEl, true);
            show(baseWrapEl, false);
            hidePunch();
            setTeam('', '', 'BASE PRICE', 'Now Auctioning');
            setTimerActive(true);
        }
        armCard(uiState, p.id);

        if (uiState === 'PLAYER_INTRO') {
            if (introTimer) {
                clearTimeout(introTimer);
            }
            introTimer = setTimeout(function () {
                if (root && (root.getAttribute('data-state') || '') === 'player_intro') {
                    setUiState('BIDDING');
                }
            }, INTRO_MS);
        }

        lastPlayerId = p.id;
        lastBid = bidAmt || null;
        lastState = uiState;
    }

    function fetchOnce(done) {
        if (inFlight) {
            if (typeof done === 'function') {
                done();
            }
            return;
        }
        inFlight = true;
        fetch(dataUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', method: 'call', params: {} }),
            cache: 'no-store',
        })
            .then(function (r) { return r.json(); })
            .then(function (json) {
                failStreak = 0;
                apply(json.result || lastKnown || {});
            })
            .catch(function () {
                failStreak += 1;
                if (lastKnown) {
                    apply(lastKnown);
                }
            })
            .then(function () {
                inFlight = false;
                if (typeof done === 'function') {
                    done();
                }
            });
    }

    function pollDelay() {
        return Math.min(POLL_MAX, POLL_MIN * Math.pow(1.5, failStreak));
    }

    function poll() {
        if (!pollAllowed) {
            return;
        }
        var started = Date.now();
        pollTimer = true;
        fetchOnce(function () {
            if (!pollAllowed) {
                pollTimer = null;
                return;
            }
            var wait = Math.max(40, pollDelay() - (Date.now() - started));
            pollTimer = setTimeout(poll, wait);
        });
    }

    function startPoll() {
        pollAllowed = true;
        if (connState === 'OFFLINE') {
            setConn('RECONNECTING');
        }
        if (!pollTimer) {
            poll();
        }
    }

    function stopPoll() {
        setConn('CONNECTED');
        pollAllowed = false;
        if (pollTimer) {
            clearTimeout(pollTimer);
            pollTimer = null;
        }
    }

    window.addEventListener('resize', scheduleFit);
    window.addEventListener('orientationchange', scheduleFit);
    window.addEventListener('pageshow', scheduleFit);
    if (window.visualViewport) {
        window.visualViewport.addEventListener('resize', scheduleFit);
        window.visualViewport.addEventListener('scroll', fitCanvas);
    }
    scheduleFit();

    function previewKind() {
        var match = /(?:^|[?&])preview(?:=([a-z0-9]+))?(?:&|$)/.exec(location.search || '');
        if (!match) {
            return '';
        }
        return match[1] || 'cycle';
    }

    function previewPayload(kind, bid) {
        function pad(n) { return (n < 10 ? '0' : '') + n; }
        var soon = new Date(Date.now() + 8 * 1000);
        var soonStamp = soon.getUTCFullYear() + '-' + pad(soon.getUTCMonth() + 1) + '-' + pad(soon.getUTCDate())
            + ' ' + pad(soon.getUTCHours()) + ':' + pad(soon.getUTCMinutes()) + ':' + pad(soon.getUTCSeconds());
        var photo = 'data:image/svg+xml,' + encodeURIComponent(
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 480'><defs><linearGradient id='g' x1='0' y1='0' x2='0' y2='1'><stop stop-color='#1d4e9a'/><stop offset='1' stop-color='#07142e'/></linearGradient></defs><rect width='400' height='480' fill='url(#g)'/><circle cx='200' cy='168' r='78' fill='#e8d7b0'/><path d='M80 480c18-120 68-176 120-176s102 56 120 176' fill='#123a78'/></svg>"
        );
        var auctioning = kind === 'intro' || kind === 'bid';
        var player = kind === 'idle' ? null : {
            id: 9001,
            sl_no: '18',
            name: 'Arjun Menon',
            role: 'All Rounder',
            tier_name: 'Platinum',
            tier_color: '#D9A441',
            batting_style: 'Right Hand',
            bowling_style: 'Right Arm Medium',
            age: 24,
            location: 'Kochi',
            photo_url: photo,
            base_price: 10000,
            current_bid: auctioning ? (bid || 0) : (kind === 'sold' ? 120000 : 0),
            sold_points: kind === 'sold' ? 120000 : 0,
            state: auctioning ? 'auction' : kind,
            team_name: kind === 'sold' ? 'KCB Capitals' : '',
            current_bid_team: (kind === 'bid' || kind === 'sold') ? {id: 10, name: 'KCB Capitals', color: '#C91E32'} : null,
            tournament_type: 'cricket',
            icon_player: true
        };
        return {
            seq: Date.now(),
            player: player,
            progress: {total: 80, sold: 14, unsold: 6, in_auction: 60, remaining: 66, current: 15},
            wait_phase: kind === 'idle' ? {phase: 'about_to_begin', idle_headline: 'COMING UP NEXT'} : {},
            recent_bids: [{player_name: 'Neeraj Kumar', team_name: 'Team ASR', points: 80000, kind: 'sold'}],
            advertisers: [],
            auction_meta: {sold_display_seconds: 8},
            celebration_until: (kind === 'sold' || kind === 'unsold' || kind === 'withdrawn') ? soonStamp : ''
        };
    }

    function showPreview(kind, bid) {
        clearHoldTimer();
        holdPlayerId = null;
        holdKind = '';
        holdUntil = 0;
        if (kind === 'intro') {
            lastPlayerId = null;
            lastBid = null;
        }
        apply(previewPayload(kind, bid || 0));
    }

    function runPreview(which) {
        document.documentElement.classList.add('is-preview');
        setConn('CONNECTED');
        var dock = document.createElement('div');
        dock.className = 'ac-preview-dock';
        var names = ['intro', 'bid', 'sold', 'unsold', 'withdrawn', 'idle'];
        var timer = null;
        names.forEach(function (name) {
            var button = document.createElement('button');
            button.type = 'button';
            button.textContent = name;
            button.addEventListener('click', function () {
                if (timer) {
                    clearInterval(timer);
                    timer = null;
                }
                animKey = '';
                lastState = '';
                showPreview(name, name === 'bid' ? 70000 : 0);
            });
            dock.appendChild(button);
        });
        document.body.appendChild(dock);
        if (which && which !== '1' && which !== 'cycle') {
            showPreview(which, which === 'bid' ? 45000 : 120000);
            return;
        }
        var order = [
            ['intro', 0],
            ['bid', 45000],
            ['bid', 70000],
            ['sold', 120000],
            ['unsold', 0],
            ['withdrawn', 0],
            ['idle', 0]
        ];
        var step = 0;
        function tick() {
            var row = order[step % order.length];
            animKey = row[0] === 'intro' ? '' : animKey;
            showPreview(row[0], row[1]);
            step += 1;
        }
        tick();
        timer = setInterval(tick, 4600);
    }

    window.__acApplyProjector = apply;
    log('Boot', window.YTOV_SLUG || '');
    var preview = previewKind();
    if (preview) {
        runPreview(preview);
    } else if (overlayStatus === 'missing') {
        apply({ player: null, wait_phase: {} });
    }

    if (!preview) fetchOnce(function () {
        if (sseOn && window.AuctionChampSSE && eventsUrl) {
            setConn('CONNECTING');
            window.AuctionChampSSE.bind({
                url: eventsUrl,
                apply: apply,
                startPoll: startPoll,
                // Keep the short poll. SSE still applies a push immediately,
                // but a quiet stream must not leave the points card behind.
                stopPoll: function () {},
                onStampExpiry: function () { fetchOnce(); },
            });
        }
        setConn('CONNECTED');
        startPoll();
    });

    (function bindWatchFullscreen() {
        if (document.documentElement.getAttribute('data-page') !== 'watch') {
            return;
        }
        var btn = document.getElementById('ytWatchFs');
        var landBtn = document.getElementById('ytWatchLandscape');
        var mobileMq = window.matchMedia ? window.matchMedia('(max-width: 900px)') : null;
        function fsEl() {
            return document.fullscreenElement || document.webkitFullscreenElement || null;
        }
        function syncLabel() {
            if (!btn) {
                return;
            }
            btn.textContent = fsEl() ? 'Exit full screen' : 'Fullscreen';
        }
        function isPortraitMobile() {
            if (!mobileMq || !mobileMq.matches) {
                return false;
            }
            return window.innerHeight > window.innerWidth;
        }
        function syncLandscapeBtn() {
            if (!landBtn) {
                return;
            }
            landBtn.textContent = isPortraitMobile() ? 'Landscape' : 'Portrait view';
        }
        function toggleFs() {
            var rootEl = document.documentElement;
            try {
                if (fsEl()) {
                    if (document.exitFullscreen) {
                        document.exitFullscreen();
                    } else if (document.webkitExitFullscreen) {
                        document.webkitExitFullscreen();
                    }
                } else if (rootEl.requestFullscreen) {
                    rootEl.requestFullscreen();
                } else if (rootEl.webkitRequestFullscreen) {
                    rootEl.webkitRequestFullscreen();
                }
            } catch (e) { /* ignore */ }
        }
        function openLandscape() {
            var rootEl = document.documentElement;
            try {
                if (!fsEl()) {
                    if (rootEl.requestFullscreen) {
                        rootEl.requestFullscreen();
                    } else if (rootEl.webkitRequestFullscreen) {
                        rootEl.webkitRequestFullscreen();
                    }
                }
            } catch (e) { /* ignore */ }
            try {
                if (screen.orientation && screen.orientation.lock) {
                    screen.orientation.lock('landscape').catch(function () { /* ignore */ });
                }
            } catch (e2) { /* ignore */ }
        }
        if (btn) {
            btn.addEventListener('click', function (ev) {
                ev.preventDefault();
                toggleFs();
            });
        }
        if (landBtn) {
            landBtn.addEventListener('click', function (ev) {
                ev.preventDefault();
                openLandscape();
            });
        }
        document.addEventListener('fullscreenchange', function () {
            syncLabel();
            syncLandscapeBtn();
            scheduleFit();
        });
        document.addEventListener('webkitfullscreenchange', function () {
            syncLabel();
            syncLandscapeBtn();
            scheduleFit();
        });
        window.addEventListener('orientationchange', function () {
            syncLandscapeBtn();
            scheduleFit();
        });
        window.addEventListener('resize', syncLandscapeBtn);
        syncLabel();
        syncLandscapeBtn();
    })();
})();
