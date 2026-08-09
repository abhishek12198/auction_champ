/**
 * Squad Poster photo editor (mobile-first)
 * - Adjust photos → pick a player → drag/zoom in a large stage
 * - Full photos lazy-loaded only when editing (fast page load)
 * - No floating Edit overlays on phones (they collide on scaled posters)
 */
(function () {
  'use strict';

  if (window.__spEditorBooted) return;
  window.__spEditorBooted = true;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function isPhone() {
    try {
      return window.matchMedia('(max-width: 820px), (pointer: coarse)').matches;
    } catch (e) {
      return window.innerWidth <= 820;
    }
  }

  function ensureStyle() {
    if ($('#spEditorCss')) return;
    var css = document.createElement('style');
    css.id = 'spEditorCss';
    css.textContent = [
      '#spEditorRoot{width:100%;box-sizing:border-box;padding:8px 12px 10px;background:#0c0c10;border-bottom:1px solid rgba(255,255,255,.12);position:relative;z-index:2147483001;pointer-events:auto!important}',
      '#spEditorRoot *{box-sizing:border-box}',
      '#spEditorRoot .spE-title{font:700 12px/1.35 sans-serif;letter-spacing:.04em;color:rgba(255,230,180,.9);margin:0 0 6px;text-align:center}',
      '#spEditorRoot .spE-pick{display:none;gap:8px;overflow-x:auto;-webkit-overflow-scrolling:touch;padding:6px 2px 10px;scroll-snap-type:x proximity}',
      '#spEditorRoot.is-picking .spE-pick,#spEditorRoot.is-editing .spE-pick{display:flex}',
      '#spEditorRoot .spE-chip{flex:0 0 auto;width:76px;scroll-snap-align:start;appearance:none;border:2px solid rgba(255,255,255,.2);background:#141416;border-radius:12px;padding:6px;color:#fff;cursor:pointer;touch-action:manipulation}',
      '#spEditorRoot .spE-chip img{width:64px;height:64px;object-fit:cover;border-radius:8px;display:block;background:#222}',
      '#spEditorRoot .spE-chip span{display:block;margin-top:4px;font:700 10px/1.15 sans-serif;text-align:center;max-width:64px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
      '#spEditorRoot .spE-chip.is-on{border-color:#ff7a18;box-shadow:0 0 0 1px rgba(255,122,24,.45)}',
      '#spEditorRoot .spE-panel{display:none;margin:8px auto 0;max-width:520px;background:#141416;border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:12px}',
      '#spEditorRoot.is-editing .spE-panel{display:block}',
      '#spEditorRoot .spE-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}',
      '#spEditorRoot .spE-name{margin:0;font:700 15px/1.2 sans-serif;color:#fff;text-transform:uppercase;letter-spacing:.04em}',
      '#spEditorRoot .spE-compare{display:flex;gap:10px;align-items:stretch;justify-content:center;margin-bottom:10px}',
      '#spEditorRoot .spE-thumb{width:72px;flex:0 0 72px;text-align:center}',
      '#spEditorRoot .spE-thumb img{width:72px;height:72px;object-fit:cover;border-radius:8px;border:1px solid rgba(255,255,255,.2);display:block}',
      '#spEditorRoot .spE-thumb span{display:block;margin-top:4px;font:700 10px/1 sans-serif;color:rgba(255,255,255,.55);text-transform:uppercase;letter-spacing:.06em}',
      '#spEditorRoot .spE-stage-wrap{flex:1 1 auto;min-width:0;text-align:center}',
      '#spEditorRoot .spE-stage{position:relative;width:min(280px,100%);aspect-ratio:1/1;margin:0 auto;overflow:hidden;border:2px solid #e8c547;border-radius:10px;background:#0a0604;touch-action:none;cursor:grab;user-select:none}',
      '#spEditorRoot .spE-stage.is-drag{cursor:grabbing}',
      '#spEditorRoot .spE-img{position:absolute;left:0;top:0;max-width:none;max-height:none;width:auto;height:auto;object-fit:fill;pointer-events:none;user-select:none;-webkit-user-drag:none}',
      '#spEditorRoot .spE-frame-lbl{margin:6px 0 0;font:700 11px/1.3 sans-serif;color:#e8c547;text-transform:uppercase;letter-spacing:.08em}',
      '#spEditorRoot .spE-help{margin:8px 0 0;font:600 12px/1.4 sans-serif;color:rgba(255,255,255,.65);text-align:center}',
      '#spEditorRoot .spE-row{display:flex;align-items:center;gap:8px;margin-top:10px}',
      '#spEditorRoot .spE-row input[type=range]{flex:1;min-height:36px}',
      '#spEditorRoot .spE-badge-row{display:none;flex-direction:column;gap:6px;margin-top:12px;padding-top:10px;border-top:1px solid rgba(255,255,255,.1)}',
      '#spEditorRoot.is-icon-edit .spE-badge-row{display:flex}',
      '#spEditorRoot .spE-badge-lbl{font:700 11px/1.2 sans-serif;letter-spacing:.08em;text-transform:uppercase;color:rgba(255,230,180,.85)}',
      '#spEditorRoot .spE-badge-input{width:100%;appearance:none;border:1px solid rgba(255,220,140,.45);background:#0c0c10;color:#ffe7a8;border-radius:10px;padding:12px 14px;font:700 15px/1.2 "Oswald",sans-serif;letter-spacing:.12em;text-transform:uppercase;min-height:48px}',
      '#spEditorRoot .spE-badge-hint{margin:0;font:600 11px/1.3 sans-serif;color:rgba(255,255,255,.5)}',
      '#spEditorRoot .spE-actions{display:flex;justify-content:stretch;gap:8px;margin-top:12px}',
      '#spEditorRoot .spE-actions .spE-btn{flex:1}',
      '#spEditorRoot button.spE-btn{appearance:none;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.08);color:#fff;border-radius:999px;padding:12px 16px;font:700 14px/1 sans-serif;cursor:pointer;min-height:48px;pointer-events:auto!important;touch-action:manipulation}',
      '#spEditorRoot button.spE-btn.primary{background:linear-gradient(135deg,#ff7a18,#c45a10);color:#111;border-color:transparent}',
      '#spEditorRoot .spE-hint{margin:6px 0 0;text-align:center;font:600 12px/1.3 sans-serif;color:#6ee7b7}',
      '#spEditorRoot .spE-loading{display:none;text-align:center;font:600 13px/1.4 sans-serif;color:rgba(255,230,180,.85);padding:8px}',
      '#spEditorRoot.is-loading .spE-loading{display:block}',
      '#spCardHitLayer{position:fixed;inset:0;z-index:2147482500;pointer-events:none}',
      '#spCardHitLayer .spE-hit{position:fixed;pointer-events:auto!important;cursor:pointer;border:none;border-radius:8px;background:transparent;display:flex;align-items:flex-start;justify-content:flex-start;padding:2px;touch-action:manipulation;width:auto!important;height:auto!important;min-width:44px;min-height:32px}',
      '#spCardHitLayer .spE-hit span{background:rgba(0,0,0,.78);color:#ffe7a8;font:800 11px/1 sans-serif;letter-spacing:.06em;text-transform:uppercase;padding:7px 10px;border-radius:6px;border:1px solid rgba(255,220,140,.55);pointer-events:none;box-shadow:0 2px 8px rgba(0,0,0,.45)}',
      '#spCardHitLayer .spE-hit.is-on span{border-color:#ff7a18;box-shadow:0 0 0 1px rgba(255,122,24,.45),0 2px 8px rgba(0,0,0,.45)}',
      '.sp-peditor:not(#spEditorRoot){display:none!important;pointer-events:none!important}',
      '.sp-preview-scale,.sp-canvas{pointer-events:none!important}',
      '.sp-photo-edit-btn,#spPlayerEditBar,.sp-player-edit-bar{display:none!important}',
      '@media (max-width:820px){',
      '  #spEditorRoot{padding:10px 10px 14px;padding-bottom:calc(14px + env(safe-area-inset-bottom,0px))}',
      '  #spEditorRoot .spE-title{font-size:13px;line-height:1.4}',
      '  #spEditorRoot .spE-thumb{display:none}',
      '  #spEditorRoot .spE-compare{display:block}',
      '  #spEditorRoot .spE-stage{width:min(92vw,360px);max-width:100%}',
      '  #spEditorRoot .spE-panel{max-width:none;border-radius:16px;padding:14px 12px 16px}',
      '  #spEditorRoot .spE-actions{flex-direction:column-reverse}',
      '  #spEditorRoot .spE-actions .spE-btn{width:100%;min-height:52px;font-size:16px}',
      '  #spCardHitLayer .spE-hit{min-width:48px;min-height:36px;padding:1px}',
      '  #spCardHitLayer .spE-hit span{font-size:10px;padding:6px 8px}',
      '}'
    ].join('\n');
    document.head.appendChild(css);
  }

  function cardsWithPhotos() {
    var canvas = $('#spCanvas');
    if (!canvas) return [];
    return $all('.sp-card', canvas).filter(function (c) {
      return !!c.querySelector('.sp-card-photo');
    });
  }

  function photoKey(card) {
    return String(card.getAttribute('data-player-id') || card.getAttribute('data-player-name') || '');
  }

  function cropPhotoSrc(card) {
    var img = card.querySelector('.sp-card-photo');
    return card.getAttribute('data-photo-crop')
      || (img && (img.getAttribute('data-orig-crop') || img.getAttribute('src')))
      || '';
  }

  function auctionId() {
    var aid = window.__spAuctionId;
    if (!aid) {
      var m = (location.pathname || '').match(/\/auction\/squad-poster\/(\d+)/);
      aid = m ? m[1] : null;
    }
    return aid;
  }

  function dbName() {
    var db = window.__spDbName || '';
    if (!db) {
      var dm = (location.pathname || '').match(/^\/([^\/]+)\/auction\/squad-poster\//);
      db = dm ? dm[1] : '';
    }
    return db;
  }

  function cropsApiUrl() {
    var aid = auctionId();
    if (!aid) return null;
    var db = dbName();
    if (db) return '/' + db + '/auction/squad-poster/' + aid + '/photo-crops';
    return '/auction/squad-poster/' + aid + '/photo-crops';
  }

  function fullPhotoApiUrl(playerId) {
    var aid = auctionId();
    if (!aid || !playerId) return null;
    var db = dbName();
    if (db) return '/' + db + '/auction/squad-poster/' + aid + '/full-photo/' + playerId;
    return '/auction/squad-poster/' + aid + '/full-photo/' + playerId;
  }

  function jsonRpc(url, params) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        jsonrpc: '2.0',
        method: 'call',
        params: params || {},
        id: Date.now(),
      }),
    }).then(function (r) { return r.json(); }).then(function (data) {
      return (data && data.result) ? data.result : data;
    });
  }

  function loadFullPhoto(card) {
    var id = card.getAttribute('data-player-id');
    var map = window.__spFullPhotos || (window.__spFullPhotos = {});
    if (id && map[String(id)]) {
      return Promise.resolve(map[String(id)]);
    }
    var cached = card.getAttribute('data-photo-full');
    if (cached) {
      if (id) map[String(id)] = cached;
      return Promise.resolve(cached);
    }
    var url = fullPhotoApiUrl(id);
    if (!url) {
      return Promise.resolve(cropPhotoSrc(card));
    }
    return jsonRpc(url, {}).then(function (res) {
      var uri = (res && res.ok && res.uri) ? res.uri : '';
      if (!uri) uri = cropPhotoSrc(card);
      if (id && uri) map[String(id)] = uri;
      return uri;
    }).catch(function () {
      return cropPhotoSrc(card);
    });
  }

  function autoCrop(card) {
    var id = card.getAttribute('data-player-id');
    var autoMap = window.__spAutoCrops || {};
    var map = window.__spPhotoCrops || {};
    var c = (id && autoMap[String(id)]) || (id && map[String(id)]) || null;
    if (c && typeof c.l === 'number') return { l: c.l, t: c.t, sw: c.sw, sh: c.sh };
    return { l: 0, t: 0, sw: 1, sh: 1 };
  }

  function effectiveCrop(card) {
    var id = card.getAttribute('data-player-id');
    var map = window.__spPhotoCrops || {};
    var c = (id && map[String(id)]) || null;
    if (c && typeof c.l === 'number') return { l: c.l, t: c.t, sw: c.sw, sh: c.sh };
    return autoCrop(card);
  }

  function storageKey() {
    return 'spPosterCrops:' + (auctionId() || '0');
  }

  function labelsStorageKey() {
    return 'spPosterIconLabels:' + (auctionId() || '0');
  }

  function readLocalCrops() {
    try {
      var raw = localStorage.getItem(storageKey());
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return (parsed && typeof parsed === 'object') ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  function writeLocalCrops(crops) {
    try {
      localStorage.setItem(storageKey(), JSON.stringify(crops || {}));
    } catch (e) {}
  }

  function readLocalLabels() {
    try {
      var raw = localStorage.getItem(labelsStorageKey());
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return (parsed && typeof parsed === 'object') ? parsed : {};
    } catch (e) {
      return {};
    }
  }

  function writeLocalLabels(labels) {
    try {
      localStorage.setItem(labelsStorageKey(), JSON.stringify(labels || {}));
    } catch (e) {}
  }

  function mergeLocalIntoPhotoCrops() {
    var local = readLocalCrops();
    window.__spPhotoCrops = window.__spPhotoCrops || {};
    Object.keys(local).forEach(function (pid) {
      var c = local[pid];
      if (c && typeof c.l === 'number') {
        window.__spPhotoCrops[pid] = { l: c.l, t: c.t, sw: c.sw, sh: c.sh };
      }
    });
    var localLabels = readLocalLabels();
    window.__spIconLabels = window.__spIconLabels || {};
    Object.keys(localLabels).forEach(function (pid) {
      if (localLabels[pid]) window.__spIconLabels[pid] = String(localLabels[pid]);
    });
  }

  function collectManualCrops() {
    var out = {};
    Object.keys(states).forEach(function (k) {
      var st = states[k];
      if (!st || !st.manual) return;
      if (!/^\d+$/.test(String(k))) return;
      out[String(k)] = { l: st.l, t: st.t, sw: st.sw, sh: st.sh };
    });
    return out;
  }

  function collectIconLabels() {
    var out = {};
    Object.keys(labelStates).forEach(function (k) {
      if (!/^\d+$/.test(String(k))) return;
      var txt = (labelStates[k] || '').trim();
      if (txt) out[String(k)] = txt.slice(0, 28);
    });
    // Also include in-memory map so Done persists even without open
    var map = window.__spIconLabels || {};
    Object.keys(map).forEach(function (k) {
      if (out[k]) return;
      if (!/^\d+$/.test(String(k))) return;
      var txt = String(map[k] || '').trim();
      if (txt) out[k] = txt.slice(0, 28);
    });
    return out;
  }

  function persistCrops(extraClearIds) {
    var crops = collectManualCrops();
    var labels = collectIconLabels();
    writeLocalCrops(crops);
    writeLocalLabels(labels);
    Object.keys(crops).forEach(function (pid) {
      window.__spPhotoCrops = window.__spPhotoCrops || {};
      window.__spPhotoCrops[pid] = crops[pid];
    });
    (extraClearIds || []).forEach(function (pid) {
      if (window.__spPhotoCrops) delete window.__spPhotoCrops[String(pid)];
    });
    Object.keys(labels).forEach(function (pid) {
      window.__spIconLabels = window.__spIconLabels || {};
      window.__spIconLabels[pid] = labels[pid];
    });
    var api = cropsApiUrl();
    if (!api) return Promise.resolve({ ok: false });
    return jsonRpc(api, {
      crops: crops,
      clear_ids: extraClearIds || [],
      icon_labels: labels,
    }).catch(function () {
      return { ok: false };
    });
  }

  var states = {};
  var labelStates = {};
  var active = null;
  var draft = { l: 0, t: 0, sw: 1, sh: 1 };
  var drag = null;
  var hitMap = {};
  var chipMap = {};
  var nat = { w: 1, h: 1 };
  var hitsEnabled = true;
  var syncTimer = null;
  var DEFAULT_ICON_BADGE = 'ICON PLAYER';

  function isIconCard(card) {
    return !!(card && (card.classList.contains('is-icon') || card.querySelector('.sp-card-icon-badge')));
  }

  function getBadgeText(card) {
    var id = card && card.getAttribute('data-player-id');
    if (id && labelStates[String(id)]) return labelStates[String(id)];
    if (id && window.__spIconLabels && window.__spIconLabels[String(id)]) {
      return window.__spIconLabels[String(id)];
    }
    var fromAttr = card && card.getAttribute('data-icon-badge');
    if (fromAttr) return fromAttr;
    var el = card && card.querySelector('.sp-card-icon-badge-txt');
    return (el && el.textContent) || DEFAULT_ICON_BADGE;
  }

  function applyBadgeToCard(card, text) {
    if (!card || !isIconCard(card)) return;
    var txt = (text || '').trim() || DEFAULT_ICON_BADGE;
    txt = txt.slice(0, 28).toUpperCase();
    var el = card.querySelector('.sp-card-icon-badge-txt');
    if (el) el.textContent = txt;
    card.setAttribute('data-icon-badge', txt);
    var id = card.getAttribute('data-player-id');
    if (id) {
      labelStates[String(id)] = txt;
      window.__spIconLabels = window.__spIconLabels || {};
      window.__spIconLabels[String(id)] = txt;
    }
  }

  function getState(card) {
    var k = photoKey(card);
    if (!states[k]) {
      var c = effectiveCrop(card);
      states[k] = { l: c.l, t: c.t, sw: c.sw, sh: c.sh, manual: false };
      var id = card.getAttribute('data-player-id');
      var local = readLocalCrops();
      if (id && local[String(id)]) states[k].manual = true;
      else if (id && window.__spPhotoCrops && window.__spAutoCrops) {
        var saved = window.__spPhotoCrops[String(id)];
        var auto = window.__spAutoCrops[String(id)];
        if (saved && auto && (
          Math.abs(saved.l - auto.l) > 0.001 ||
          Math.abs(saved.t - auto.t) > 0.001 ||
          Math.abs(saved.sw - auto.sw) > 0.001
        )) {
          states[k].manual = true;
        }
      }
    }
    return states[k];
  }

  function clampDraft(d) {
    d.sw = Math.max(0.12, Math.min(1, d.sw || 1));
    var sideW = d.sw * nat.w;
    d.sh = sideW / Math.max(1, nat.h);
    if (d.sh > 1) {
      d.sh = 1;
      d.sw = nat.h / Math.max(1, nat.w);
    }
    d.l = Math.max(0, Math.min(1 - d.sw, d.l || 0));
    d.t = Math.max(0, Math.min(1 - d.sh, d.t || 0));
    return d;
  }

  function layoutImg(imgEl, stageEl, d) {
    if (!imgEl || !stageEl || !nat.w) return;
    d = clampDraft(d);
    var stageS = stageEl.clientWidth || 280;
    var sidePx = d.sw * nat.w;
    if (sidePx < 1) sidePx = 1;
    var scale = stageS / sidePx;
    imgEl.style.width = (nat.w * scale) + 'px';
    imgEl.style.height = (nat.h * scale) + 'px';
    imgEl.style.left = (-d.l * nat.w * scale) + 'px';
    imgEl.style.top = (-d.t * nat.h * scale) + 'px';
    imgEl.style.transform = 'none';
  }

  function applyToCard(card, d, fullSrc) {
    var img = card.querySelector('.sp-card-photo');
    var wrap = card.querySelector('.sp-card-photo-wrap') || (img && img.parentElement);
    if (!img || !wrap) return;
    var full = fullSrc || (window.__spFullPhotos && window.__spFullPhotos[photoKey(card)]) || '';
    if (full) {
      if (!img.getAttribute('data-orig-crop')) {
        img.setAttribute('data-orig-crop', cropPhotoSrc(card) || img.src);
      }
      if (img.getAttribute('src') !== full) img.src = full;
    }
    function paint() {
      var nw = img.naturalWidth || nat.w;
      var nh = img.naturalHeight || nat.h;
      if (!nw || !nh) return;
      var dd = { l: d.l, t: d.t, sw: d.sw, sh: d.sh };
      var sideW = dd.sw * nw;
      dd.sh = sideW / nh;
      if (dd.sh > 1) {
        dd.sh = 1;
        dd.sw = nh / nw;
      }
      dd.l = Math.max(0, Math.min(1 - dd.sw, dd.l));
      dd.t = Math.max(0, Math.min(1 - dd.sh, dd.t));

      var stageS = wrap.clientWidth || 160;
      var sidePx = dd.sw * nw;
      var scale = stageS / Math.max(1, sidePx);
      img.style.position = 'absolute';
      img.style.maxWidth = 'none';
      img.style.maxHeight = 'none';
      img.style.objectFit = 'fill';
      img.style.width = (nw * scale) + 'px';
      img.style.height = (nh * scale) + 'px';
      img.style.left = (-dd.l * nw * scale) + 'px';
      img.style.top = (-dd.t * nh * scale) + 'px';
      img.style.right = 'auto';
      img.style.bottom = 'auto';
      img.style.transform = 'none';
    }
    if (img.complete && img.naturalWidth) paint();
    else img.onload = paint;
  }

  function zoomPct(d) {
    return Math.round(100 / Math.max(0.12, d.sw));
  }

  function setZoomFromPct(pct) {
    var z = Math.max(100, Math.min(500, pct || 100)) / 100;
    var cx = draft.l + draft.sw * 0.5;
    var cy = draft.t + draft.sh * 0.5;
    draft.sw = 1 / z;
    draft.sh = (draft.sw * nat.w) / Math.max(1, nat.h);
    draft.l = cx - draft.sw * 0.5;
    draft.t = cy - draft.sh * 0.5;
    clampDraft(draft);
  }

  function syncHits(list) {
    if (!hitsEnabled) return;
    var layer = $('#spCardHitLayer');
    if (!layer) return;
    list.forEach(function (card) {
      var k = photoKey(card);
      var hit = hitMap[k];
      if (!hit) return;
      var r = card.getBoundingClientRect();
      if (r.width < 8 || r.height < 8 || r.bottom < 0 || r.top > window.innerHeight) {
        hit.style.display = 'none';
        return;
      }
      // Compact Edit chip at card top-left (avoids full-card overlays colliding on mobile zoom)
      hit.style.display = 'flex';
      hit.style.left = Math.round(r.left + 2) + 'px';
      hit.style.top = Math.round(r.top + 2) + 'px';
    });
  }

  function boot() {
    ensureStyle();
    mergeLocalIntoPhotoCrops();
    $all('.sp-peditor').forEach(function (n) {
      if (n.id === 'spEditorRoot') return;
      n.style.setProperty('display', 'none', 'important');
      n.style.setProperty('pointer-events', 'none', 'important');
    });

    var list = cardsWithPhotos();
    if (!list.length) return;

    var mount = $('#spToolbar') || document.body;
    var root = $('#spEditorRoot');
    if (!root) {
      root = document.createElement('div');
      root.id = 'spEditorRoot';
      if (mount.id === 'spToolbar') mount.insertBefore(root, mount.firstChild);
      else document.body.insertBefore(root, document.body.firstChild);
    }

    root.innerHTML =
      '<div class="spE-title" id="spETitle">Tap <b>Adjust photos</b>, then pick a player</div>' +
      '<div class="spE-pick" id="spEPick"></div>' +
      '<div class="spE-loading" id="spELoading">Loading photo…</div>' +
      '<div class="spE-panel" id="spEPanel">' +
        '<div class="spE-head">' +
          '<h3 class="spE-name" id="spEName">Player</h3>' +
          '<button type="button" class="spE-btn" id="spEClose">Close</button>' +
        '</div>' +
        '<div class="spE-compare">' +
          '<div class="spE-thumb"><img id="spEBefore" alt=""/><span>On card now</span></div>' +
          '<div class="spE-stage-wrap">' +
            '<div class="spE-stage" id="spEStage"><img class="spE-img" id="spEImg" alt=""/></div>' +
            '<div class="spE-frame-lbl">Drag photo inside the yellow frame</div>' +
          '</div>' +
        '</div>' +
        '<p class="spE-help">Pinch / zoom slider for tighter or wider crop</p>' +
        '<div class="spE-row">' +
          '<button type="button" class="spE-btn" id="spEMinus">−</button>' +
          '<input type="range" id="spERange" min="100" max="400" value="100" step="2"/>' +
          '<button type="button" class="spE-btn" id="spEPlus">+</button>' +
          '<span id="spEZoomLbl">100%</span>' +
        '</div>' +
        '<div class="spE-badge-row" id="spEBadgeRow">' +
          '<label class="spE-badge-lbl" for="spEBadge">ICON capsule text</label>' +
          '<input type="text" class="spE-badge-input" id="spEBadge" maxlength="28" placeholder="ICON PLAYER" autocomplete="off" autocapitalize="characters"/>' +
          '<p class="spE-badge-hint">Shown on the gold capsule (e.g. ICON PLAYER, CAPTAIN, MVP)</p>' +
        '</div>' +
        '<div class="spE-actions">' +
          '<button type="button" class="spE-btn" id="spEReset">Reset</button>' +
          '<button type="button" class="spE-btn primary" id="spEDone">Done</button>' +
        '</div>' +
      '</div>' +
      '<p class="spE-hint" id="spEHint">Use Adjust photos to reframe player faces</p>';

    var pickEl = $('#spEPick', root);
    var stage = $('#spEStage', root);
    var imgEl = $('#spEImg', root);
    var beforeEl = $('#spEBefore', root);
    var rangeEl = $('#spERange', root);
    var zoomLbl = $('#spEZoomLbl', root);
    var nameEl = $('#spEName', root);
    var hint = $('#spEHint', root);
    var titleEl = $('#spETitle', root);
    var badgeInput = $('#spEBadge', root);

    list.forEach(function (card) {
      var k = photoKey(card) || ('i' + Math.random());
      getState(card);
      if (isIconCard(card)) applyBadgeToCard(card, getBadgeText(card));
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'spE-chip';
      var thumb = cropPhotoSrc(card);
      var nm = card.getAttribute('data-player-name') || 'Player';
      chip.innerHTML = '<img alt=""/><span></span>';
      chip.querySelector('img').src = thumb;
      chip.querySelector('span').textContent = nm;
      chip.addEventListener('click', function (ev) {
        ev.preventDefault();
        open(card);
      });
      pickEl.appendChild(chip);
      chipMap[k] = chip;
    });

    function setPicking(on) {
      root.classList.toggle('is-picking', !!on);
      if (on) {
        titleEl.innerHTML = 'Pick a player below, then drag to reframe';
        hint.textContent = 'Scroll the row to find a player';
        try { root.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (e) {}
      } else if (!root.classList.contains('is-editing')) {
        titleEl.innerHTML = 'Tap <b>Adjust photos</b>, then pick a player';
        hint.textContent = 'Use Adjust photos to reframe player faces';
      }
    }

    function setHits(on) {
      hitsEnabled = on !== false;
      var layer = $('#spCardHitLayer');
      if (!layer) return;
      layer.style.display = hitsEnabled ? '' : 'none';
      if (hitsEnabled) syncHits(list);
    }

    function refreshChrome() {
      layoutImg(imgEl, stage, draft);
      var zp = zoomPct(draft);
      if (rangeEl) rangeEl.value = String(zp);
      if (zoomLbl) zoomLbl.textContent = zp + '%';
    }

    function highlightChip(card) {
      var key = photoKey(card);
      Object.keys(chipMap).forEach(function (k) {
        chipMap[k].classList.toggle('is-on', k === key);
      });
      Object.keys(hitMap).forEach(function (k) {
        hitMap[k].classList.toggle('is-on', hitMap[k].__spCard === card);
      });
    }

    function open(card) {
      active = card;
      var st = getState(card);
      draft = { l: st.l, t: st.t, sw: st.sw, sh: st.sh };
      nameEl.textContent = card.getAttribute('data-player-name') || 'Player';
      beforeEl.src = cropPhotoSrc(card);
      highlightChip(card);
      var iconEdit = isIconCard(card);
      root.classList.toggle('is-icon-edit', iconEdit);
      if (badgeInput) {
        badgeInput.value = getBadgeText(card);
        if (iconEdit) {
          // Live preview while typing
          badgeInput.oninput = function () {
            if (!active) return;
            applyBadgeToCard(active, badgeInput.value);
          };
        } else {
          badgeInput.oninput = null;
        }
      }
      root.classList.add('is-picking', 'is-loading');
      root.classList.remove('is-editing');
      hint.textContent = 'Loading full photo…';
      loadFullPhoto(card).then(function (full) {
        if (active !== card) return;
        imgEl.onload = function () {
          nat.w = imgEl.naturalWidth || 1;
          nat.h = imgEl.naturalHeight || 1;
          clampDraft(draft);
          refreshChrome();
          root.classList.remove('is-loading');
          root.classList.add('is-editing');
          hint.textContent = iconEdit
            ? 'Drag photo · edit ICON capsule text below'
            : 'Drag to move · zoom for tighter/wider crop';
        };
        imgEl.src = full || cropPhotoSrc(card);
        if (imgEl.complete && imgEl.naturalWidth) {
          nat.w = imgEl.naturalWidth;
          nat.h = imgEl.naturalHeight;
          clampDraft(draft);
          refreshChrome();
          root.classList.remove('is-loading');
          root.classList.add('is-editing');
          hint.textContent = iconEdit
            ? 'Drag photo · edit ICON capsule text below'
            : 'Drag to move · zoom for tighter/wider crop';
        }
      });
      try { root.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (e) {}
    }

    function close(save) {
      if (save && active) {
        var st = getState(active);
        st.l = draft.l; st.t = draft.t; st.sw = draft.sw; st.sh = draft.sh;
        st.manual = true;
        var full = (window.__spFullPhotos && window.__spFullPhotos[photoKey(active)]) || '';
        applyToCard(active, draft, full);
        if (isIconCard(active) && badgeInput) {
          applyBadgeToCard(active, badgeInput.value);
        }
        hint.textContent = 'Saved · will restore next time you open this poster';
        persistCrops([]);
      }
      active = null;
      drag = null;
      root.classList.remove('is-editing', 'is-loading', 'is-icon-edit');
      if (badgeInput) badgeInput.oninput = null;
      Object.keys(hitMap).forEach(function (k) { hitMap[k].classList.remove('is-on'); });
      Object.keys(chipMap).forEach(function (k) { chipMap[k].classList.remove('is-on'); });
      if (root.classList.contains('is-picking')) {
        hint.textContent = 'Pick another player, or tap Adjust photos again to finish';
      }
    }

    // Always show compact Edit chips on every card (desktop + mobile)
    var layer = $('#spCardHitLayer');
    if (!layer) {
      layer = document.createElement('div');
      layer.id = 'spCardHitLayer';
      document.body.appendChild(layer);
    }
    layer.innerHTML = '';
    hitMap = {};
    list.forEach(function (card) {
      var k = photoKey(card) || ('i' + Math.random());
      var hit = document.createElement('button');
      hit.type = 'button';
      hit.className = 'spE-hit';
      hit.innerHTML = '<span>Edit</span>';
      hit.__spCard = card;
      hit.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        setPicking(true);
        open(card);
        var editBtn = $('#spEditPhotos');
        if (editBtn) editBtn.textContent = 'Done adjusting';
      });
      layer.appendChild(hit);
      hitMap[k] = hit;
    });
    setHits(true);
    syncHits(list);

    window.addEventListener('scroll', function () { syncHits(list); }, true);
    window.addEventListener('resize', function () { syncHits(list); });
    var preview = $('.sp-preview-wrap');
    if (preview) preview.addEventListener('scroll', function () { syncHits(list); });
    var zoomSel = $('#spZoom');
    if (zoomSel) zoomSel.addEventListener('change', function () {
      setTimeout(function () { syncHits(list); }, 80);
    });
    if (syncTimer) clearInterval(syncTimer);
    syncTimer = setInterval(function () {
      if (hitsEnabled) syncHits(list);
    }, 1200);

    var editBtn = $('#spEditPhotos');
    if (editBtn) {
      editBtn.addEventListener('click', function (e) {
        e.preventDefault();
        var next = !root.classList.contains('is-picking') && !root.classList.contains('is-editing');
        if (next) {
          setPicking(true);
          setHits(true);
          editBtn.textContent = 'Done adjusting';
        } else {
          close(false);
          setPicking(false);
          setHits(true); // keep Edit chips visible
          editBtn.textContent = 'Adjust photos';
          root.classList.remove('is-picking', 'is-editing', 'is-loading', 'is-icon-edit');
        }
      });
    }

    $('#spEDone', root).addEventListener('click', function (e) { e.preventDefault(); close(true); });
    $('#spEClose', root).addEventListener('click', function (e) { e.preventDefault(); close(false); });
    $('#spEReset', root).addEventListener('click', function (e) {
      e.preventDefault();
      if (!active) return;
      var c = autoCrop(active);
      draft = { l: c.l, t: c.t, sw: c.sw, sh: c.sh };
      clampDraft(draft);
      refreshChrome();
      var st = getState(active);
      st.l = draft.l; st.t = draft.t; st.sw = draft.sw; st.sh = draft.sh;
      st.manual = false;
      var full = (window.__spFullPhotos && window.__spFullPhotos[photoKey(active)]) || '';
      applyToCard(active, draft, full);
      if (isIconCard(active)) {
        applyBadgeToCard(active, DEFAULT_ICON_BADGE);
        if (badgeInput) badgeInput.value = DEFAULT_ICON_BADGE;
      }
      var pid = active.getAttribute('data-player-id');
      if (pid) persistCrops([String(pid)]);
    });
    function bumpZoom(delta) {
      setZoomFromPct(zoomPct(draft) + delta);
      refreshChrome();
    }
    $('#spEMinus', root).addEventListener('click', function (e) { e.preventDefault(); bumpZoom(-10); });
    $('#spEPlus', root).addEventListener('click', function (e) { e.preventDefault(); bumpZoom(10); });
    rangeEl.addEventListener('input', function () {
      setZoomFromPct(parseInt(rangeEl.value, 10) || 100);
      refreshChrome();
    });

    function onDown(ev) {
      if (!root.classList.contains('is-editing')) return;
      var pt = ev.touches ? ev.touches[0] : ev;
      drag = {
        x0: pt.clientX, y0: pt.clientY,
        l0: draft.l, t0: draft.t,
        stage: stage.clientWidth || 280
      };
      stage.classList.add('is-drag');
      if (ev.pointerId != null) {
        try { stage.setPointerCapture(ev.pointerId); } catch (err) {}
      }
      ev.preventDefault();
    }
    function onMove(ev) {
      if (!drag) return;
      var pt = ev.touches ? ev.touches[0] : ev;
      var sidePx = draft.sw * nat.w;
      var scale = drag.stage / Math.max(1, sidePx);
      draft.l = drag.l0 - (pt.clientX - drag.x0) / (nat.w * scale);
      draft.t = drag.t0 - (pt.clientY - drag.y0) / (nat.h * scale);
      clampDraft(draft);
      refreshChrome();
      ev.preventDefault();
    }
    function onUp() {
      drag = null;
      stage.classList.remove('is-drag');
    }

    stage.addEventListener('pointerdown', onDown);
    stage.addEventListener('pointermove', onMove);
    stage.addEventListener('pointerup', onUp);
    stage.addEventListener('pointercancel', onUp);
    stage.addEventListener('touchstart', onDown, { passive: false });
    stage.addEventListener('touchmove', onMove, { passive: false });
    stage.addEventListener('touchend', onUp);
    stage.addEventListener('wheel', function (ev) {
      ev.preventDefault();
      bumpZoom(ev.deltaY > 0 ? -8 : 8);
    }, { passive: false });

    window.__spClosePhotoEditor = function () { close(false); };
    window.__spPersistPhotoCrops = function () { return persistCrops([]); };

    var status = $('#spStatus');
    if (status) {
      status.textContent = 'Tap Edit on a photo — or use Adjust photos';
      status.className = 'sp-status is-ok';
    }

    var hintBar = $('.sp-hint');
    if (hintBar) {
      hintBar.textContent = '1) Tap Edit on a player · 2) Drag / zoom · 3) Done · 4) Save PNG/JPG';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
  setTimeout(function () {
    if (!$('#spEditorRoot')) boot();
  }, 400);
})();
