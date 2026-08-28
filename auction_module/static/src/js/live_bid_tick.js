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
    function bidKey(player) {
        if (!player) return '0:0:0';
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
    w.acLiveBidTick = { unlock: unlock, play: play, maybePlay: maybePlay };
})(window);
