/* Short bid-update cue for Live Board + Projector. Unlock on first gesture. */
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
    function play() {
        var c = audioCtx();
        if (!c) return;
        try {
            var t = c.currentTime;
            var osc = c.createOscillator();
            var g = c.createGain();
            osc.type = 'triangle';
            osc.frequency.setValueAtTime(920, t);
            osc.frequency.exponentialRampToValueAtTime(380, t + 0.09);
            g.gain.setValueAtTime(0.2, t);
            g.gain.exponentialRampToValueAtTime(0.001, t + 0.14);
            osc.connect(g);
            g.connect(c.destination);
            osc.start(t);
            osc.stop(t + 0.15);
        } catch (e) {}
    }
    function bidKey(player) {
        if (!player || player.state !== 'auction') return '0:0:0';
        var bid = Number(player.current_bid || 0) || 0;
        var team = player.current_bid_team || {};
        return String(player.id || 0) + ':' + bid + ':' + String(team.id || 0);
    }
    var lastKey = '';
    function maybePlay(enabled, player) {
        var key = bidKey(player);
        var prev = lastKey;
        lastKey = key;
        if (!enabled || !prev) return;
        var prevId = prev.split(':')[0];
        var bid = Number(player && player.current_bid || 0);
        if (!player || player.state !== 'auction' || !bid) return;
        if (String(player.id || 0) !== prevId) return;
        if (key === prev) return;
        play();
    }
    ['click', 'touchstart', 'keydown'].forEach(function (ev) {
        w.document.addEventListener(ev, unlock, { once: true, capture: true });
    });
    w.acLiveBidTick = { unlock: unlock, play: play, maybePlay: maybePlay };
})(window);
