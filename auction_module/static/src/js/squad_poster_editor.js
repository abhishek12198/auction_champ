/**
 * Squad Poster photo editor
 * - Opens ALREADY FRAMED like the card (same auto-crop)
 * - Full DB photo underneath — drag/zoom to reframe
 * - Yellow square = exactly what appears on the poster card
 */
(function () {
  'use strict';

  if (window.__spEditorBooted) return;
  window.__spEditorBooted = true;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function ensureStyle() {
    if ($('#spEditorCss')) return;
    var css = document.createElement('style');
    css.id = 'spEditorCss';
    css.textContent = [
      '#spEditorRoot{width:100%;box-sizing:border-box;padding:8px 12px 10px;background:#0c0c10;border-bottom:1px solid rgba(255,255,255,.12);position:relative;z-index:2147483001;pointer-events:auto!important}',
      '#spEditorRoot *{box-sizing:border-box}',
      '#spEditorRoot .spE-title{font:700 12px/1.35 sans-serif;letter-spacing:.04em;color:rgba(255,230,180,.9);margin:0 0 6px;text-align:center}',
      '#spEditorRoot .spE-panel{display:none;margin:8px auto 0;max-width:440px;background:#141416;border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:12px}',
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
      '#spEditorRoot .spE-row input[type=range]{flex:1}',
      '#spEditorRoot .spE-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:10px}',
      '#spEditorRoot button.spE-btn{appearance:none;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.08);color:#fff;border-radius:999px;padding:10px 16px;font:700 13px/1 sans-serif;cursor:pointer;min-height:40px;pointer-events:auto!important}',
      '#spEditorRoot button.spE-btn.primary{background:linear-gradient(135deg,#ff7a18,#c45a10);color:#111;border-color:transparent}',
      '#spEditorRoot .spE-hint{margin:6px 0 0;text-align:center;font:600 12px/1.3 sans-serif;color:#6ee7b7}',
      '#spCardHitLayer{position:fixed;inset:0;z-index:2147482500;pointer-events:none}',
      '#spCardHitLayer .spE-hit{position:fixed;pointer-events:auto!important;cursor:pointer;border:none;border-radius:8px;background:transparent;display:flex;align-items:flex-start;justify-content:flex-start;padding:6px;touch-action:manipulation}',
      '#spCardHitLayer .spE-hit span{background:rgba(0,0,0,.72);color:#ffe7a8;font:800 11px/1 sans-serif;letter-spacing:.06em;text-transform:uppercase;padding:6px 8px;border-radius:6px;border:1px solid rgba(255,220,140,.5);pointer-events:none}',
      '#spCardHitLayer .spE-hit.is-on span{border-color:#ff7a18;box-shadow:0 0 0 1px rgba(255,122,24,.45)}',
      '.sp-peditor:not(#spEditorRoot){display:none!important;pointer-events:none!important}',
      '.sp-preview-scale,.sp-canvas{pointer-events:none!important}',
      '.sp-photo-edit-btn,#spPlayerEditBar,.sp-player-edit-bar{display:none!important}'
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

  function fullPhotoSrc(card) {
    var id = card.getAttribute('data-player-id');
    var map = window.__spFullPhotos || {};
    if (id && map[String(id)]) return map[String(id)];
    return card.getAttribute('data-photo-full') || '';
  }

  function cropPhotoSrc(card) {
    var img = card.querySelector('.sp-card-photo');
    return card.getAttribute('data-photo-crop')
      || (img && (img.getAttribute('data-orig-crop') || img.getAttribute('src')))
      || '';
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
    var aid = window.__spAuctionId || '';
    if (!aid) {
      var m = (location.pathname || '').match(/\/auction\/squad-poster\/(\d+)/);
      aid = m ? m[1] : '0';
    }
    return 'spPosterCrops:' + aid;
  }

  function cropsApiUrl() {
    var aid = window.__spAuctionId;
    if (!aid) {
      var m = (location.pathname || '').match(/\/auction\/squad-poster\/(\d+)/);
      aid = m ? m[1] : null;
    }
    if (!aid) return null;
    var db = window.__spDbName || '';
    if (!db) {
      var dm = (location.pathname || '').match(/^\/([^\/]+)\/auction\/squad-poster\//);
      db = dm ? dm[1] : '';
    }
    if (db) return '/' + db + '/auction/squad-poster/' + aid + '/photo-crops';
    return '/auction/squad-poster/' + aid + '/photo-crops';
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

  function mergeLocalIntoPhotoCrops() {
    var local = readLocalCrops();
    window.__spPhotoCrops = window.__spPhotoCrops || {};
    Object.keys(local).forEach(function (pid) {
      var c = local[pid];
      if (c && typeof c.l === 'number') {
        window.__spPhotoCrops[pid] = { l: c.l, t: c.t, sw: c.sw, sh: c.sh };
      }
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

  function persistCrops(extraClearIds) {
    var crops = collectManualCrops();
    writeLocalCrops(crops);
    Object.keys(crops).forEach(function (pid) {
      window.__spPhotoCrops = window.__spPhotoCrops || {};
      window.__spPhotoCrops[pid] = crops[pid];
    });
    (extraClearIds || []).forEach(function (pid) {
      if (window.__spPhotoCrops) delete window.__spPhotoCrops[String(pid)];
    });
    var api = cropsApiUrl();
    if (!api) return Promise.resolve({ ok: false });
    var payload = {
      jsonrpc: '2.0',
      method: 'call',
      params: {
        crops: crops,
        clear_ids: extraClearIds || [],
      },
      id: Date.now(),
    };
    return fetch(api, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    }).then(function (r) { return r.json(); }).catch(function () {
      return { ok: false };
    });
  }

  /** draft = { l, t, sw, sh } normalized crop window on the full image */
  var states = {};
  var active = null;
  var draft = { l: 0, t: 0, sw: 1, sh: 1 };
  var drag = null;
  var hitMap = {};
  var nat = { w: 1, h: 1 };

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
    d.sh = d.sw * (nat.w / Math.max(1, nat.h)); // keep square in image pixels
    // Re-express sh based on equal pixel side
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

  function applyToCard(card, d) {
    var img = card.querySelector('.sp-card-photo');
    var wrap = card.querySelector('.sp-card-photo-wrap') || (img && img.parentElement);
    if (!img || !wrap) return;
    var full = fullPhotoSrc(card);
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
      var dd = {
        l: d.l, t: d.t, sw: d.sw, sh: d.sh
      };
      // same clamp with this image's nat
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
    // 100% = full image width in frame; higher = tighter crop
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
    var layer = $('#spCardHitLayer');
    if (!layer) return;
    list.forEach(function (card) {
      var k = photoKey(card);
      var hit = hitMap[k];
      if (!hit) return;
      var r = card.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) {
        hit.style.display = 'none';
        return;
      }
      hit.style.display = 'flex';
      hit.style.left = Math.round(r.left) + 'px';
      hit.style.top = Math.round(r.top) + 'px';
      hit.style.width = Math.round(r.width) + 'px';
      hit.style.height = Math.round(r.height) + 'px';
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
      '<div class="spE-title">Tap Edit on a photo — starts matching the card, then drag to reframe</div>' +
      '<div class="spE-panel" id="spEPanel">' +
        '<div class="spE-head">' +
          '<h3 class="spE-name" id="spEName">Player</h3>' +
          '<button type="button" class="spE-btn" id="spEClose">Close</button>' +
        '</div>' +
        '<div class="spE-compare">' +
          '<div class="spE-thumb"><img id="spEBefore" alt=""/><span>On card now</span></div>' +
          '<div class="spE-stage-wrap">' +
            '<div class="spE-stage" id="spEStage"><img class="spE-img" id="spEImg" alt=""/></div>' +
            '<div class="spE-frame-lbl">Card preview (drag photo)</div>' +
          '</div>' +
        '</div>' +
        '<p class="spE-help">Yellow frame = poster crop. Pinch/zoom or slider to go tighter or wider.</p>' +
        '<div class="spE-row">' +
          '<button type="button" class="spE-btn" id="spEMinus">-</button>' +
          '<input type="range" id="spERange" min="100" max="400" value="100" step="2"/>' +
          '<button type="button" class="spE-btn" id="spEPlus">+</button>' +
          '<span id="spEZoomLbl">100%</span>' +
        '</div>' +
        '<div class="spE-actions">' +
          '<button type="button" class="spE-btn" id="spEReset">Reset auto</button>' +
          '<button type="button" class="spE-btn primary" id="spEDone">Done</button>' +
        '</div>' +
      '</div>' +
      '<p class="spE-hint" id="spEHint">Tap Edit on a player photo</p>';

    var stage = $('#spEStage', root);
    var imgEl = $('#spEImg', root);
    var beforeEl = $('#spEBefore', root);
    var rangeEl = $('#spERange', root);
    var zoomLbl = $('#spEZoomLbl', root);
    var nameEl = $('#spEName', root);
    var hint = $('#spEHint', root);

    function refreshChrome() {
      layoutImg(imgEl, stage, draft);
      var zp = zoomPct(draft);
      if (rangeEl) rangeEl.value = String(zp);
      if (zoomLbl) zoomLbl.textContent = zp + '%';
    }

    function open(card) {
      active = card;
      var st = getState(card);
      draft = { l: st.l, t: st.t, sw: st.sw, sh: st.sh };
      nameEl.textContent = card.getAttribute('data-player-name') || 'Player';
      beforeEl.src = cropPhotoSrc(card);
      var full = fullPhotoSrc(card) || cropPhotoSrc(card);
      imgEl.onload = function () {
        nat.w = imgEl.naturalWidth || 1;
        nat.h = imgEl.naturalHeight || 1;
        clampDraft(draft);
        refreshChrome();
      };
      imgEl.src = full;
      if (imgEl.complete && imgEl.naturalWidth) {
        nat.w = imgEl.naturalWidth;
        nat.h = imgEl.naturalHeight;
        clampDraft(draft);
        refreshChrome();
      }
      Object.keys(hitMap).forEach(function (k) {
        hitMap[k].classList.toggle('is-on', hitMap[k].__spCard === card);
      });
      root.classList.add('is-editing');
      hint.textContent = 'Starts like the card · drag to move · zoom for tighter/wider crop';
      try { root.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); } catch (e) {}
    }

    function close(save) {
      if (save && active) {
        var st = getState(active);
        st.l = draft.l; st.t = draft.t; st.sw = draft.sw; st.sh = draft.sh;
        st.manual = true;
        applyToCard(active, draft);
        hint.textContent = 'Saved framing · will restore next time you open this poster';
        persistCrops([]);
      }
      active = null;
      drag = null;
      root.classList.remove('is-editing');
      Object.keys(hitMap).forEach(function (k) { hitMap[k].classList.remove('is-on'); });
    }

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
        open(card);
      });
      layer.appendChild(hit);
      hitMap[k] = hit;
      // Re-apply saved framing on load (server + localStorage)
      var st = getState(card);
      if (st.manual) {
        applyToCard(card, st);
      }
    });
    syncHits(list);
    window.addEventListener('scroll', function () { syncHits(list); }, true);
    window.addEventListener('resize', function () { syncHits(list); });
    var preview = $('.sp-preview-wrap');
    if (preview) preview.addEventListener('scroll', function () { syncHits(list); });
    var zoomSel = $('#spZoom');
    if (zoomSel) zoomSel.addEventListener('change', function () {
      setTimeout(function () { syncHits(list); }, 80);
    });
    setInterval(function () { syncHits(list); }, 800);

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
      applyToCard(active, draft);
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
      // Moving image under window: drag right → crop moves left
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
      status.textContent = 'Tap Edit on a photo — framing is saved for next time';
      status.className = 'sp-status is-ok';
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
  setTimeout(function () {
    if (!$('#spCardHitLayer') || !$all('#spCardHitLayer .spE-hit').length) boot();
  }, 500);
})();
