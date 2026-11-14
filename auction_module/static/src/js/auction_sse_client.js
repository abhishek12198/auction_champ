/* AuctionChamp Phase 3 — SSE primary with polling fallback.
 * Pages define:
 *   window.__acApplyLiveBoard(data)
 *   window.__acApplyProjector(result)
 *   window.__acApplyBalance(payload)
 * and optional start/stop poll functions.
 */
(function (global) {
  'use strict';

  /* LIVE tags on the projector and the public live board. This runs even when
     the page was rendered before AuctionConnectivity was added to the template. */
  var pillKind = 'online';
  var pillTimer = null;
  function livePills() {
    var out = [];
    var pj = document.querySelector('#pj-bar .pj-live-pill');
    var lb = document.getElementById('lbx-live');
    if (pj) out.push(pj);
    if (lb) out.push(lb);
    return out;
  }
  function paintPill(kind) {
    if (kind === 'reconnecting' && (pillKind === 'reconnecting' || pillKind === 'offline')) return;
    var pills = livePills();
    if (!pills.length) return;
    pillKind = kind;
    var text = 'LIVE';
    var bg = '';
    if (kind === 'reconnecting') { text = 'RECONNECTING'; bg = '#8a5a00'; }
    else if (kind === 'offline') { text = 'CONNECTION LOST'; bg = '#8e1b2c'; }
    else if (kind === 'back') { text = 'BACK ONLINE'; bg = '#0e6b3c'; }
    var i;
    for (i = 0; i < pills.length; i++) {
      var pill = pills[i];
      var label = pill.querySelector('.pj-live-pill-label, .lbx-live-label, .ac-conn-label');
      if (!label) {
        var nodes = pill.childNodes;
        var n;
        for (n = nodes.length - 1; n >= 0; n--) {
          if (nodes[n].nodeType === 3) pill.removeChild(nodes[n]);
        }
        label = document.createElement('span');
        label.className = pill.id === 'lbx-live' ? 'lbx-live-label' : 'pj-live-pill-label';
        pill.appendChild(label);
      }
      var shown = text;
      if (kind === 'online' && pill.id === 'lbx-live' && document.body && document.body.classList.contains('lb-thankyou-active')) {
        shown = 'COMPLETE';
      }
      label.textContent = shown;
      pill.style.background = bg;
      pill.classList.remove('is-reconnecting', 'is-offline', 'is-back');
      if (kind === 'reconnecting' || kind === 'offline' || kind === 'back') pill.classList.add('is-' + kind);
    }
    if (pillTimer) { clearTimeout(pillTimer); pillTimer = null; }
    if (kind === 'reconnecting') {
      pillTimer = setTimeout(function () {
        pillTimer = null;
        if (pillKind === 'reconnecting') paintPill('offline');
      }, 2500);
    } else if (kind === 'back') {
      pillTimer = setTimeout(function () {
        pillTimer = null;
        if (pillKind === 'back') paintPill('online');
      }, 4000);
    }
  }
  function signalDown() {
    if (global.AuctionConnectivity) global.AuctionConnectivity.noteFailure();
    else paintPill('reconnecting');
  }
  function signalUp() {
    if (global.AuctionConnectivity) global.AuctionConnectivity.noteStreamBeat();
    else if (pillKind === 'reconnecting' || pillKind === 'offline') paintPill('back');
  }
  global.addEventListener('offline', function () {
    if (!global.AuctionConnectivity) paintPill('offline');
  });

  function sseEnabled(el) {
    if (!el) return false;
    var v = el.getAttribute('data-sse-enabled');
    return v === '1' || v === 'true' || v === 'True';
  }

  function bindSse(opts) {
    opts = opts || {};
    var url = opts.url;
    var apply = opts.apply;
    var startPoll = opts.startPoll || function () {};
    var stopPoll = opts.stopPoll || function () {};
    var onStampExpiry = opts.onStampExpiry || null;
    var onOpen = opts.onOpen || null;
    var onError = opts.onError || null;
    var onPing = opts.onPing || null;
    var stampTimer = null;
    var beatTimer = null;
    var lastBeat = Date.now();
    var beatMs = 20000;
    var staleFired = false;
    var seenPing = false;

    if (!url || typeof apply !== 'function' || typeof EventSource === 'undefined') {
      startPoll();
      return null;
    }

    var es = null;
    var closed = false;

    function clearStampTimer() {
      if (stampTimer) {
        clearTimeout(stampTimer);
        stampTimer = null;
      }
    }

    function armStampExpiry(payload) {
      clearStampTimer();
      if (!onStampExpiry || !payload || !payload.stamp_expires_at) return;
      var exp = Date.parse(String(payload.stamp_expires_at).replace(' ', 'T') + 'Z');
      if (isNaN(exp)) {
        // Odoo naive UTC string — treat as UTC
        exp = Date.parse(String(payload.stamp_expires_at).replace(' ', 'T') + '+00:00');
      }
      if (isNaN(exp)) return;
      var wait = exp - Date.now();
      if (wait <= 0) {
        onStampExpiry();
        return;
      }
      // Cap to 2 minutes — sold_display is typically short
      if (wait > 120000) wait = 120000;
      stampTimer = setTimeout(function () {
        stampTimer = null;
        onStampExpiry();
      }, wait + 50);
    }

    function handlePayload(payload) {
      try {
        apply(payload);
        armStampExpiry(payload);
      } catch (e) {
        /* keep stream alive */
      }
    }

    function stampBeat() {
      lastBeat = Date.now();
      staleFired = false;
    }

    function notifyUp() {
      signalUp();
      if (typeof onPing === 'function') {
        try { onPing(); } catch (e) {}
      }
    }

    function markBeat() {
      stampBeat();
      notifyUp();
    }

    function connect() {
      if (closed) return;
      if (es) {
        try { es.close(); } catch (e) {}
        es = null;
      }
      try {
        es = new EventSource(url);
      } catch (e) {
        if (typeof onError === 'function') {
          try { onError(); } catch (err) {}
        }
        startPoll();
        return;
      }

      es.addEventListener('snapshot', function (ev) {
        stampBeat();
        stopPoll();
        try {
          handlePayload(JSON.parse(ev.data));
        } catch (e) {}
        notifyUp();
      });
      es.addEventListener('auction.update', function (ev) {
        stampBeat();
        stopPoll();
        try {
          handlePayload(JSON.parse(ev.data));
        } catch (e) {}
        notifyUp();
      });
      es.addEventListener('ping', function () {
        seenPing = true;
        markBeat();
      });
      es.onopen = function () {
        markBeat();
        stopPoll();
        if (typeof onOpen === 'function') {
          try { onOpen(); } catch (e) {}
        }
      };
      es.onerror = function () {
        // Browser will auto-reconnect; meanwhile resume polling.
        signalDown();
        if (typeof onError === 'function') {
          try { onError(); } catch (e) {}
        }
        startPoll();
      };
    }

    beatTimer = setInterval(function () {
      if (closed) {
        clearInterval(beatTimer);
        beatTimer = null;
        return;
      }
      if (!seenPing) return;
      if (Date.now() - lastBeat <= beatMs) return;
      if (staleFired) return;
      staleFired = true;
      signalDown();
      if (typeof onError === 'function') {
        try { onError(); } catch (e) {}
      }
      startPoll();
      connect();
    }, 1000);

    connect();

    return {
      close: function () {
        closed = true;
        clearStampTimer();
        if (beatTimer) {
          clearInterval(beatTimer);
          beatTimer = null;
        }
        if (es) {
          try { es.close(); } catch (e) {}
          es = null;
        }
        startPoll();
      },
    };
  }

  global.AuctionChampSSE = { bind: bindSse, enabled: sseEnabled };
})(window);
