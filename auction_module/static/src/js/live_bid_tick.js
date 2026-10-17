/* Coin-clink cue on each live bid for Live Board + Projector. Unlock on first gesture. */
(function (w) {
    'use strict';
    var ctx;
    function audioCtx() {
        var AC = w.AudioContext || w.webkitAudioContext;
        if (!AC) return null;
        if (!ctx) ctx = new AC();
        if (ctx.state === 'suspended') {
            try { ctx.resume(); } catch (e) {}
        }
        return ctx;
    }
    function unlock() {
        var c = audioCtx();
        if (!c) return;
        try {
            var buf = c.createBuffer(1, 1, 22050);
            var src = c.createBufferSource();
            src.buffer = buf;
            src.connect(c.destination);
            src.start(0);
        } catch (e) {}
    }
    function ping(c, t, freq, dur, vol) {
        var osc = c.createOscillator();
        var g = c.createGain();
        osc.type = 'square';
        osc.frequency.setValueAtTime(freq, t);
        osc.frequency.exponentialRampToValueAtTime(Math.max(180, freq * 0.55), t + dur);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(vol, t + 0.008);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        osc.connect(g);
        g.connect(c.destination);
        osc.start(t);
        osc.stop(t + dur + 0.02);
    }
    function clinkNoise(c, t, dur, vol) {
        var n = c.sampleRate * dur;
        var buf = c.createBuffer(1, n, c.sampleRate);
        var data = buf.getChannelData(0);
        for (var i = 0; i < n; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / n);
        var src = c.createBufferSource();
        src.buffer = buf;
        var bp = c.createBiquadFilter();
        bp.type = 'highpass';
        bp.frequency.value = 1800;
        var g = c.createGain();
        g.gain.setValueAtTime(vol, t);
        g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
        src.connect(bp);
        bp.connect(g);
        g.connect(c.destination);
        src.start(t);
        src.stop(t + dur);
    }
    function play() {
        var c = audioCtx();
        if (!c) return;
        try {
            var t = c.currentTime;
            clinkNoise(c, t, 0.05, 0.09);
            ping(c, t, 1960, 0.09, 0.16);
            ping(c, t + 0.045, 2620, 0.11, 0.14);
            ping(c, t + 0.09, 3320, 0.08, 0.1);
        } catch (e) {}
    }
    /* Key on player + bid amount only. The leading team can arrive in a later
       update than the amount (or change without a new bid), which used to make
       the cue play twice — once for the amount, once for the team. */
    function bidKey(player) {
        if (!player) return '0:0';
        var bid = Number(player.current_bid || 0) || 0;
        return String(player.id || 0) + ':' + bid;
    }
    var lastKey = '';
    function maybePlay(enabled, player) {
        var key = bidKey(player);
        var prev = lastKey;
        lastKey = key;
        if (!enabled || !prev) return;
        if (!player || player.state === 'sold' || player.state === 'unsold') return;
        var prevId = prev.split(':')[0];
        var bid = Number(player.current_bid || 0);
        if (!bid) return;
        if (String(player.id || 0) !== prevId) return;
        if (key === prev) return;
        play();
    }
    ['click', 'touchstart', 'keydown'].forEach(function (ev) {
        w.document.addEventListener(ev, unlock, { once: true, capture: true });
    });
    function ensureProjectorGloss() {
        if (!document.getElementById('pj-root')) return;
        if (document.getElementById('pjGlossCss')) return;
        var link = document.createElement('link');
        link.id = 'pjGlossCss';
        link.rel = 'stylesheet';
        link.href = '/auction_module/static/src/css/projector_gloss.css?v=2';
        (document.head || document.documentElement).appendChild(link);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ensureProjectorGloss);
    } else {
        ensureProjectorGloss();
    }
    function ensureEmptyBidStyle() {
        if (document.getElementById('pjEmptyBidStyle')) return;
        var css = document.createElement('style');
        css.id = 'pjEmptyBidStyle';
        css.textContent = [
            '.pj-live-bid.is-waiting{display:flex !important}',
            '.pj-live-bid.is-waiting .pj-live-bid__sub,',
            '.pj-live-bid.is-waiting .pj-live-bid__team{display:none !important}',
            '.pj-live-bid.is-waiting .pj-live-bid__waiting{display:flex !important}',
            '.pj-live-bid.is-waiting .pj-live-bid__amount{',
            'font-family:inherit !important;font-weight:800 !important;',
            'font-size:clamp(1.25rem,3.4vh,2.1rem) !important;line-height:1.2 !important;',
            'letter-spacing:.05em !important;text-transform:uppercase !important;',
            'white-space:normal !important;color:var(--tx,#f4f4f4) !important;',
            'text-shadow:none !important}',
            '[data-theme="lemon"] .pj-live-bid.is-waiting .pj-live-bid__amount,',
            '[data-theme="vanilla"] .pj-live-bid.is-waiting .pj-live-bid__amount{color:#1F1A0A !important}',
            '[data-theme="lemon"] .pj-live-bid.is-waiting .pj-live-bid__waiting,',
            '[data-theme="vanilla"] .pj-live-bid.is-waiting .pj-live-bid__waiting{color:#3a2a10 !important}'
        ].join('');
        (document.head || document.documentElement).appendChild(css);
    }

    function hideProjectorEmptyBid() {
        var root = document.getElementById('pjLiveBid');
        var wait = document.getElementById('pjLiveBidWaiting');
        if (root) root.classList.remove('is-waiting');
        if (wait) wait.style.display = 'none';
    }

    function paintProjectorEmptyBid(player) {
        var root = document.getElementById('pjLiveBid');
        var valEl = document.getElementById('pjLiveBidVal');
        var wait = document.getElementById('pjLiveBidWaiting');
        if (!root || !valEl) return;
        var bid = Number((player && player.current_bid) || 0);
        var closed = !player || player.state === 'sold' || player.state === 'unsold' || player.state === 'withdrawn';
        if (closed || bid > 0) {
            hideProjectorEmptyBid();
            return;
        }
        ensureEmptyBidStyle();
        root.style.display = 'flex';
        root.classList.add('is-waiting');
        root.classList.remove('is-sold', 'is-unsold');
        valEl.style.fontSize = '';
        valEl.textContent = 'No paddle raised yet';
        var label = document.getElementById('pjLiveBidLabel');
        if (label) label.textContent = 'Bidding Open';
        if (wait) {
            wait.style.display = 'flex';
            var copy = wait.querySelector('span:not(.pj-live-bid__wait-dot)');
            if (copy) copy.textContent = 'The floor is open. Waiting for the first bid.';
        }
        var teamEl = document.getElementById('pjLiveBidTeam');
        if (teamEl) teamEl.style.display = 'none';
    }

    function wrapProjectorPoll() {
        var prev = w._pjOnPollResult;
        if (typeof prev === 'function' && prev._emptyBidWrapped) return;
        var wrapped = function (result) {
            if (typeof prev === 'function') prev(result);
            paintProjectorEmptyBid(result && result.player);
        };
        wrapped._emptyBidWrapped = true;
        w._pjOnPollResult = wrapped;
    }

    function watchProjectorPoll() {
        wrapProjectorPoll();
        var n = 0;
        var t = setInterval(function () {
            wrapProjectorPoll();
            if (++n > 40) clearInterval(t);
        }, 250);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watchProjectorPoll);
    } else {
        watchProjectorPoll();
    }

    w.acLiveBidTick = {
        unlock: unlock,
        play: play,
        maybePlay: maybePlay,
        paintProjectorEmptyBid: paintProjectorEmptyBid,
    };
})(window);
