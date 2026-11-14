/* Connection indicator for the projector and the public live board.
 * Reuses each page's existing LIVE tag. Does not fetch, and does not add
 * a second badge. An open SSE stream counts as healthy: snapshots only
 * arrive when the auction changes.
 */
(function (global) {
  'use strict';

  var staleMs = 2500;
  var hideMs = 4000;
  var state = 'online';
  var lastSuccess = 0;
  var failureSince = 0;
  var streamLive = false;
  var lastBeat = 0;
  var beatMs = 20000;
  var started = false;
  var hideTimer = null;
  var watchTimer = null;

  function livePills() {
    var out = [];
    var pj = document.querySelector('#pj-bar .pj-live-pill');
    var lb = document.getElementById('lbx-live');
    if (pj) out.push(pj);
    if (lb) out.push(lb);
    return out;
  }

  function pillLabel(pill) {
    var label = pill.querySelector('.pj-live-pill-label, .lbx-live-label, .ac-conn-label');
    if (label) return label;
    var nodes = pill.childNodes;
    var i;
    for (i = nodes.length - 1; i >= 0; i--) {
      if (nodes[i].nodeType === 3) pill.removeChild(nodes[i]);
    }
    label = document.createElement('span');
    label.className = pill.id === 'lbx-live' ? 'lbx-live-label' : 'pj-live-pill-label';
    pill.appendChild(label);
    return label;
  }

  function onlineLabel(pill) {
    if (pill.id === 'lbx-live' && document.body && document.body.classList.contains('lb-thankyou-active')) {
      return 'COMPLETE';
    }
    return 'LIVE';
  }

  function paintOne(pill, next, text) {
    pill.classList.remove('is-reconnecting', 'is-offline', 'is-back');
    if (next === 'reconnecting') pill.classList.add('is-reconnecting');
    else if (next === 'offline') pill.classList.add('is-offline');
    else if (next === 'back') pill.classList.add('is-back');
    /* Inline color so the tag changes even before a refreshed stylesheet. */
    if (next === 'reconnecting') pill.style.background = '#8a5a00';
    else if (next === 'offline') pill.style.background = '#8e1b2c';
    else if (next === 'back') pill.style.background = '#0e6b3c';
    else pill.style.background = '';
    pillLabel(pill).textContent = next === 'online' ? onlineLabel(pill) : text;
  }

  function paint(next, text) {
    state = next;
    var pills = livePills();
    var i;
    for (i = 0; i < pills.length; i++) paintOne(pills[i], next, text);
  }

  function clearHide() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function showReconnecting() {
    clearHide();
    if (state === 'offline' && global.navigator && global.navigator.onLine === false) return;
    paint('reconnecting', 'RECONNECTING');
  }

  function showOffline() {
    clearHide();
    paint('offline', 'CONNECTION LOST');
  }

  function showBack() {
    clearHide();
    paint('back', 'BACK ONLINE');
    hideTimer = setTimeout(function () {
      hideTimer = null;
      if (state === 'back') paint('online', '');
    }, hideMs);
  }

  function noteSuccess() {
    var wasDown = state === 'reconnecting' || state === 'offline';
    lastSuccess = Date.now();
    lastBeat = lastSuccess;
    failureSince = 0;
    if (wasDown) {
      showBack();
      return true;
    }
    if (state !== 'back') paint('online', '');
    return false;
  }

  function noteFailure() {
    streamLive = false;
    if (global.navigator && global.navigator.onLine === false) {
      showOffline();
      return;
    }
    if (state === 'offline') return;
    if (state !== 'reconnecting') failureSince = Date.now();
    showReconnecting();
  }

  function noteStreamBeat() {
    streamLive = true;
    lastBeat = Date.now();
    if (state === 'reconnecting' || state === 'offline') noteSuccess();
  }

  function noteStreamOpen() {
    noteStreamBeat();
    if (state === 'offline') showReconnecting();
  }

  function tick() {
    var online = !global.navigator || global.navigator.onLine !== false;
    var now = Date.now();
    if (!online) {
      if (state !== 'offline') showOffline();
      return;
    }
    if (document.hidden) return;
    if (streamLive) return;
    if ((state === 'online' || state === 'back') && lastSuccess && now - lastSuccess > staleMs) {
      showOffline();
      return;
    }
    if (state === 'reconnecting' && failureSince && now - failureSince >= staleMs) {
      showOffline();
    }
  }

  function start(opts) {
    opts = opts || {};
    if (started) return;
    started = true;
    if (opts.staleMs) staleMs = Number(opts.staleMs) || staleMs;
    lastSuccess = Date.now();
    if (global.navigator && global.navigator.onLine === false) showOffline();
    global.addEventListener('offline', function () { showOffline(); });
    global.addEventListener('online', function () {
      if (state !== 'offline') return;
      if (streamLive) {
        noteSuccess();
        return;
      }
      failureSince = Date.now();
      showReconnecting();
    });
    watchTimer = setInterval(tick, 500);
  }

  global.AuctionConnectivity = {
    start: start,
    state: function () { return state; },
    noteSuccess: noteSuccess,
    noteFailure: noteFailure,
    noteStreamOpen: noteStreamOpen,
    noteStreamBeat: noteStreamBeat
  };
})(window);
