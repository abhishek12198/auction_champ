/* Bid Summary Sold / Unsold / In-auction boards.
 * Player lists come from the Redis `bal` snapshot (SSE / balance/json).
 * Search, team filter, and paging run in the browser — no per-keystroke ORM.
 */
(function () {
  'use strict';

  var PAGE = 100;
  var state = {
    tab: 'teams',
    offset: 0,
    total: 0,
    teamId: '',
    teamName: '',
    q: '',
    counts: { sold: 0, unsold: 0, auction: 0 },
    snapPlayers: { sold: [], unsold: [], auction: [] },
    useSnap: false,
    listFp: '',
  };

  function $(id) { return document.getElementById(id); }

  function fmtPts(n) {
    if (window.fmtUnit) { return window.fmtUnit(n); }
    try { return Number(n || 0).toLocaleString(); } catch (e) { return String(n || 0); }
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function pinTop() {
    var top = document.querySelector('.bs2-top');
    var main = document.querySelector('.bs2-main');
    if (!top || !main) { return; }
    var h = top.offsetHeight || 0;
    document.documentElement.style.setProperty('--bs2-top-h', h + 'px');
    main.style.paddingTop = (h + 10) + 'px';
  }

  function setCount(el, n) {
    if (el) { el.textContent = String(n || 0); }
  }

  function applyCounts(c) {
    if (!c) { return; }
    var next = {
      sold: Number(c.sold || 0),
      unsold: Number(c.unsold || 0),
      auction: Number(c.auction || 0),
    };
    state.counts = next;
    setCount($('pulse-sold-n'), next.sold);
    setCount($('pulse-unsold-n'), next.unsold);
    setCount($('pulse-auction-n'), next.auction);
  }

  function syncChips() {
    var tab = state.tab;
    ['teams', 'sold', 'unsold', 'auction'].forEach(function (id) {
      var btn = $('pulse-' + id);
      if (!btn) { return; }
      var on = tab === id;
      btn.classList.toggle('active', on);
      btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    var filt = $('pulse-filter');
    if (filt) {
      filt.classList.toggle('is-on', !!(state.teamId && tab === 'sold'));
      var nameEl = $('pulse-filter-name');
      if (nameEl) { nameEl.textContent = state.teamName || ''; }
    }
    document.body.classList.toggle('bs2-tab-teams', tab === 'teams');
    document.body.classList.toggle('bs2-tab-players', tab !== 'teams');
  }

  function attrsHtml(p) {
    var rows = p.attrs || [];
    if (!rows.length) { return ''; }
    return '<div class="bs2-pl-attrs">' + rows.map(function (a) {
      if (!a || !a.v) { return ''; }
      return '<div class="bs2-pl-attr">' +
        '<span class="bs2-pl-attr-k">' + esc(a.k || '') + '</span>' +
        '<span class="bs2-pl-attr-v">' + esc(a.v) + '</span>' +
      '</div>';
    }).join('') + '</div>';
  }

  function rowHtml(p, bucket) {
    var photo = p.photo_url
      ? '<img src="' + esc(p.photo_url) + '" alt="" loading="lazy" decoding="async" onerror="this.style.display=\'none\'"/>'
      : '<span class="bs2-sq-rph">&#128100;</span>';
    var meta = p.role || '';
    var extra = '';
    var pts = '';
    if (bucket === 'sold') {
      extra = '<div class="bs2-pl-team">' +
        (p.team_logo_url ? '<img src="' + esc(p.team_logo_url) + '" alt=""/>' : '') +
        esc(p.team_name || '') + '</div>';
      pts = fmtPts(p.points);
    } else if (bucket === 'unsold') {
      pts = 'UNSOLD';
    } else {
      if (p.on_stage) {
        extra = '<div class="bs2-pl-stage">On stage</div>';
      }
      if (p.base_price) { pts = fmtPts(p.base_price); }
    }
    var sl = p.sl_no ? '#' + p.sl_no + ' ' : '';
    return '<article class="bs2-pl-card' + (p.on_stage ? ' is-stage' : '') + '">' +
      '<div class="bs2-pl-card-photo">' + photo + '</div>' +
      '<div class="bs2-pl-card-body">' +
        '<div class="bs2-pl-card-name">' + sl + esc(p.name || '—') + '</div>' +
        (meta ? '<div class="bs2-pl-card-role">' + esc(meta) + '</div>' : '') +
        attrsHtml(p) +
        extra +
        (pts ? '<div class="bs2-pl-card-pts">' + esc(pts) + '</div>' : '') +
      '</div>' +
    '</article>';
  }

  function matchesQuery(p, q) {
    if (!q) { return true; }
    var term = String(q).toLowerCase();
    var serial = term.replace(/^#/, '').trim();
    var digits = term.replace(/\D/g, '');
    var hay = [
      p.name, p.role, p.team_name, p.contact, p.sl_no
    ].map(function (v) { return String(v == null ? '' : v).toLowerCase(); }).join(' ');
    (p.attrs || []).forEach(function (a) {
      if (!a) { return; }
      hay += ' ' + String(a.k || '').toLowerCase() + ' ' + String(a.v || '').toLowerCase();
    });
    if (hay.indexOf(term) >= 0) { return true; }
    if (/^\d+$/.test(serial) && String(p.sl_no || '') === serial) { return true; }
    var contactDigits = String(p.contact || '').replace(/\D/g, '');
    if (digits.length >= 3 && contactDigits.indexOf(digits) >= 0) { return true; }
    return false;
  }

  function filteredRows() {
    var rows = state.snapPlayers[state.tab] || [];
    return rows.filter(function (p) {
      if (state.teamId && state.tab === 'sold' && String(p.team_id || '') !== String(state.teamId)) {
        return false;
      }
      return matchesQuery(p, state.q);
    });
  }

  function paintTitle() {
    var title = $('pl-title');
    if (!title || state.tab === 'teams') { return; }
    var labels = { sold: 'Sold', unsold: 'Unsold', auction: 'In auction remaining' };
    var label = labels[state.tab] || state.tab;
    if (state.teamId && state.teamName && state.tab === 'sold') {
      label = 'Sold · ' + state.teamName;
    }
    title.textContent = label + ' · ' + state.offset + ' / ' + state.total;
  }

  function renderFromSnap(append) {
    if (state.tab === 'teams') { return; }
    var list = $('pl-list');
    var more = $('pl-more');
    if (!list) { return; }
    var all = filteredRows();
    state.total = all.length;
    if (!append) { state.offset = 0; }
    var slice = all.slice(state.offset, state.offset + PAGE);
    if (!append) {
      if (!slice.length) {
        list.innerHTML = state.q
          ? '<div class="bs2-sq-empty bs2-pl-span">No players match “' + esc(state.q) + '”</div>'
          : '<div class="bs2-sq-empty bs2-pl-span">No players in this list</div>';
      } else {
        list.innerHTML = slice.map(function (p) { return rowHtml(p, state.tab); }).join('');
      }
    } else if (slice.length) {
      list.insertAdjacentHTML('beforeend', slice.map(function (p) {
        return rowHtml(p, state.tab);
      }).join(''));
    }
    state.offset += slice.length;
    if (more) { more.classList.toggle('is-on', state.offset < state.total); }
    paintTitle();
  }

  function listFingerprint(bags) {
    function fp(arr) {
      return (arr || []).map(function (p) {
        var av = (p.attrs || []).map(function (a) {
          return String(a.k || '') + '=' + String(a.v || '');
        }).join(',');
        return [
          p.id, p.photo_url, p.name, p.role, p.team_id,
          p.points, p.on_stage ? 1 : 0, av
        ].join('\x1f');
      }).join('\x1e');
    }
    return fp(bags.sold) + '#' + fp(bags.unsold) + '#' + fp(bags.auction);
  }

  function ingestSnapshot(payload) {
    if (!payload) { return false; }
    if (payload.player_counts) { applyCounts(payload.player_counts); }
    var bags = payload.players;
    if (!bags || typeof bags !== 'object' || Array.isArray(bags)) {
      return false;
    }
    var next = {
      sold: bags.sold || [],
      unsold: bags.unsold || [],
      auction: bags.auction || [],
    };
    var fp = listFingerprint(next);
    var changed = fp !== state.listFp;
    state.snapPlayers = next;
    state.listFp = fp;
    state.useSnap = true;
    return changed;
  }

  function loadPlayers(append) {
    if (state.tab === 'teams') { return; }
    if (state.useSnap) {
      renderFromSnap(append);
      return;
    }
    var list = $('pl-list');
    if (list && !append) {
      list.innerHTML = '<div class="bs2-sq-loading bs2-pl-span">Loading…</div>';
    }
  }

  function setTab(tab, opts) {
    opts = opts || {};
    if (!opts.keepFilter) {
      state.teamId = '';
      state.teamName = '';
    }
    state.tab = tab || 'teams';
    syncChips();
    pinTop();
    if (state.tab !== 'teams') {
      loadPlayers(false);
    }
  }

  function filterSoldByTeam(teamId, teamName) {
    state.teamId = String(teamId || '');
    state.teamName = teamName || '';
    setTab('sold', { keepFilter: true });
  }

  function teamLabel(el) {
    if (!el) { return ''; }
    var n = el.querySelector('.bs2-team-name, .bs2-card-name, .bs2-mob-name');
    return n ? n.textContent.trim() : '';
  }

  window.__acTrackerOnBalance = function (payload) {
    var changed = ingestSnapshot(payload);
    if (state.tab !== 'teams' && (changed || !$('pl-list') || !$('pl-list').children.length)) {
      loadPlayers(false);
    }
  };

  function boot() {
    pinTop();
    window.addEventListener('resize', pinTop);

    ['teams', 'sold', 'unsold', 'auction'].forEach(function (id) {
      var btn = $('pulse-' + id);
      if (btn) {
        btn.addEventListener('click', function () { setTab(id); });
      }
    });
    var more = $('pl-more');
    if (more) {
      more.addEventListener('click', function () { loadPlayers(true); });
    }
    var list = $('pl-list');
    if (list) {
      list.addEventListener('scroll', function () {
        if (state.tab === 'teams' || state.offset >= state.total) { return; }
        if (list.scrollTop + list.clientHeight >= list.scrollHeight - 96) {
          loadPlayers(true);
        }
      });
    }
    var clear = $('pulse-clear');
    if (clear) {
      clear.addEventListener('click', function () {
        state.teamId = '';
        state.teamName = '';
        setTab('sold');
      });
    }

    var search = $('pl-search');
    if (search) {
      var onSearch = function () {
        state.q = (search.value || '').trim();
        if (state.tab !== 'teams') { loadPlayers(false); }
      };
      search.addEventListener('input', onSearch);
      search.addEventListener('search', onSearch);
    }

    var teams = $('tracker-teams');
    if (teams) {
      teams.addEventListener('click', function (e) {
        if (e.target.closest && (e.target.closest('.bs2-eye-btn') || e.target.closest('.bs2-tiers-btn'))) { return; }
        var row = e.target.closest ? e.target.closest('[data-team-id]') : null;
        if (!row) { return; }
        var tid = row.getAttribute('data-team-id');
        if (!tid) { return; }
        filterSoldByTeam(tid, teamLabel(row));
      });
    }

    setTab('teams');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
