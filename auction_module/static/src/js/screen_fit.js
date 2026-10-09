/* Fit the auction screens into the laptop window at 100% browser zoom.
   A full HD window (about 1920×900) stays full size. A smaller window is
   drawn at the same scale as zooming the browser out, and the page shells
   are stretched so they still fill that window. Phones keep their own layout. */
(function () {
  if (window.__acScreenFit) return;
  window.__acScreenFit = true;

  var FIT_W = 1920;
  var FIT_H = 900;
  var MIN_Z = 0.62;

  function ensureStyle() {
    var tag = document.getElementById('ac-screen-fit-style');
    if (tag) return tag;
    tag = document.createElement('style');
    tag.id = 'ac-screen-fit-style';
    (document.head || document.documentElement).appendChild(tag);
    return tag;
  }

  function apply() {
    var root = document.documentElement;
    var tag = document.getElementById('ac-screen-fit-style');
    root.style.zoom = '';
    root.style.removeProperty('--ac-z');
    root.classList.remove('ac-fitted');
    if (tag) tag.textContent = '';

    var w = window.innerWidth;
    var h = window.innerHeight;
    if (w < 1025) return;

    var z = Math.min(1, w / FIT_W, h / FIT_H);
    if (z > 0.985) return;
    z = Math.max(MIN_Z, Math.round(z * 1000) / 1000);

    root.style.zoom = String(z);
    root.style.setProperty('--ac-z', String(z));
    root.classList.add('ac-fitted');
    ensureStyle().textContent = [
      'html.ac-fitted, html.ac-fitted body {',
      '  height: calc(100dvh / var(--ac-z)) !important;',
      '  min-height: calc(100dvh / var(--ac-z)) !important;',
      '}',
      'html.ac-fitted #pj-root {',
      '  height: calc(100dvh / var(--ac-z)) !important;',
      '}',
      'html.ac-fitted #pj-sponsors { display: block !important; }',
      'html.ac-fitted .hud-arena,',
      'html.ac-fitted body:has(#acLiveBidPad) .hud-arena,',
      'html.ac-fitted body:has(#acLiveBidPad) .bb-stage,',
      'html.ac-fitted body:has(#acLiveBidPad) .pt-stage,',
      'html.ac-fitted body:has(#acLiveBidPad) .lm-stage,',
      'html.ac-fitted body:has(#acLiveBidPad) .sw-stage,',
      'html.ac-fitted body:has(#acLiveBidPad) .cr-arena .cr-stage {',
      '  height: calc(100dvh / var(--ac-z) - 84px - 42px) !important;',
      '}',
      'html.ac-fitted .ac-layout {',
      '  height: calc(100dvh / var(--ac-z) - 68px - 36px) !important;',
      '  margin-top: 68px !important;',
      '}',
      'html.ac-fitted .ac-nav { height: 68px !important; }',
      'html.ac-fitted .ac-powered { height: 36px !important; }',
      'html.ac-fitted .pc-panel {',
      '  height: calc(100dvh / var(--ac-z)) !important;',
      '  max-height: none !important;',
      '}'
    ].join('\n');
  }

  var timer = null;
  function schedule() {
    if (timer) window.clearTimeout(timer);
    timer = window.setTimeout(apply, 40);
  }

  apply();
  window.addEventListener('resize', schedule);
  document.addEventListener('fullscreenchange', apply);
})();
