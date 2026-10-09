/* Sold-coin cue for Projector + Live Board.
   sold_coin.wav is an original synthesis (no third-party sample).
   One play per confirmed sale. Refresh and repeat polls do not replay it. */
(function (w) {
    'use strict';
    var SRC = '/auction_module/static/src/audio/sold_coin.wav?v=2';
    var MUTE_KEY = 'acSoldCoinMuted';
    var PLAYED_KEY = 'acSoldCoinPlayed';
    var clip = null;
    var prev = null;
    var played = {};
    var blockedKey = '';
    var pendingKey = '';

    function storageGet(key) {
        try { return w.sessionStorage.getItem(key) || ''; } catch (e) { return ''; }
    }
    function storageSet(key, val) {
        try { w.sessionStorage.setItem(key, val); } catch (e) {}
    }
    function isMuted() {
        return storageGet(MUTE_KEY) === '1';
    }
    function remembered(key) {
        var raw = storageGet(PLAYED_KEY);
        if (!raw) return false;
        return raw.split(',').indexOf(key) >= 0;
    }
    function remember(key) {
        var raw = storageGet(PLAYED_KEY);
        var list = raw ? raw.split(',') : [];
        if (list.indexOf(key) < 0) list.push(key);
        if (list.length > 40) list = list.slice(list.length - 40);
        storageSet(PLAYED_KEY, list.join(','));
        played[key] = 1;
    }
    function audio() {
        if (!clip) {
            clip = new w.Audio(SRC);
            clip.preload = 'auto';
            clip.volume = 0.9;
            try { clip.setAttribute('playsinline', 'true'); } catch (e) {}
            try { clip.load(); } catch (e2) {}
        }
        return clip;
    }
    function buttons() {
        return [w.document.getElementById('pjCoinBtn'), w.document.getElementById('lbCoinBtn')];
    }
    function paint(enabled) {
        var muted = isMuted();
        var blocked = !!blockedKey;
        buttons().forEach(function (btn) {
            if (!btn) return;
            if (!enabled) {
                btn.hidden = true;
                return;
            }
            btn.hidden = false;
            btn.classList.toggle('is-muted', muted);
            btn.classList.toggle('is-blocked', blocked && !muted);
            var label = muted ? 'Sold coin sound off' : (blocked ? 'Enable sold coin sound' : 'Mute sold coin sound');
            btn.title = label;
            btn.setAttribute('aria-label', label);
            btn.setAttribute('aria-pressed', muted ? 'true' : 'false');
        });
    }
    function unlock() {
        try {
            var c = audio();
            var p = c.play();
            if (p && p.then) {
                p.then(function () {
                    c.pause();
                    c.currentTime = 0;
                }).catch(function () {});
            }
        } catch (e) {}
    }
    function playKey(key) {
        var c = audio();
        try {
            c.pause();
            c.currentTime = 0;
        } catch (e) {}
        var p = c.play();
        if (p && p.then) {
            p.then(function () {
                blockedKey = '';
                pendingKey = '';
                paint(true);
            }).catch(function () {
                delete played[key];
                blockedKey = key;
                pendingKey = key;
                paint(true);
            });
        }
    }
    function maybePlay(enabled, player, amount) {
        var on = !!enabled;
        paint(on);
        var id = player && player.id ? String(player.id) : '';
        var state = (player && player.state) || '';
        var pts = Number(amount || (player && player.sold_points) || 0);
        var before = prev;
        prev = { id: id, state: state, pts: pts };
        if (!before || !on || !player) return;
        if (state !== 'sold' || !(pts > 0)) return;
        if (before.id === id && before.state === 'sold' && before.pts > 0) return;
        var key = id + ':' + pts;
        if (played[key] || remembered(key) || blockedKey === key) return;
        if (isMuted()) return;
        remember(key);
        playKey(key);
    }
    function onButton(ev) {
        var btn = ev.target && ev.target.closest ? ev.target.closest('#pjCoinBtn, #lbCoinBtn') : null;
        if (!btn) return;
        ev.preventDefault();
        unlock();
        if (blockedKey || pendingKey) {
            storageSet(MUTE_KEY, '0');
            var key = pendingKey || blockedKey;
            blockedKey = '';
            pendingKey = '';
            if (key && !played[key]) remember(key);
            if (key) playKey(key);
            paint(true);
            return;
        }
        var next = isMuted() ? '0' : '1';
        storageSet(MUTE_KEY, next);
        if (next === '1') {
            try { audio().pause(); } catch (e) {}
        }
        paint(true);
    }
    ['click', 'touchstart', 'keydown'].forEach(function (ev) {
        w.document.addEventListener(ev, unlock, { once: true, capture: true });
    });
    w.document.addEventListener('click', onButton);
    try { audio(); } catch (e) {}
    w.acSoldCoin = { maybePlay: maybePlay, unlock: unlock };
})(window);
