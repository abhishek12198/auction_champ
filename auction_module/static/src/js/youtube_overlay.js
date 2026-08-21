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
    var photoEl = document.getElementById('ytovPhoto');
    var photoPhEl = document.getElementById('ytovPhotoPh');
    var nameEl = document.getElementById('ytovName');
    var chipsEl = document.getElementById('ytovChips');
    var lotEl = document.getElementById('ytovLot');
    var baseValEl = document.getElementById('ytovBaseVal');
    var liveBoxEl = document.getElementById('ytovLiveBox');
    var liveLabelEl = document.getElementById('ytovLiveLabel');
    var bidValEl = document.getElementById('ytovBidVal');
    var bidTeamEl = document.getElementById('ytovBidTeam');
    var bidTeamLogoEl = document.getElementById('ytovBidTeamLogo');
    var bidTeamLogoPhEl = document.getElementById('ytovBidTeamLogoPh');
    var bidTeamNameEl = document.getElementById('ytovBidTeamName');
    var stampEl = document.getElementById('ytovStamp');
    var progressEl = document.getElementById('ytovProgress');
    var pausedEl = document.getElementById('ytovPaused');
    var completeEl = document.getElementById('ytovCompleted');
    var sponsorEl = document.getElementById('ytovSponsor');
    var sponsorTrackEl = document.getElementById('ytovSponsorTrack');

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
    var preloaded = {};
    var sponsorKey = '';
    var connState = 'CONNECTING';
    var overlayStatus = (document.documentElement.getAttribute('data-overlay-status') || 'ok');

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
        } catch (e) {
            return String(num) + ' PTS';
        }
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

    function playerChips(p) {
        var bits = [];
        if (p.tier_name) {
            bits.push(p.tier_name);
        }
        if (p.tournament_type === 'football' || p.dominant_position) {
            if (p.dominant_position) {
                bits.push(p.dominant_position);
            }
            if (p.preferred_foot) {
                bits.push(p.preferred_foot);
            }
        } else {
            if (p.role) {
                bits.push(p.role);
            }
            var batting = styleLabel(p.batting_style);
            var bowling = styleLabel(p.bowling_style);
            if (batting) {
                bits.push(batting);
            }
            if (bowling) {
                bits.push(bowling);
            }
        }
        return bits.map(chip).join('');
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

    function fitCanvas() {
        if (!root) {
            return;
        }
        if (document.documentElement.getAttribute('data-page') === 'watch') {
            root.style.transform = '';
            return;
        }
        var w = window.innerWidth || 1920;
        var h = window.innerHeight || 1080;
        var s = Math.min(w / 1920, h / 1080);
        root.style.transform = 'scale(' + s + ')';
    }

    function setPhoto(url, name) {
        var src = url || PLACEHOLDER_PHOTO;
        if (photoEl) {
            photoEl.onerror = function () {
                photoEl.removeAttribute('src');
                photoEl.classList.remove('is-on');
                show(photoPhEl, true);
            };
            if (photoEl.src !== src) {
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

    function setTeam(name, logoUrl) {
        if (bidTeamNameEl) {
            bidTeamNameEl.textContent = name || '';
        }
        if (bidTeamLogoEl) {
            if (logoUrl) {
                bidTeamLogoEl.onerror = function () {
                    bidTeamLogoEl.setAttribute('hidden', 'hidden');
                    show(bidTeamLogoPhEl, true);
                };
                if (bidTeamLogoEl.src !== logoUrl) {
                    bidTeamLogoEl.src = logoUrl;
                }
                bidTeamLogoEl.removeAttribute('hidden');
                show(bidTeamLogoPhEl, false);
                preload(logoUrl);
            } else {
                bidTeamLogoEl.setAttribute('hidden', 'hidden');
                show(bidTeamLogoPhEl, !!name);
            }
        }
        if (bidTeamLogoPhEl && name && !logoUrl) {
            bidTeamLogoPhEl.textContent = String(name).charAt(0).toUpperCase();
        }
        show(bidTeamEl, !!(name || logoUrl));
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
        for (var i = 0; i < ads.length; i++) {
            var ad = ads[i];
            if (!ad || !ad.image_url) {
                continue;
            }
            var img = document.createElement('img');
            img.className = 'sponsor-logo';
            img.src = ad.image_url;
            img.alt = ad.name || '';
            img.title = ad.name || '';
            sponsorTrackEl.appendChild(img);
            preload(ad.image_url);
            shown += 1;
        }
        show(sponsorEl, shown > 0);
        if (root) {
            root.classList.toggle('has-sponsors', shown > 0);
        }
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
        return wait.idle_headline || wait.message || 'Waiting for next player';
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
        var prog = result.progress || {};
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
        if (paused && p && uiState !== 'COMPLETED') {
            /* Keep player/bid graphics; banner is additive. */
        }

        var evt = mapEvent(p, bidAmt, uiState);
        if (evt) {
            log('Event: ' + evt, p ? ('Player: ' + p.id) : '', bidAmt ? ('Amount: ' + bidAmt) : '');
        }

        setUiState(uiState);
        if (progressEl) {
            progressEl.textContent = prog.label || '';
        }
        rotateSponsors(result.advertisers || []);

        show(completeEl, completed);
        show(pausedEl, paused && !completed);

        if (completed || !p) {
            show(playerEl, false);
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
        if (playerEl) {
            playerEl.classList.remove('is-sold', 'is-unsold', 'has-live-bid');
        }

        if (nameEl) {
            nameEl.textContent = p.name || '';
        }
        if (lotEl) {
            var lot = p.sl_no;
            lotEl.textContent = lot && lot !== '?' ? ('LOT #' + lot) : '';
            show(lotEl, !!(lot && lot !== '?'));
        }
        setPhoto(p.photo_url, p.name);
        if (chipsEl) {
            chipsEl.innerHTML = playerChips(p);
        }
        if (baseValEl) {
            baseValEl.textContent = pts(baseAmt);
        }

        var team = p.current_bid_team || {};
        var soldTeamName = p.team_name || '';
        var soldLogo = p.team_logo_url || '';

        if (uiState === 'SOLD') {
            if (playerEl) {
                playerEl.classList.add('is-sold');
            }
            if (liveLabelEl) {
                liveLabelEl.textContent = 'Sold';
            }
            if (bidValEl) {
                bidValEl.textContent = pts(soldAmt || bidAmt || baseAmt);
            }
            show(liveBoxEl, true);
            if (stampEl) {
                stampEl.textContent = 'SOLD';
            }
            show(stampEl, true);
            setTeam(soldTeamName, soldLogo);
        } else if (uiState === 'UNSOLD') {
            if (playerEl) {
                playerEl.classList.add('is-unsold');
            }
            show(liveBoxEl, false);
            if (stampEl) {
                stampEl.textContent = 'UNSOLD';
            }
            show(stampEl, true);
            setTeam('', '');
        } else if (bidAmt) {
            if (playerEl) {
                playerEl.classList.add('has-live-bid');
            }
            if (liveLabelEl) {
                liveLabelEl.textContent = 'Current Bid';
            }
            if (bidValEl) {
                bidValEl.textContent = pts(bidAmt);
            }
            show(liveBoxEl, true);
            show(stampEl, false);
            setTeam(team.name, team.logo_url);
            if (uiState === 'BID_UPDATE') {
                pulseBid();
            }
        } else {
            show(liveBoxEl, false);
            show(stampEl, false);
            setTeam('', '');
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
        var n = Math.min(POLL_MAX, POLL_MIN * Math.pow(1.5, failStreak));
        return n;
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

    window.addEventListener('resize', fitCanvas);
    fitCanvas();

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
            fitCanvas();
        });
        document.addEventListener('webkitfullscreenchange', function () {
            syncLabel();
            syncLandscapeBtn();
            fitCanvas();
        });
        window.addEventListener('orientationchange', syncLandscapeBtn);
        window.addEventListener('resize', syncLandscapeBtn);
        syncLabel();
        syncLandscapeBtn();
    })();
})();
