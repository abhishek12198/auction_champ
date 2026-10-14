/* Shared owner-bid tick-tock clock for display_auction + roll call. */
(function (window, document) {
    'use strict';
    var CIRC = 2 * Math.PI * 15.5;
    var S = {enabled: false, running: false, frozen: false, held: false, remainUntil: 0, heldLeft: 0, seconds: 0};
    var pollTimer = null;
    var tickTimer = null;
    var holdBusy = false;
    var bound = false;
    var lastEpoch = 0;

    function clocks() {
        return document.querySelectorAll('[data-bid-clock]');
    }

    function ctrlClocks() {
        return document.querySelectorAll('[data-bid-clock-ctrl]');
    }

    function canToggle() {
        return S.enabled && (S.running || S.held) && !S.frozen;
    }

    function tipText() {
        return S.held ? 'Click to resume' : 'Click to hold';
    }

    window.acBidClockMarkup = function (id) {
        return (
            '<div class="ac-bid-clock" data-bid-clock="' + (id || '') + '" hidden="hidden">' +
              '<svg class="ac-bid-clock-svg" viewBox="0 0 36 36" aria-hidden="true">' +
                '<circle class="ac-bid-clock-track" cx="18" cy="18" r="15.5"></circle>' +
                '<circle class="ac-bid-clock-arc" cx="18" cy="18" r="15.5"></circle>' +
              '</svg>' +
              '<span class="ac-bid-clock-num">0</span>' +
            '</div>'
        );
    };

    function hideAll() {
        clocks().forEach(function (el) {
            el.hidden = true;
            el.classList.remove('is-blink', 'is-urgent', 'is-held', 'is-ctrl');
        });
        syncClockControls();
    }

    function syncClockControls() {
        var clickable = canToggle();
        var tip = tipText();
        ctrlClocks().forEach(function (el) {
            el.classList.toggle('is-ctrl', clickable);
            el.setAttribute('role', clickable ? 'button' : 'img');
            if (clickable) el.setAttribute('tabindex', '0');
            else el.removeAttribute('tabindex');
            el.setAttribute('aria-label', clickable ? tip : 'Bid timer');
            el.setAttribute('title', clickable ? tip : '');
            var tipEl = el.querySelector('[data-bid-clock-tip]');
            if (tipEl) tipEl.textContent = tip;
        });
    }

    function paint() {
        var nodes = clocks();
        if (!nodes.length) return;
        if (!S.enabled || (!S.running && !S.frozen && !S.held)) {
            hideAll();
            return;
        }
        var left = S.held
            ? Math.max(0, S.heldLeft)
            : (S.frozen ? 0 : Math.max(0, (S.remainUntil - Date.now()) / 1000));
        if (!S.held && left <= 0) {
            S.frozen = true;
            S.running = false;
            left = 0;
        }
        var shown = Math.ceil(left);
        var span = S.seconds > 0 ? S.seconds : left;
        var gone = span > 0 ? Math.min(1, Math.max(0, 1 - (left / span))) : 1;
        var urgent = !S.held && (S.frozen || left <= 5);
        nodes.forEach(function (el) {
            el.hidden = false;
            el.classList.toggle('is-urgent', urgent);
            el.classList.toggle('is-blink', urgent && S.running);
            el.classList.toggle('is-held', !!S.held);
            var num = el.querySelector('.ac-bid-clock-num');
            if (num && num.textContent !== String(shown)) num.textContent = shown;
            var arc = el.querySelector('.ac-bid-clock-arc');
            if (arc) {
                arc.style.strokeDasharray = String(CIRC);
                arc.style.strokeDashoffset = String(CIRC * gone);
            }
        });
        syncClockControls();
    }

    window.acBidClockSync = function (timer) {
        timer = timer || {};
        var epoch = Number(timer.epoch || 0);
        if (epoch && lastEpoch && epoch + 0.0001 < lastEpoch) return;
        if (S.held && timer.running && !timer.held) {
            if ((Number(timer.remaining) || 0) + 0.6 < (Number(S.heldLeft) || 0)) return;
        }
        if (epoch) lastEpoch = epoch;
        if (!timer.enabled || timer.state === 'sold' || timer.state === 'unsold') {
            S = {enabled: false, running: false, frozen: false, held: false, remainUntil: 0, heldLeft: 0, seconds: 0};
        } else if (timer.held) {
            S = {
                enabled: true,
                running: false,
                frozen: false,
                held: true,
                remainUntil: 0,
                heldLeft: Math.max(0, timer.remaining || 0),
                seconds: timer.seconds || 0,
            };
        } else if (timer.frozen) {
            S = {enabled: true, running: false, frozen: true, held: false, remainUntil: 0, heldLeft: 0, seconds: timer.seconds || 0};
        } else if (timer.running) {
            S = {
                enabled: true,
                running: true,
                frozen: false,
                held: false,
                remainUntil: Date.now() + Math.max(0, (timer.remaining || 0) * 1000),
                heldLeft: 0,
                seconds: timer.seconds || 0,
            };
        } else {
            S = {enabled: true, running: false, frozen: false, held: false, remainUntil: 0, heldLeft: 0, seconds: timer.seconds || 0};
        }
        paint();
        if (!tickTimer) tickTimer = setInterval(paint, 250);
    };

    function timerUrl() {
        var parts = (location.pathname || '').split('/').filter(Boolean);
        var db = window.AUCTION_DB_NAME || parts[0] || '';
        var qs = [];
        var pid = document.body && document.body.getAttribute('data-player-id');
        var tid = (window.AUCTION_TOURNAMENT_ID || (document.body && document.body.getAttribute('data-tournament-id')) || '');
        if (pid) qs.push('player_id=' + encodeURIComponent(pid));
        if (tid) qs.push('tournament_id=' + encodeURIComponent(tid));
        var path = (db ? '/' + db : '') + '/auction/bid_timer';
        return qs.length ? path + '?' + qs.join('&') : path;
    }

    function holdUrl(action) {
        return timerUrl().replace('/auction/bid_timer', '/auction/bid_timer/' + action);
    }

    function poll() {
        fetch(timerUrl(), {cache: 'no-store', credentials: 'same-origin'})
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
            .then(window.acBidClockSync)
            .catch(function () {});
    }

    window.acBidClockToggleHold = function () {
        if (holdBusy || !canToggle()) return;
        holdBusy = true;
        var action = S.held ? 'resume' : 'hold';
        fetch(holdUrl(action), {method: 'POST', cache: 'no-store', credentials: 'same-origin'})
            .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
            .then(window.acBidClockSync)
            .catch(function () {})
            .then(function () { holdBusy = false; });
    };

    function bindClockClicks() {
        if (bound) return;
        bound = true;
        document.addEventListener('click', function (ev) {
            var el = ev.target && ev.target.closest && ev.target.closest('[data-bid-clock-ctrl]');
            if (!el || el.hidden) return;
            ev.preventDefault();
            window.acBidClockToggleHold();
        });
        document.addEventListener('keydown', function (ev) {
            if (ev.key !== 'Enter' && ev.key !== ' ') return;
            var el = ev.target && ev.target.closest && ev.target.closest('[data-bid-clock-ctrl]');
            if (!el || el.hidden) return;
            ev.preventDefault();
            window.acBidClockToggleHold();
        });
    }

    window.acBidClockStart = function () {
        bindClockClicks();
        poll();
        if (!pollTimer) pollTimer = setInterval(poll, 1000);
        if (!tickTimer) tickTimer = setInterval(paint, 250);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window.acBidClockStart);
    } else {
        window.acBidClockStart();
    }
})(window, document);
