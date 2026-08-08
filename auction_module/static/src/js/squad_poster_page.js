(function () {
  // Nuke any leftover full-screen editor overlays that steal clicks
  (function killClickBlockers() {
    var nodes = document.querySelectorAll('.sp-peditor, #spPhotoEditor');
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      n.classList.remove('is-open');
      n.style.setProperty('position', 'relative', 'important');
      n.style.setProperty('inset', 'auto', 'important');
      n.style.setProperty('display', 'none', 'important');
      n.style.setProperty('pointer-events', 'none', 'important');
      n.style.setProperty('z-index', '2', 'important');
    }
    var preview = document.querySelector('.sp-preview-wrap');
    if (preview) preview.style.setProperty('pointer-events', 'auto', 'important');
    var scale = document.getElementById('spScaleBox');
    if (scale) scale.style.setProperty('pointer-events', 'none', 'important');
    var canvasEl = document.getElementById('spCanvas');
    if (canvasEl) canvasEl.style.setProperty('pointer-events', 'none', 'important');
  })();

  var CANVAS_W = 1024, CANVAS_H = 1536;
  var shell = document.getElementById('spShell');
  var canvas = document.getElementById('spCanvas');
  var scaleBox = document.getElementById('spScaleBox');
  var zoomSel = document.getElementById('spZoom');
  var scaleSel = document.getElementById('spScale');
  var statusEl = document.getElementById('spStatus');
  var btnPng = document.getElementById('spDlPng');
  var btnJpg = document.getElementById('spDlJpg');
  var btnShare = document.getElementById('spShare');
  var btnPrint = document.getElementById('spPrint');
  var lastBlob = null;
  var lastName = '';
  var lastMime = 'image/png';

  function isMobile() {
    return window.matchMedia('(max-width: 820px)').matches
      || /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '');
  }

  function isIOS() {
    return /iPad|iPhone|iPod/.test(navigator.userAgent || '')
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  }

  function setStatus(msg, kind) {
    if (!statusEl) return;
    statusEl.textContent = msg || '';
    statusEl.className = 'sp-status' + (kind ? ' is-' + kind : '');
  }

  function fitZoomValue() {
    var avail = Math.max(220, (window.innerWidth || 360) - 28);
    var z = avail / CANVAS_W;
    return Math.max(0.18, Math.min(0.92, Math.round(z * 100) / 100));
  }

  function currentZoom() {
    var v = zoomSel && zoomSel.value;
    if (!v || v === 'auto') return fitZoomValue();
    return parseFloat(v) || fitZoomValue();
  }

  function applyZoom() {
    var z = currentZoom();
    if (!scaleBox) return;
    // Prefer CSS zoom: hit-testing matches what you see (transform:scale often breaks clicks)
    var useCssZoom = true;
    try {
      if (typeof CSS !== 'undefined' && CSS.supports && !CSS.supports('zoom', '1')) useCssZoom = false;
    } catch (eZ) {}
    // Firefox historically weak on zoom
    if (/firefox/i.test(navigator.userAgent || '')) useCssZoom = false;
    if (useCssZoom) {
      scaleBox.style.zoom = String(z);
      scaleBox.style.transform = 'none';
      scaleBox.style.transformOrigin = 'top center';
      scaleBox.style.marginBottom = '0';
    } else {
      scaleBox.style.zoom = '';
      scaleBox.style.transform = 'scale(' + z + ')';
      scaleBox.style.transformOrigin = 'top center';
      scaleBox.style.marginBottom = ((CANVAS_H * z) - CANVAS_H) + 'px';
    }
  }

  function syncPalette() {
    var pal = (shell && shell.getAttribute('data-palette')) || 'ember-orange';
    document.querySelectorAll('.sp-swatch').forEach(function (b) {
      b.classList.toggle('is-active', b.getAttribute('data-palette') === pal);
    });
  }

  document.querySelectorAll('.sp-swatch').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var p = btn.getAttribute('data-palette');
      if (shell) shell.setAttribute('data-palette', p);
      syncPalette();
    });
  });

  if (zoomSel) zoomSel.addEventListener('change', applyZoom);
  window.addEventListener('resize', function () {
    if (!zoomSel || zoomSel.value === 'auto') applyZoom();
    sizeSquareCards();
  });
  applyZoom();
  syncPalette();

  // Phones: default to 1× export to avoid OOM crashes
  if (isMobile() && scaleSel) scaleSel.value = '1';

  function fitTeamName() {
    var left = canvas && canvas.querySelector('.sp-team-left');
    var name = canvas && canvas.querySelector('.sp-team-name');
    if (!left || !name) return;
    // Reset scale before measuring
    name.style.transform = 'rotate(-4deg) skewX(-2deg)';
    name.style.transformOrigin = 'left center';
    var maxW = Math.max(40, left.clientWidth - 8);
    var widest = 0;
    name.querySelectorAll('.sp-team-word-face').forEach(function (el) {
      widest = Math.max(widest, el.scrollWidth || el.offsetWidth || 0);
    });
    if (widest < 8) return;
    var scale = Math.min(1, maxW / widest);
    scale = Math.max(0.42, scale);
    name.style.transform = 'rotate(-4deg) skewX(-2deg) scale(' + scale + ')';
  }

  function fitTournamentName() {
    var wrap = canvas && canvas.querySelector('.sp-tourn-titles');
    var title = canvas && (canvas.querySelector('#spTournTitle') || canvas.querySelector('.sp-type--single'));
    if (!wrap || !title) return;
    title.style.transform = 'none';
    title.style.fontSize = '42px';
    var face = title.querySelector('.sp-type-face') || title;
    var maxW = Math.max(80, wrap.clientWidth - 12);
    var textW = face.scrollWidth || face.offsetWidth || title.scrollWidth || 0;
    if (textW < 8) return;
    // Prefer shrinking font-size (keeps one visual size) over multi-line wrap
    var scale = Math.min(1, maxW / textW);
    var px = Math.max(18, Math.floor(42 * scale));
    title.style.fontSize = px + 'px';
    // If still slightly wide after integer px, nudge with scale
    textW = face.scrollWidth || face.offsetWidth || 0;
    if (textW > maxW + 2) {
      var s2 = Math.max(0.55, maxW / textW);
      title.style.transform = 'scale(' + s2 + ')';
    }
  }

  function applyCardSide(cards, sidePx) {
    Array.prototype.forEach.call(cards, function (card) {
      card.style.width = sidePx + 'px';
      card.style.height = sidePx + 'px';
      card.style.maxWidth = sidePx + 'px';
      card.style.flex = '0 0 ' + sidePx + 'px';
    });
  }

  function sizeSquareCards() {
    var layer = canvas && canvas.querySelector('.sp-layer');
    var grid = canvas && canvas.querySelector('.sp-grid-sym');
    var squad = canvas && canvas.querySelector('.sp-squad');
    var cols = 5;
    var gap = 8;
    var side = 0;
    var rowGap = 4;
    if (grid) {
      cols = parseInt(getComputedStyle(grid).getPropertyValue('--sp-cols'), 10) || 5;
      gap = parseFloat(getComputedStyle(grid).getPropertyValue('--sp-card-gap')) || 8;
      rowGap = parseFloat(getComputedStyle(grid).getPropertyValue('--sp-row-gap')) || 4;
      grid.querySelectorAll('.sp-grid-row').forEach(function (row) {
        var rw = row.clientWidth;
        if (rw < 8) return;
        side = Math.floor((rw - (cols - 1) * gap) / cols);
        side = Math.max(48, side);
        applyCardSide(row.querySelectorAll('.sp-card'), side);
      });
      if (squad && side) {
        squad.style.setProperty('--sp-card-side', side + 'px');
        squad.style.setProperty('--sp-row-gap', rowGap + 'px');
      }
    }

    var heroRow = canvas && canvas.querySelector('.sp-icon-hero-row');
    var heroCards = heroRow ? heroRow.querySelectorAll('.sp-card') : [];
    var heroSide = 0;
    if (heroCards.length) {
      var nIcon = heroCards.length;
      var baseSide = side;
      if (!baseSide && squad) {
        var sw0 = squad.clientWidth || 900;
        baseSide = Math.max(120, Math.floor((sw0 - 4 * 8) / 5));
      }
      baseSide = baseSide || 160;
      var rowW = heroRow.clientWidth || (squad && squad.clientWidth) || 900;
      var iconGap = nIcon === 1 ? 0 : (nIcon === 2 ? 28 : (nIcon === 3 ? 18 : 12));
      heroSide = Math.floor((rowW - (nIcon - 1) * iconGap) / nIcon);
      var maxByCount = nIcon === 1 ? 268 : (nIcon === 2 ? 236 : (nIcon === 3 ? 210 : 186));
      var minByCount = nIcon === 1 ? Math.round(baseSide * 1.35) : Math.round(baseSide * 1.08);
      heroSide = Math.max(minByCount, Math.min(heroSide, maxByCount));
      heroSide = Math.max(96, heroSide);
      heroRow.style.setProperty('--sp-icon-gap', iconGap + 'px');
      applyCardSide(heroCards, heroSide);
      if (squad) {
        squad.style.setProperty('--sp-icon-hero-side', heroSide + 'px');
        squad.style.setProperty('--sp-icon-hero-h', (heroSide + 12) + 'px');
        if (!side) {
          squad.style.setProperty('--sp-card-side', baseSide + 'px');
          squad.style.setProperty('--sp-row-gap', rowGap + 'px');
        }
      }
    } else if (squad) {
      squad.style.setProperty('--sp-icon-hero-h', '0px');
    }

    // Shrink cards if icon + grid would clip under strike / sponsors / footer
    if (layer && squad && (side || heroSide)) {
      var layerH = layer.clientHeight;
      var usedOutside = 0;
      var kids = layer.children;
      for (var i = 0; i < kids.length; i++) {
        if (kids[i] === squad) continue;
        usedOutside += kids[i].offsetHeight || 0;
      }
      var layerGap = parseFloat(getComputedStyle(layer).gap) || 3;
      usedOutside += Math.max(0, kids.length - 1) * layerGap;
      var avail = layerH - usedOutside - 8;
      if (avail > 120) {
        var gridRows = grid ? grid.querySelectorAll('.sp-grid-row').length : 0;
        var heroPad = heroCards.length ? 12 : 0;
        var need = (heroSide || 0) + heroPad;
        if (gridRows && side) {
          need += gridRows * side + Math.max(0, gridRows - 1) * rowGap;
        }
        need += 6;
        if (need > avail) {
          var scale = Math.max(0.72, avail / need);
          if (scale < 0.995) {
            if (side && grid) {
              side = Math.max(48, Math.floor(side * scale));
              grid.querySelectorAll('.sp-grid-row').forEach(function (row) {
                applyCardSide(row.querySelectorAll('.sp-card'), side);
              });
              squad.style.setProperty('--sp-card-side', side + 'px');
            }
            if (heroSide && heroCards.length) {
              heroSide = Math.max(84, Math.floor(heroSide * scale));
              applyCardSide(heroCards, heroSide);
              squad.style.setProperty('--sp-icon-hero-side', heroSide + 'px');
              squad.style.setProperty('--sp-icon-hero-h', (heroSide + 12) + 'px');
            }
          }
        }
      }
    }

    var srow = canvas && canvas.querySelector('.sp-sponsors-row');
    if (srow) {
      var sGap = parseFloat(getComputedStyle(srow).getPropertyValue('--sp-card-gap')) || 6;
      var sCols = parseInt(getComputedStyle(srow).getPropertyValue('--sp-cols'), 10) || 10;
      var sw = srow.clientWidth;
      var sSide = Math.max(36, Math.floor((sw - (sCols - 1) * sGap) / sCols));
      srow.querySelectorAll('.sp-sponsor').forEach(function (box) {
        box.style.width = sSide + 'px';
        box.style.height = sSide + 'px';
        box.style.maxWidth = sSide + 'px';
        box.style.flex = '0 0 ' + sSide + 'px';
      });
    }
    fitTeamName();
    fitTournamentName();
    if (typeof reapplyAllPhotoStates === 'function') reapplyAllPhotoStates();
  }

  sizeSquareCards();
  setTimeout(sizeSquareCards, 50);
  setTimeout(sizeSquareCards, 300);
  setTimeout(applyZoom, 60);

  function safeName(s, fallback) {
    var out = String(s || '')
      .trim()
      .replace(/[^\w\-]+/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_|_$/g, '')
      .slice(0, 40);
    return out || (fallback || '');
  }

  function posterTeamName() {
    var fromAttr = shell && shell.getAttribute('data-team-name');
    if (fromAttr) return fromAttr;
    // title: "Squad Poster — TEAM NAME | AuctionChamp"
    var t = document.title || '';
    var m = t.match(/—\s*(.+?)\s*\|/);
    if (m && m[1]) return m[1].trim();
    var parts = t.split('—');
    if (parts.length > 1) return parts[1].split('|')[0].trim();
    return 'Team';
  }

  function posterTournamentName() {
    return (shell && shell.getAttribute('data-tournament-name')) || '';
  }

  function posterFileName(fmt) {
    var team = safeName(posterTeamName(), 'Team');
    var tourn = safeName(posterTournamentName(), '');
    var base = tourn ? (team + '_' + tourn) : team;
    if (base.length > 72) base = base.slice(0, 72).replace(/_+$/, '');
    return base + '_Squad_poster.' + (fmt === 'jpg' ? 'jpg' : 'png');
  }

  function showShareBtn(show) {
    if (!btnShare) return;
    btnShare.style.display = show ? '' : 'none';
  }

  function openImagePreview(blob, filename) {
    var url = URL.createObjectURL(blob);
    var w = window.open('', '_blank');
    if (w) {
      w.document.write(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"/>'
        + '<title>' + filename + '</title>'
        + '<style>html,body{margin:0;background:#111;color:#fff;font-family:sans-serif;text-align:center}'
        + 'p{padding:12px;font-size:14px}img{max-width:100%;height:auto;display:block;margin:0 auto}</style></head><body>'
        + '<p>Long-press the image → <b>Save Image</b> / Share</p>'
        + '<img src="' + url + '" alt="Squad poster"/>'
        + '</body></html>'
      );
      w.document.close();
      setStatus('Long-press the image to save it to your phone', 'ok');
      return true;
    }
    // Popup blocked — navigate same tab
    window.location.href = url;
    return false;
  }

  function downloadBlob(blob, filename) {
    lastBlob = blob;
    lastName = filename;
    lastMime = blob.type || 'image/png';
    showShareBtn(true);

    // Prefer native share sheet on phones (best UX)
    if (isMobile() && navigator.share && navigator.canShare) {
      try {
        var file = new File([blob], filename, { type: lastMime });
        if (navigator.canShare({ files: [file] })) {
          navigator.share({
            files: [file],
            title: 'Squad Poster',
            text: filename
          }).then(function () {
            setStatus('Shared · ' + filename, 'ok');
          }).catch(function (err) {
            if (err && err.name === 'AbortError') {
              setStatus('Share cancelled — try Save again or Share', '');
              return;
            }
            // Fall through to download / preview
            legacyDownload(blob, filename);
          });
          return;
        }
      } catch (e) { /* fall through */ }
    }

    legacyDownload(blob, filename);
  }

  function legacyDownload(blob, filename) {
    var url = URL.createObjectURL(blob);
    // iOS Safari often ignores <a download> for blobs
    if (isIOS() || isMobile()) {
      openImagePreview(blob, filename);
      setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
      return;
    }
    var a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { URL.revokeObjectURL(url); a.remove(); }, 2000);
    setStatus('Downloaded · ' + filename, 'ok');
  }

  if (btnShare) {
    btnShare.addEventListener('click', function () {
      if (!lastBlob) {
        setStatus('Save the poster first, then Share', 'err');
        return;
      }
      if (!(navigator.share && navigator.canShare)) {
        openImagePreview(lastBlob, lastName || 'squad_poster.png');
        return;
      }
      try {
        var file = new File([lastBlob], lastName || 'squad_poster.png', { type: lastMime });
        if (!navigator.canShare({ files: [file] })) {
          openImagePreview(lastBlob, lastName || 'squad_poster.png');
          return;
        }
        navigator.share({ files: [file], title: 'Squad Poster' }).catch(function () {});
      } catch (e) {
        openImagePreview(lastBlob, lastName || 'squad_poster.png');
      }
    });
  }

  function exportPoster(fmt) {
    if (!window.html2canvas) {
      setStatus('Export library missing. Hard-refresh the page.', 'err');
      return;
    }
    var scale = parseInt(scaleSel && scaleSel.value, 10) || 1;
    if (isMobile()) scale = Math.min(scale, 1); // hard-cap on phones
    var buttons = [btnPng, btnJpg, btnShare];
    buttons.forEach(function (b) { if (b) b.disabled = true; });
    setStatus('Preparing poster…', '');

    var prev = scaleBox ? scaleBox.style.transform : '';
    var prevOrigin = scaleBox ? scaleBox.style.transformOrigin : '';
    var prevZoom = scaleBox ? scaleBox.style.zoom : '';
    // Capture at full size (unscaled) — critical for mobile
    if (scaleBox) {
      scaleBox.style.zoom = '1';
      scaleBox.style.transform = 'none';
      scaleBox.style.transformOrigin = 'top left';
      scaleBox.style.marginBottom = '0';
    }

  function restoreExportUi() {
    if (canvas) canvas.classList.remove('is-exporting');
    if (scaleBox) {
      scaleBox.style.zoom = prevZoom || '';
      scaleBox.style.transform = prev || '';
      scaleBox.style.transformOrigin = prevOrigin || 'top center';
      applyZoom();
    }
  }

  function restoreSloganLogoSrc() {
    var logo = canvas && canvas.querySelector('.sp-slogan-logo');
    if (!logo) return;
    var prev = logo.getAttribute('data-sp-export-prev');
    if (prev) {
      logo.setAttribute('src', prev);
      logo.removeAttribute('data-sp-export-prev');
    }
    logo.style.filter = '';
    logo.style.opacity = '';
  }

  /** html2canvas drops SVG <img>; rasterize slogan logo to PNG data-URL first. */
  function prepareSloganLogoForExport(done) {
    var logo = canvas && canvas.querySelector('.sp-slogan-logo');
    if (!logo) { done(); return; }
    var prev = logo.getAttribute('src') || '';
    if (!logo.getAttribute('data-sp-export-prev')) {
      logo.setAttribute('data-sp-export-prev', prev);
    }
    if (prev.indexOf('data:image/png') === 0) { done(); return; }

    function applyDataUrl(dataUrl) {
      logo.style.filter = 'none';
      logo.style.opacity = '0.42';
      logo.setAttribute('src', dataUrl);
      if (logo.complete && logo.naturalWidth) done();
      else {
        logo.onload = function () { done(); };
        logo.onerror = function () { usePngFallback(); };
      }
    }

    function usePngFallback() {
      logo.style.filter = 'none';
      logo.style.opacity = '0.42';
      logo.setAttribute('src', '/auction_module/static/description/icon.png');
      if (logo.complete && logo.naturalWidth) done();
      else {
        logo.onload = function () { done(); };
        logo.onerror = function () { done(); };
      }
    }

    function canvasHasInk(c) {
      try {
        var x = c.getContext('2d');
        var d = x.getImageData(0, 0, Math.min(c.width, 64), Math.min(c.height, 64)).data;
        for (var i = 3; i < d.length; i += 16) {
          if (d[i] > 8) return true;
        }
      } catch (e) {}
      return false;
    }

    function drawToPng(im) {
      try {
        var w = Math.max(2, im.naturalWidth || 241);
        var h = Math.max(2, im.naturalHeight || 37);
        var c = document.createElement('canvas');
        c.width = w * 2;
        c.height = h * 2;
        var x = c.getContext('2d');
        if (!x || !c.width || !c.height) { usePngFallback(); return; }
        x.clearRect(0, 0, c.width, c.height);
        x.drawImage(im, 0, 0, c.width, c.height);
        if (!canvasHasInk(c)) { usePngFallback(); return; }
        applyDataUrl(c.toDataURL('image/png'));
      } catch (e) {
        usePngFallback();
      }
    }

    if (prev.indexOf('.svg') !== -1) {
      fetch(prev, { credentials: 'same-origin' }).then(function (r) {
        if (!r.ok) throw new Error('svg fetch failed');
        return r.text();
      }).then(function (svgText) {
        // Explicit size required or canvas draw is blank in many browsers
        var patched = svgText;
        if (!/\swidth\s*=/.test(patched)) {
          patched = patched.replace(/<svg\b/, '<svg width="482" height="74"');
        }
        var blob = new Blob([patched], { type: 'image/svg+xml;charset=utf-8' });
        var url = URL.createObjectURL(blob);
        var im = new Image();
        im.onload = function () {
          drawToPng(im);
          URL.revokeObjectURL(url);
        };
        im.onerror = function () {
          URL.revokeObjectURL(url);
          usePngFallback();
        };
        im.src = url;
      }).catch(function () { usePngFallback(); });
    } else {
      var im2 = new Image();
      im2.crossOrigin = 'anonymous';
      im2.onload = function () { drawToPng(im2); };
      im2.onerror = function () { usePngFallback(); };
      im2.src = prev;
    }
  }

  function runCapture() {
    sizeSquareCards();
    if (canvas) canvas.classList.add('is-exporting');
    if (window.__spClosePhotoEditor) {
      try { window.__spClosePhotoEditor(false); } catch (eClose) {}
    }

    // Hide blend/filter FX on the live DOM too (ignoreElements alone is not enough)
    var killed = [];
    function softHide(sel) {
      canvas.querySelectorAll(sel).forEach(function (el) {
        killed.push({ el: el, v: el.style.visibility, d: el.style.display, f: el.style.filter, m: el.style.mixBlendMode });
        el.style.visibility = 'hidden';
        el.style.filter = 'none';
        el.style.mixBlendMode = 'normal';
      });
    }
    softHide('.sp-fx-smoke, .sp-fx-fire, .sp-fx-sparks, .sp-fx-flare, .sp-brand-logo, .sp-type-glow');
    canvas.querySelectorAll('img').forEach(function (img) {
      if (img.classList && img.classList.contains('sp-slogan-logo')) return;
      img.style.filter = 'none';
      img.style.mixBlendMode = 'normal';
    });
    canvas.querySelectorAll('.sp-team-logo-wrap, .sp-tourn-logo, .sp-sponsor').forEach(function (el) {
      el.style.filter = 'none';
    });

    var opts = {
      scale: scale,
      width: CANVAS_W,
      height: CANVAS_H,
      windowWidth: CANVAS_W,
      windowHeight: CANVAS_H,
      x: 0,
      y: 0,
      scrollX: 0,
      scrollY: 0,
      backgroundColor: '#050506',
      useCORS: true,
      allowTaint: true,
      logging: false,
      imageTimeout: 15000,
      foreignObjectRendering: false,
      removeContainer: true,
      ignoreElements: function (el) {
        if (!el || !el.tagName) return false;
        var tag = el.tagName.toLowerCase();
        if (tag === 'svg') return true;
        if (el.classList) {
          if (el.classList.contains('sp-brand-logo')) return true;
          if (el.classList.contains('sp-fx-smoke')) return true;
          if (el.classList.contains('sp-fx-fire')) return true;
          if (el.classList.contains('sp-fx-sparks')) return true;
          if (el.classList.contains('sp-fx-flare')) return true;
          if (el.classList.contains('sp-type-glow')) return true;
          if (el.classList.contains('sp-photo-edit-btn')) return true;
          if (el.classList.contains('sp-peditor')) return true;
          if (el.classList.contains('sp-hint')) return true;
        }
        if (tag === 'img' && el.classList && el.classList.contains('sp-slogan-logo')) return false;
        if (tag === 'img' && el.complete && el.naturalWidth === 0) return true;
        return false;
      },
      onclone: function (doc, cloned) {
        var root = doc.getElementById('spCanvas') || cloned;
        if (root) {
          root.classList.add('is-exporting');
          root.style.width = CANVAS_W + 'px';
          root.style.height = CANVAS_H + 'px';
          root.style.transform = 'none';
          root.style.overflow = 'hidden';
        }
        // Kill every blend/filter in the clone tree
        Array.prototype.forEach.call(doc.querySelectorAll('*'), function (n) {
          if (!n.style) return;
          n.style.mixBlendMode = 'normal';
          n.style.filter = 'none';
          n.style.backdropFilter = 'none';
          n.style.webkitBackdropFilter = 'none';
        });
        Array.prototype.forEach.call(
          doc.querySelectorAll('svg, .sp-brand-logo, .sp-fx-smoke, .sp-fx-fire, .sp-fx-sparks, .sp-fx-flare, .sp-type-glow'),
          function (n) { if (n && n.parentNode) n.parentNode.removeChild(n); }
        );
        // Export-safe slogan watermark (logo is already a PNG data-URL)
        var slogan = doc.querySelector('.sp-slogan');
        if (slogan) {
          slogan.style.zIndex = '0';
          slogan.style.opacity = '1';
          slogan.style.visibility = 'visible';
          slogan.style.display = 'flex';
        }
        Array.prototype.forEach.call(doc.querySelectorAll('.sp-slogan-logo'), function (img) {
          img.style.filter = 'none';
          img.style.opacity = '0.42';
          img.style.visibility = 'visible';
          img.style.display = 'block';
        });
        Array.prototype.forEach.call(doc.querySelectorAll('.sp-slogan-word'), function (el) {
          el.style.setProperty('color', 'rgba(255,255,255,0.45)', 'important');
          el.style.setProperty('-webkit-text-fill-color', 'rgba(255,255,255,0.45)', 'important');
          el.style.setProperty('opacity', '1', 'important');
          el.style.setProperty('visibility', 'visible', 'important');
        });
        Array.prototype.forEach.call(doc.querySelectorAll('.sp-slogan-dot'), function (el) {
          el.style.setProperty('color', 'rgba(232,197,71,0.5)', 'important');
          el.style.setProperty('-webkit-text-fill-color', 'rgba(232,197,71,0.5)', 'important');
          el.style.setProperty('opacity', '1', 'important');
        });
        // Opaque title fills
        var nodes = doc.querySelectorAll('.sp-type-face, .sp-team-word-face, .sp-season, .sp-strike-title, .sp-strike-num');
        for (var i = 0; i < nodes.length; i++) {
          var el = nodes[i];
          var fill = '#f0c24a';
          if (el.classList.contains('sp-season')) fill = '#ffe7a8';
          else if (el.classList.contains('sp-strike-num')) fill = '#ffffff';
          else if (el.classList.contains('sp-strike-title')) fill = '#f0c24a';
          else if (el.closest('.sp-type--silver')) fill = '#e8eef5';
          else if (el.closest('.sp-type--single')) fill = '#f0c24a';
          else if (el.closest('.sp-type--hero')) fill = '#ffd060';
          else if (el.classList.contains('sp-team-word-face')) {
            var word = el.closest('.sp-team-word');
            var parent = word && word.parentElement;
            var sibs = parent ? parent.children : [];
            var wordList = [];
            for (var w = 0; w < sibs.length; w++) {
              if (sibs[w].classList && sibs[w].classList.contains('sp-team-word')) wordList.push(sibs[w]);
            }
            if (wordList.length === 1) fill = '#ff8a8a';
            else if (wordList.length && word === wordList[0]) fill = '#f2f5fa';
            else fill = '#ff8a8a';
          }
          el.style.setProperty('background-image', 'none', 'important');
          el.style.setProperty('background', 'transparent', 'important');
          el.style.setProperty('-webkit-background-clip', 'border-box', 'important');
          el.style.setProperty('background-clip', 'border-box', 'important');
          el.style.setProperty('color', fill, 'important');
          el.style.setProperty('-webkit-text-fill-color', fill, 'important');
          el.style.setProperty('-webkit-text-stroke', '0', 'important');
          el.style.setProperty('filter', 'none', 'important');
        }
        // Solid rules (gradients → pattern canvases can go 0×0)
        Array.prototype.forEach.call(
          doc.querySelectorAll('.sp-strike-rule, .sp-sponsors-rule, .sp-season-rule'),
          function (n) {
            n.style.background = '#e8c547';
            n.style.backgroundImage = 'none';
            n.style.height = '2px';
            n.style.opacity = '0.85';
          }
        );
        // Sponsor tiles — force non-zero boxes
        var srow = doc.querySelector('.sp-sponsors-row');
        if (srow) {
          var sCols = 10, sGap = 6, sw = CANVAS_W - 52;
          var sSide = Math.max(40, Math.floor((sw - (sCols - 1) * sGap) / sCols));
          Array.prototype.forEach.call(srow.querySelectorAll('.sp-sponsor'), function (box) {
            box.style.width = sSide + 'px';
            box.style.height = sSide + 'px';
            box.style.minWidth = sSide + 'px';
            box.style.minHeight = sSide + 'px';
            box.style.flex = '0 0 ' + sSide + 'px';
          });
        }
        // Drop zero-size / broken images from clone (keep slogan logo — already PNG data-URL)
        Array.prototype.forEach.call(doc.querySelectorAll('img'), function (img) {
          var src = img.getAttribute('src') || '';
          var isSlogan = img.classList && img.classList.contains('sp-slogan-logo');
          if (isSlogan) {
            img.style.filter = 'none';
            img.style.mixBlendMode = 'normal';
            img.style.opacity = '0.42';
            return;
          }
          if (!src || src.indexOf('.svg') !== -1) {
            if (img.parentNode) img.parentNode.removeChild(img);
            return;
          }
          img.style.filter = 'none';
          img.style.mixBlendMode = 'normal';
          if (img.style.width === '0px' || img.style.height === '0px') {
            if (img.parentNode) img.parentNode.removeChild(img);
          }
        });
      }
    };

    function cleanupKilled() {
      killed.forEach(function (k) {
        k.el.style.visibility = k.v || '';
        k.el.style.display = k.d || '';
        k.el.style.filter = k.f || '';
        k.el.style.mixBlendMode = k.m || '';
      });
      restoreSloganLogoSrc();
    }

    window.html2canvas(canvas, opts).then(function (off) {
      cleanupKilled();
      restoreExportUi();
      // Always rasterize via an offscreen canvas (avoids JPEG alpha quirks)
      var out = document.createElement('canvas');
      out.width = off.width;
      out.height = off.height;
      if (!out.width || !out.height) {
        buttons.forEach(function (b) { if (b) b.disabled = false; });
        setStatus('Export failed — empty canvas. Try Save PNG.', 'err');
        return;
      }
      var ctx = out.getContext('2d');
      ctx.fillStyle = '#050506';
      ctx.fillRect(0, 0, out.width, out.height);
      ctx.drawImage(off, 0, 0);
      var mime = fmt === 'jpg' ? 'image/jpeg' : 'image/png';
      var q = fmt === 'jpg' ? 0.92 : undefined;
      function finish(blob) {
        buttons.forEach(function (b) { if (b) b.disabled = false; });
        if (!blob) { setStatus('Export failed — try again.', 'err'); return; }
        var filename = posterFileName(fmt);
        downloadBlob(blob, filename);
        if (!isMobile()) {
          setStatus('Saved · ' + out.width + '×' + out.height, 'ok');
        }
      }
      if (out.toBlob) {
        out.toBlob(finish, mime, q);
      } else {
        var dataUrl = out.toDataURL(mime, q);
        var arr = dataUrl.split(','), bstr = atob(arr[1]), n = bstr.length, u8 = new Uint8Array(n);
        while (n--) u8[n] = bstr.charCodeAt(n);
        finish(new Blob([u8], { type: mime }));
      }
    }).catch(function (err) {
      cleanupKilled();
      restoreExportUi();
      buttons.forEach(function (b) { if (b) b.disabled = false; });
      setStatus('Export error: ' + (err && err.message ? err.message : err) + ' — try Save PNG', 'err');
    });
  }

  // Wait for webfonts + images + layout settle, then rasterize SVG slogan logo for export
  var fontsReady = (document.fonts && document.fonts.ready)
    ? document.fonts.ready.catch(function () {})
    : Promise.resolve();
  fontsReady.then(function () {
    setTimeout(function () {
      var persist = (typeof window.__spPersistPhotoCrops === 'function')
        ? window.__spPersistPhotoCrops()
        : Promise.resolve();
      Promise.resolve(persist).finally(function () {
        prepareSloganLogoForExport(function () {
          runCapture();
        });
      });
    }, 120);
  });
}

  if (btnPng) btnPng.addEventListener('click', function () { exportPoster('png'); });
  if (btnJpg) btnJpg.addEventListener('click', function () { exportPoster('jpg'); });
  if (btnPrint) btnPrint.addEventListener('click', function () { window.print(); });

  // Photo editing handled by squad_poster_editor.js (injected by controller)
  window.__spClosePhotoEditor = window.__spClosePhotoEditor || function () {};
  window.spEditPlayer = window.spEditPlayer || function () { return false; };
})();
