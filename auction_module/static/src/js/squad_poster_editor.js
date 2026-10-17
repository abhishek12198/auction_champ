/**
 * Squad Poster photo editor
 * Poster room: tap a player card
 * Photo room: large crop stage + docked zoom / Reset / Done
 */
(function () {
  'use strict';

  if (window.__spEditorBooted) return;
  window.__spEditorBooted = true;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function ensureStyle() {
    var old = $('#spEditorRoot');
    if (old && old.parentNode) old.parentNode.removeChild(old);
    var hits = $('#spCardHitLayer');
    if (hits && hits.parentNode) hits.parentNode.removeChild(hits);
    $all('.sp-peditor').forEach(function (n) {
      n.style.setProperty('display', 'none', 'important');
      n.style.setProperty('pointer-events', 'none', 'important');
    });
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
    if (String(playerId) === 'owner') {
      if (db) return '/' + db + '/auction/squad-poster/' + aid + '/owner-full-photo';
      return '/auction/squad-poster/' + aid + '/owner-full-photo';
    }
    if (db) return '/' + db + '/auction/squad-poster/' + aid + '/full-photo/' + playerId;
    return '/auction/squad-poster/' + aid + '/full-photo/' + playerId;
  }

  function fullPhotoImgUrl(playerId) {
    var aid = auctionId();
    if (!aid || !playerId) return null;
    var db = dbName();
    var path;
    if (String(playerId) === 'owner') {
      path = '/auction/squad-poster/' + aid + '/owner-full-photo-img';
    } else {
      path = '/auction/squad-poster/' + aid + '/full-photo-img/' + playerId;
    }
    if (db) path = '/' + db + path;
    return path;
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
    var imgUrl = fullPhotoImgUrl(id);
    if (imgUrl) {
      if (id) map[String(id)] = imgUrl;
      return Promise.resolve(imgUrl);
    }
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

  function collectOwnerCrop() {
    var st = states.owner;
    if (!st || !st.manual) return null;
    return { l: st.l, t: st.t, sw: st.sw, sh: st.sh };
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
    var ownerCrop = collectOwnerCrop();
    var clearOwner = (extraClearIds || []).indexOf('owner') !== -1;
    var labels = collectIconLabels();
    var localCrops = {};
    Object.keys(crops).forEach(function (pid) { localCrops[pid] = crops[pid]; });
    if (ownerCrop) localCrops.owner = ownerCrop;
    writeLocalCrops(localCrops);
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
    if (ownerCrop) {
      window.__spPhotoCrops = window.__spPhotoCrops || {};
      window.__spPhotoCrops.owner = ownerCrop;
    }
    if (clearOwner && window.__spPhotoCrops) delete window.__spPhotoCrops.owner;
    return jsonRpc(api, {
      crops: crops,
      clear_ids: extraClearIds || [],
      icon_labels: labels,
      owner_crop: ownerCrop,
      clear_owner: clearOwner,
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

  function frameAspect(el, fallback) {
    if (!el) return fallback || 0.75;
    var w = el.clientWidth || 0;
    var h = el.clientHeight || 0;
    if (w < 2 || h < 2) return fallback || 0.75;
    return w / h;
  }

  function clampDraft(d, aspect) {
    aspect = aspect || frameAspect(document.getElementById('spPhotoStage'), 0.75);
    d.sw = Math.max(0.12, Math.min(1, d.sw || 1));
    d.sh = d.sw * (nat.w / Math.max(1, nat.h)) / aspect;
    if (d.sh > 1) {
      d.sh = 1;
      d.sw = aspect * nat.h / Math.max(1, nat.w);
    }
    d.l = Math.max(0, Math.min(1 - d.sw, d.l || 0));
    d.t = Math.max(0, Math.min(1 - d.sh, d.t || 0));
    return d;
  }

  function layoutImg(imgEl, stageEl, d) {
    if (!imgEl || !stageEl || !nat.w) return;
    d = clampDraft(d, frameAspect(stageEl, 0.75));
    var stageW = stageEl.clientWidth || 280;
    var stageH = stageEl.clientHeight || Math.round(stageW / 0.75);
    var cropW = Math.max(1, d.sw * nat.w);
    var cropH = Math.max(1, d.sh * nat.h);
    var scale = Math.max(stageW / cropW, stageH / cropH);
    imgEl.style.width = (nat.w * scale) + 'px';
    imgEl.style.height = (nat.h * scale) + 'px';
    imgEl.style.left = (-d.l * nat.w * scale) + 'px';
    imgEl.style.top = (-d.t * nat.h * scale) + 'px';
    imgEl.style.transform = 'none';
  }

  function applyToCard(card, d, fullSrc, retry) {
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
      var wrapW = wrap.clientWidth || 0;
      var wrapH = wrap.clientHeight || 0;
      if (!nw || !nh) return;
      if (wrapW < 4 || wrapH < 4) {
        if ((retry || 0) < 8) {
          requestAnimationFrame(function () {
            applyToCard(card, d, fullSrc, (retry || 0) + 1);
          });
        }
        return;
      }
      var aspect = wrapW / wrapH;
      var dd = { l: d.l, t: d.t, sw: d.sw, sh: d.sh };
      dd.sh = dd.sw * (nw / nh) / aspect;
      if (dd.sh > 1) {
        dd.sh = 1;
        dd.sw = aspect * nh / nw;
      }
      dd.l = Math.max(0, Math.min(1 - dd.sw, dd.l || 0));
      dd.t = Math.max(0, Math.min(1 - dd.sh, dd.t || 0));
      var scale = Math.max(
        wrapW / Math.max(1, dd.sw * nw),
        wrapH / Math.max(1, dd.sh * nh)
      );
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

  function reapplyAllPhotoStates() {
    cardsWithPhotos().forEach(function (card) {
      var st = getState(card);
      var full = (window.__spFullPhotos && window.__spFullPhotos[photoKey(card)]) || '';
      applyToCard(card, st, full);
    });
  }
  window.reapplyAllPhotoStates = reapplyAllPhotoStates;

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


  function boot() {
    ensureStyle();
    mergeLocalIntoPhotoCrops();

    var list = cardsWithPhotos();
    if (!list.length) return;

    var shell = $('#spShell') || document.body;
    var room = $('#spPhotoRoom');
    if (!room) {
      room = document.createElement('div');
      room.id = 'spPhotoRoom';
      room.className = 'sp-photo-room';
      room.hidden = true;
      shell.appendChild(room);
    }

    var stage = $('#spPhotoStage', room);
    var imgEl = $('#spPhotoImg', room);
    var rangeEl = $('#spPhotoRange', room);
    var zoomLbl = $('#spPhotoZoomLbl', room);
    var nameEl = $('#spPhotoName', room);
    var roleEl = $('#spPhotoRole', room);
    var badgeRow = $('#spPhotoBadgeRow', room);
    var badgeInput = $('#spPhotoBadge', room);
    var titleEl = $('#spToolbarTitle');
    var saveEl = $('#spToolbarSave');
    var teamTitle = (shell.getAttribute('data-team-name') || titleEl && titleEl.textContent || 'Squad').toUpperCase();

    function enterRoom() {
      room.hidden = false;
      shell.classList.add('is-photo-room');
      document.body.classList.add('is-photo-room');
      if (titleEl) titleEl.textContent = 'CROP PHOTO';
      if (saveEl) saveEl.hidden = true;
    }
    function leaveRoom() {
      room.hidden = true;
      room.classList.remove('is-loading');
      shell.classList.remove('is-photo-room');
      document.body.classList.remove('is-photo-room');
      if (titleEl) titleEl.textContent = teamTitle;
      if (saveEl) saveEl.hidden = false;
    }

    function refreshChrome() {
      layoutImg(imgEl, stage, draft);
      var zp = zoomPct(draft);
      if (rangeEl) rangeEl.value = String(zp);
      if (zoomLbl) zoomLbl.textContent = zp + '%';
    }

    function saveActive() {
      if (!active) return;
      var st = getState(active);
      st.l = draft.l; st.t = draft.t; st.sw = draft.sw; st.sh = draft.sh;
      st.manual = true;
      if (isIconCard(active) && badgeInput) applyBadgeToCard(active, badgeInput.value);
      persistCrops([]);
    }

    function open(card) {
      active = card;
      var st = getState(card);
      if (st.manual) {
        draft = { l: st.l, t: st.t, sw: st.sw, sh: st.sh };
      } else {
        draft = { l: 0, t: 0, sw: 1, sh: 1 };
      }
      var nm = (card.getAttribute('data-player-name') || 'Player').toUpperCase();
      var role = (card.getAttribute('data-player-role') || (card.classList.contains('sp-owner-card') ? 'Team owner' : 'Player')).toUpperCase();
      if (nameEl) nameEl.textContent = nm;
      if (roleEl) roleEl.textContent = role;
      var iconEdit = isIconCard(card);
      if (badgeRow) badgeRow.hidden = !iconEdit;
      if (badgeInput) {
        badgeInput.value = getBadgeText(card);
        badgeInput.oninput = iconEdit ? function () {
          if (active) applyBadgeToCard(active, badgeInput.value);
        } : null;
      }
      enterRoom();
      room.classList.add('is-loading');
      loadFullPhoto(card).then(function (full) {
        if (active !== card) return;
        function ready() {
          nat.w = imgEl.naturalWidth || 1;
          nat.h = imgEl.naturalHeight || 1;
          clampDraft(draft);
          refreshChrome();
          room.classList.remove('is-loading');
        }
        imgEl.onload = ready;
        imgEl.src = full || cropPhotoSrc(card);
        if (imgEl.complete && imgEl.naturalWidth) ready();
      });
    }

    function close(save) {
      var card = active;
      if (save) saveActive();
      active = null;
      drag = null;
      if (badgeInput) badgeInput.oninput = null;
      leaveRoom();
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          if (save && card) {
            var st = getState(card);
            var full = (window.__spFullPhotos && window.__spFullPhotos[photoKey(card)]) || '';
            applyToCard(card, st, full);
          }
          reapplyAllPhotoStates();
          try { window.dispatchEvent(new Event('resize')); } catch (eResize) {}
        });
      });
    }

    function openOffset(delta) {
      if (!list.length) return;
      var i = list.indexOf(active);
      if (i < 0) i = 0;
      if (active) saveActive();
      open(list[(i + delta + list.length) % list.length]);
    }

    list.forEach(function (card) {
      card.addEventListener('click', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        open(card);
      });
    });

    function bumpZoom(delta) {
      setZoomFromPct(zoomPct(draft) + delta);
      refreshChrome();
    }

    var btnDone = $('#spPhotoDone', room);
    var btnReset = $('#spPhotoReset', room);
    var btnPrev = $('#spPhotoPrev', room);
    var btnNext = $('#spPhotoNext', room);
    var btnMinus = $('#spPhotoMinus', room);
    var btnPlus = $('#spPhotoPlus', room);
    if (btnDone) btnDone.addEventListener('click', function (e) { e.preventDefault(); close(true); });
    if (btnReset) btnReset.addEventListener('click', function (e) {
      e.preventDefault();
      if (!active) return;
      draft = { l: 0, t: 0, sw: 1, sh: 1 };
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
    if (btnPrev) btnPrev.addEventListener('click', function (e) { e.preventDefault(); openOffset(-1); });
    if (btnNext) btnNext.addEventListener('click', function (e) { e.preventDefault(); openOffset(1); });
    if (btnMinus) btnMinus.addEventListener('click', function (e) { e.preventDefault(); bumpZoom(-10); });
    if (btnPlus) btnPlus.addEventListener('click', function (e) { e.preventDefault(); bumpZoom(10); });
    if (rangeEl) rangeEl.addEventListener('input', function () {
      setZoomFromPct(parseInt(rangeEl.value, 10) || 100);
      refreshChrome();
    });

    function onDown(ev) {
      if (room.hidden) return;
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
    if (stage) {
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
    }

    window.__spClosePhotoEditor = function () { close(false); };
    window.__spPersistPhotoCrops = function () { return persistCrops([]); };

    var status = $('#spStatus');
    if (status) {
      status.textContent = 'TAP A PLAYER PHOTO TO CROP';
      status.className = 'sp-status is-ok';
    }
    var hintBar = $('.sp-hint');
    if (hintBar) hintBar.textContent = 'TAP A PLAYER PHOTO TO CROP · THEN SAVE PNG OR JPG';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
  setTimeout(function () {
    if (!$('#spPhotoRoom') || !window.__spEditorBooted) return;
  }, 400);
})();
