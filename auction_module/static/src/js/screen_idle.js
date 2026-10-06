/* Screen idle for projector, live board, and bid summary.
   data-screen-idle on <html> is minutes. 0 keeps the screen awake. */
(function () {
  var root = document.documentElement;
  var minutes = parseInt(root.getAttribute('data-screen-idle') || '0', 10);
  if (isNaN(minutes) || minutes < 0) minutes = 0;
  var idleMs = minutes * 60000;
  var lock = null;
  var timer = null;
  var asleep = false;
  var veil = null;
  var moveGate = false;

  function ensureVeil() {
    if (veil) return veil;
    veil = document.createElement('div');
    veil.id = 'ac-screen-idle';
    veil.setAttribute('role', 'button');
    veil.setAttribute('aria-label', 'Tap to wake');
    veil.textContent = 'Tap to wake';
    veil.style.cssText = [
      'display:none', 'position:fixed', 'inset:0', 'z-index:2147483000',
      'background:#000', 'color:rgba(255,255,255,.62)',
      'align-items:center', 'justify-content:center',
      'font:700 14px/1.2 sans-serif', 'letter-spacing:.18em',
      'text-transform:uppercase', 'cursor:pointer'
    ].join(';');
    (document.body || document.documentElement).appendChild(veil);
    return veil;
  }

  function requestLock() {
    if (asleep || !navigator.wakeLock || !navigator.wakeLock.request) return;
    if (document.visibilityState && document.visibilityState !== 'visible') return;
    navigator.wakeLock.request('screen').then(function (sentinel) {
      if (asleep) {
        sentinel.release().catch(function () {});
        return;
      }
      lock = sentinel;
      sentinel.addEventListener('release', function () {
        if (lock === sentinel) lock = null;
      });
    }).catch(function () {});
  }

  function releaseLock() {
    var sentinel = lock;
    lock = null;
    if (sentinel) sentinel.release().catch(function () {});
  }

  function arm() {
    if (timer) clearTimeout(timer);
    timer = null;
    if (!idleMs || asleep) return;
    timer = setTimeout(sleep, idleMs);
  }

  function sleep() {
    if (asleep || !idleMs) return;
    asleep = true;
    if (timer) clearTimeout(timer);
    timer = null;
    releaseLock();
    ensureVeil().style.display = 'flex';
  }

  function wake() {
    asleep = false;
    if (veil) veil.style.display = 'none';
    requestLock();
    arm();
  }

  function onActivity() {
    if (asleep) wake();
    else {
      if (!lock) requestLock();
      arm();
    }
  }

  ['pointerdown', 'keydown', 'touchstart', 'wheel'].forEach(function (name) {
    window.addEventListener(name, onActivity, { passive: true, capture: true });
  });
  window.addEventListener('mousemove', function () {
    if (moveGate) return;
    moveGate = true;
    setTimeout(function () { moveGate = false; }, 1000);
    onActivity();
  }, { passive: true });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible' && !asleep) requestLock();
  });

  if (document.body) ensureVeil();
  else document.addEventListener('DOMContentLoaded', ensureVeil);

  requestLock();
  arm();
})();
