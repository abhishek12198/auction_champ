/* Bell cue on each live bid for Live Board + Projector.
   bid_bell.mp3 is Pixabay sound effect 390294 (Bell Ring), free under the
   Pixabay Content License. Unlock on first gesture. */
(function (w) {
    'use strict';
    var SRC = '/auction_module/static/src/audio/bid_bell.mp3?v=1';
    var clip = null;
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
    function play() {
        try {
            var c = audio();
            c.pause();
            c.currentTime = 0;
            var pending = c.play();
            if (pending && pending.catch) pending.catch(function () {});
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
