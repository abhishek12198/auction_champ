/* Bid-summary purse: count a team's points down after a sale and play the coin drop once. */
(function (w) {
  'use strict';
  var SRC = '/auction_module/static/src/audio/sold_coin.wav?v=2';
  var DURATION = 300;
  var clip = null;
  var lastSound = 0;
  var runs = typeof WeakMap === 'function' ? new WeakMap() : null;

  function parseShown(text) {
    var raw = String(text || '').replace(/,/g, '');
    var match = raw.match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : NaN;
  }

  function formatStep(n) {
    var rounded = Math.round(n);
    if (typeof w.fmtUnit === 'function') {
      try { return w.fmtUnit(rounded); } catch (e) {}
    }
    try { return rounded.toLocaleString(); } catch (e2) { return String(rounded); }
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

  function playCoins() {
    var now = Date.now();
    if (now - lastSound < 900) return;
    try {
      if (w.sessionStorage && w.sessionStorage.getItem('acSoldCoinMuted') === '1') return;
    } catch (e) {}
    lastSound = now;
    try {
      var c = audio();
      c.currentTime = 0;
      var pending = c.play();
      if (pending && pending.catch) pending.catch(function () {});
    } catch (e2) {}
  }

  function remember(el, raf) {
    if (runs) runs.set(el, raf);
    else el._acPurseRaf = raf;
  }
  function recall(el) {
    if (runs) return runs.get(el);
    return el._acPurseRaf;
  }
  function forget(el) {
    if (runs) runs.delete(el);
    else el._acPurseRaf = 0;
  }

  function tick(el, value, finalText) {
    var target = Number(value);
    if (!el || !isFinite(target)) {
      if (el && finalText != null) el.textContent = finalText;
      return;
    }
    var from = parseShown(el.textContent);
    if (!isFinite(from) || from === target || target > from) {
      el.textContent = finalText;
      return;
    }
    var reduce = w.matchMedia && w.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      el.textContent = finalText;
      playCoins();
      return;
    }
    var prev = recall(el);
    if (prev) w.cancelAnimationFrame(prev);
    var start = w.performance && w.performance.now ? w.performance.now() : Date.now();
    el.classList.add('is-purse-tick');
    playCoins();
    function frame(now) {
      var t = Math.min(1, (now - start) / DURATION);
      var eased = 1 - Math.pow(1 - t, 3);
      if (t < 1) {
        el.textContent = formatStep(from + (target - from) * eased);
        remember(el, w.requestAnimationFrame(frame));
      } else {
        el.textContent = finalText;
        el.classList.remove('is-purse-tick');
        forget(el);
      }
    }
    remember(el, w.requestAnimationFrame(frame));
  }

  w.acPurseTick = tick;

  function unlock() {
    try {
      var c = audio();
      var pending = c.play();
      if (pending && pending.then) {
        pending.then(function () {
          c.pause();
          c.currentTime = 0;
        }).catch(function () {});
      }
    } catch (e) {}
  }
  w.addEventListener('pointerdown', unlock, { once: true });
  w.addEventListener('keydown', unlock, { once: true });

  var style = w.document.createElement('style');
  style.textContent = [
    '.bs2-purse-value.is-purse-tick,',
    '.bs2-card-purse-value.is-purse-tick,',
    '.bs2-mob-pts.is-purse-tick{',
    'color:#f5c518;',
    'text-shadow:0 0 14px rgba(245,197,24,.45);',
    'font-variant-numeric:tabular-nums;',
    '}'
  ].join('');
  (w.document.head || w.document.documentElement).appendChild(style);
})(window);
