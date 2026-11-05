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
    var cardEl = playerEl ? playerEl.querySelector('.ipl-player-card') : null;
    var photoEl = document.getElementById('ytovPhoto');
    var photoPhEl = document.getElementById('ytovPhotoPh');
    var nameEl = document.getElementById('ytovName');
    var chipsEl = document.getElementById('ytovChips');
    var metaEl = document.getElementById('ytovMeta');
    var kickerEl = document.getElementById('ytovKicker');
    var iconEl = document.getElementById('ytovIcon');
    var lotEl = document.getElementById('ytovLot');
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
    var pausedEl = document.getElementById('ytovPaused');
    var completeEl = document.getElementById('ytovCompleted');
    var completeStatsEl = document.getElementById('ytovCompleteStats');
    var tickerEl = document.getElementById('ytovTicker');
    var soldEl = document.getElementById('ytovSold');
    var remainEl = document.getElementById('ytovRemain');
    var spendEl = document.getElementById('ytovSpend');
    var recentEl = document.getElementById('ytovRecent');
    var sponsorEl = document.getElementById('ytovSponsor');
    var sponsorTrackEl = document.getElementById('ytovSponsorTrack');
    var timerEl = document.getElementById('ytovTimer');
    var timerValEl = document.getElementById('ytovTimerVal');
    var teamRowEl = document.getElementById('ytovTeamRow');
    var punchEl = document.getElementById('ytovPunch');

    var PLACEHOLDER_PHOTO = '/auction_module/static/description/icon.png';
    var INTRO_MS = 1200;
    var POLL_MIN = 2000;
    var POLL_MAX = 8000;

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
    var tickTimer = null;
    var clockTimer = null;
    var timerPoll = null;
    var preloaded = {};
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

    function chip(text) {
        if (!text) {
            return '';
        }
        return '<span class="ipl-chip">' + esc(text) + '</span>';
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

    function roleLine(p) {
        var bits = [];
        var sport = p.tournament_type || '';
        if (sport === 'football') {
            if (p.dominant_position) {
                bits.push(p.dominant_position);
            }
        } else if (sport === 'kabaddi') {
            if (p.kabaddi_role || p.role) {
                bits.push(p.kabaddi_role || p.role);
            }
        } else if (sport === 'badminton') {
            if (p.badminton_category) {
                bits.push(p.badminton_category);
            }
            if (p.badminton_style) {
                bits.push(p.badminton_style);
            }
        } else if (p.role) {
            bits.push(p.role);
        }
        if (p.tier_name && bits.indexOf(p.tier_name) === -1) {
            bits.push(p.tier_name);
        }
        return bits.map(chip).join('');
    }

    function metaLine(p) {
        var bits = [];
        function add(k, v) {
            v = styleLabel(v);
            if (v) {
                bits.push('<span>' + esc(k) + '<b>' + esc(v) + '</b></span>');
            }
        }
        if (p.jersey) {
            add('No', p.jersey);
        } else if (p.sl_no && p.sl_no !== '?') {
            add('No', p.sl_no);
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
        return bits.slice(0, 4).join('');
    }

    function preload(url) {
        if (!url || preloaded[url]) {
            return;
        }
        preloaded[url] = true;
        try {
            var im = new Image();
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

    function setPhoto(url, name) {
        var src = url || PLACEHOLDER_PHOTO;
        if (photoEl) {
            photoEl.onerror = function () {
                photoEl.removeAttribute('src');
                photoEl.classList.remove('is-on');
                show(photoPhEl, true);
            };
            if (photoEl.getAttribute('data-src-set') !== src) {
                photoEl.setAttribute('data-src-set', src);
                photoEl.src = src;
            }
            photoEl.alt = name || '';
            photoEl.classList.add('is-on');
            show(photoPhEl, !url);
        }
        if (url) {
            preload(url);
        }
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
    }

    function hidePunch() {
        if (!punchEl) {
            return;
        }
        punchEl.classList.remove('is-on');
        punchEl.setAttribute('hidden', 'hidden');
    }

    function showPunch(kind) {
        if (!punchEl) {
            return;
        }
        var same = punchEl.getAttribute('data-kind') === kind && punchEl.classList.contains('is-on') && !punchEl.hasAttribute('hidden');
        punchEl.setAttribute('data-kind', kind);
        punchEl.removeAttribute('hidden');
        if (!same) {
            punchEl.classList.remove('is-on');
            void punchEl.offsetWidth;
            punchEl.classList.add('is-on');
        }
    }

    function shortName(name) {
        var parts = String(name || '').trim().split(/\s+/);
        if (parts.length < 2) {
            return parts[0] || '';
        }
        return parts[0] + ' ' + parts[parts.length - 1].charAt(0) + '.';
    }

    function paintRecent(list) {
        var rows = (list || []).filter(function (row) { return row && row.kind !== 'unsold'; }).slice(0, 3);
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
                '<span class="bc-sale-copy"><span class="bc-sale-name">' + esc(shortName(row.player_name)) + '</span>' +
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
        var remain = prog.remaining != null ? Number(prog.remaining) : Math.max(total - sold, 0);
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
        if (remainEl) {
            remainEl.textContent = String(remain);
        }
        if (spendEl) {
            spendEl.textContent = pts(spend);
        }
        paintRecent(result && result.recent_bids);
        show(tickerEl, total > 0 || sold > 0);
        if (completeStatsEl) {
            completeStatsEl.textContent = sold + ' SOLD  ·  ' + remain + ' REMAINING  ·  SPEND ' + pts(spend);
        }
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
        show(bidTeamEl, true);
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
        if (bidAmt && bidAmt !== lastBid) {
            return 'bid_updated';
        }
        return '';
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
        var uiState = 'IDLE';

        if (completed) {
            uiState = 'COMPLETED';
        } else if (paused && !p) {
            uiState = 'PAUSED';
        } else if (!p) {
            uiState = 'IDLE';
        } else if (pState === 'sold') {
            uiState = 'SOLD';
        } else if (pState === 'unsold') {
            uiState = 'UNSOLD';
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
        paintTicker(result);
        rotateSponsors(result.advertisers || []);
        show(completeEl, completed);
        show(pausedEl, paused && !completed);

        if (completed || !p) {
            show(playerEl, false);
            hidePunch();
            setTimerActive(false);
            if (waitEl) {
                waitEl.textContent = completed
                    ? (wait.message || 'AUCTION COMPLETED')
                    : (paused ? 'AUCTION PAUSED' : idleCopy(result));
            }
            show(waitEl, !completed && !paused);
            lastPlayerId = p ? p.id : null;
            lastBid = bidAmt || null;
            lastState = uiState;
            return;
        }

        show(waitEl, false);
        show(playerEl, true);
        if (cardEl) {
            cardEl.classList.remove('is-sold', 'is-unsold', 'has-live-bid');
        }

        if (nameEl) {
            nameEl.textContent = p.name || '';
        }
        if (lotEl) {
            var lot = p.jersey || (p.sl_no && p.sl_no !== '?' ? p.sl_no : '');
            lotEl.textContent = lot ? ('#' + lot) : '';
            show(lotEl, !!lot);
        }
        show(iconEl, !!p.icon_player);
        setPhoto(p.photo_url, p.name);
        if (chipsEl) {
            chipsEl.innerHTML = roleLine(p);
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
            if (kickerEl) {
                kickerEl.textContent = 'SOLD';
            }
            if (bidValEl) {
                bidValEl.textContent = pts(soldAmt || bidAmt || baseAmt);
            }
            show(liveBoxEl, true);
            show(baseWrapEl, false);
            if (stampEl) {
                stampEl.textContent = 'SOLD';
            }
            show(stampEl, true);
            setTeam(soldTeamName, soldLogo, '', 'Sold to');
            showPunch('sold');
            setTimerActive(false);
        } else if (uiState === 'UNSOLD') {
            if (cardEl) {
                cardEl.classList.add('is-unsold');
            }
            if (kickerEl) {
                kickerEl.textContent = 'UNSOLD';
            }
            if (liveLabelEl) {
                liveLabelEl.textContent = 'UNSOLD';
            }
            if (bidValEl) {
                bidValEl.textContent = '—';
            }
            show(liveBoxEl, true);
            show(baseWrapEl, false);
            if (stampEl) {
                stampEl.textContent = 'UNSOLD';
            }
            show(stampEl, true);
            setTeam('', '', 'Unsold');
            showPunch('unsold');
            setTimerActive(false);
        } else if (bidAmt) {
            if (cardEl) {
                cardEl.classList.add('has-live-bid');
            }
            if (kickerEl) {
                kickerEl.textContent = 'ON AUCTION';
            }
            if (liveLabelEl) {
                liveLabelEl.textContent = 'CURRENT BID';
            }
            if (bidValEl) {
                bidValEl.textContent = pts(bidAmt);
            }
            show(liveBoxEl, true);
            show(baseWrapEl, baseAmt > 0);
            show(stampEl, false);
            hidePunch();
            setTeam(team.name, team.logo_url, 'Current Bid', 'Top Bidder');
            setTimerActive(true);
            if (uiState === 'BID_UPDATE') {
                pulseBid();
            }
        } else {
            if (kickerEl) {
                kickerEl.textContent = 'ON AUCTION';
            }
            if (bidValEl) {
                bidValEl.textContent = pts(baseAmt);
            }
            show(liveBoxEl, true);
            show(baseWrapEl, false);
            show(stampEl, false);
            hidePunch();
            setTeam('', '', '', 'Now Auctioning');
            setTimerActive(true);
        }

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

    function schedule() {
        if (!pollAllowed) {
            return;
        }
        pollTimer = setTimeout(poll, pollDelay());
    }

    function poll() {
        if (!pollAllowed) {
            return;
        }
        fetchOnce(schedule);
    }

    function startPoll() {
        setConn(connState === 'CONNECTING' ? 'CONNECTING' : 'RECONNECTING');
        pollAllowed = true;
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

    window.__acApplyProjector = apply;
    log('Boot', window.YTOV_SLUG || '');
    if (overlayStatus === 'missing') {
        apply({ player: null, wait_phase: {} });
    }

    fetchOnce(function () {
        if (sseOn && window.AuctionChampSSE && eventsUrl) {
            setConn('CONNECTING');
            window.AuctionChampSSE.bind({
                url: eventsUrl,
                apply: apply,
                startPoll: startPoll,
                stopPoll: stopPoll,
                onStampExpiry: function () { fetchOnce(); },
            });
        } else {
            setConn('CONNECTED');
            startPoll();
        }
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
