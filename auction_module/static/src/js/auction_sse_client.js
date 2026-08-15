/* AuctionChamp Phase 3 — SSE primary with polling fallback.
 * Pages define:
 *   window.__acApplyLiveBoard(data)
 *   window.__acApplyProjector(result)
 *   window.__acApplyBalance(payload)
 * and optional start/stop poll functions.
 */
(function (global) {
  'use strict';

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
    var stampTimer = null;

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

    function connect() {
      if (closed) return;
      try {
        es = new EventSource(url);
      } catch (e) {
        startPoll();
        return;
      }

      es.addEventListener('snapshot', function (ev) {
        stopPoll();
        try {
          handlePayload(JSON.parse(ev.data));
        } catch (e) {}
      });
      es.addEventListener('auction.update', function (ev) {
        stopPoll();
        try {
          handlePayload(JSON.parse(ev.data));
        } catch (e) {}
      });
      es.onopen = function () {
        stopPoll();
      };
      es.onerror = function () {
        // Browser will auto-reconnect; meanwhile resume polling.
        startPoll();
      };
    }

    connect();

    return {
      close: function () {
        closed = true;
        clearStampTimer();
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
