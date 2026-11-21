/* Squad View — paints the balance Redis snapshot and patches one team on sale. */
(function () {
  'use strict';

  var ACCENTS = ['#7c3aed', '#f59e0b', '#ef4444', '#22c55e', '#3b82f6', '#06b6d4', '#eab308', '#a855f7', '#14b8a6', '#f97316'];
  var root = document.documentElement;
  var app = document.getElementById('sqApp');
  var rowsEl = document.getElementById('sqRows');
  var jsonUrl = root.getAttribute('data-json-url') || '';
  var pollTimer = null;
  var state = { order: '', slots: 0, sigs: {} };

  function fmt(n) {
    n = Math.round(Number(n) || 0);
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }
  function safeSrc(url) {
    url = String(url || '');
    if (url.indexOf('/') === 0 || url.indexOf('https://') === 0 || url.indexOf('http://') === 0) return url;
    return '';
  }
  function facePhoto(url) {
    url = safeSrc(url);
    if (!url || url.indexOf('/auction/public/image/') < 0) return url;
    if (url.indexOf('sz=bs') >= 0) return url.replace('sz=bs', 'sz=sq');
    if (url.indexOf('sz=') < 0) return url + (url.indexOf('?') >= 0 ? '&' : '?') + 'sz=sq';
    return url;
  }
  function initials(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'TM';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase();
  }
  function shortName(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '';
    if (parts.length === 1) return parts[0].toUpperCase();
    return (parts[0].charAt(0) + '. ' + parts[parts.length - 1]).toUpperCase();
  }
  function displayName(name) {
    return String(name || '').trim().toUpperCase();
  }
  function roleLabel(role) {
    return String(role || '').trim();
  }
  function setText(el, text) {
    if (el && el.textContent !== text) el.textContent = text;
  }
  function setLive(kind) {
    var pill = document.getElementById('sqLive');
    if (!pill) return;
    var label = pill.querySelector('.sq-live-label');
    pill.classList.remove('is-wait', 'is-down');
    var text = 'LIVE';
    if (kind === 'wait') { text = 'RECONNECTING'; pill.classList.add('is-wait'); }
    else if (kind === 'down') { text = 'CONNECTION LOST'; pill.classList.add('is-down'); }
    setText(label, text);
  }

  function indexSold(payload) {
    var map = {};
    var sold = ((payload && payload.players) || {}).sold || [];
    var i;
    for (i = 0; i < sold.length; i++) {
      var row = sold[i];
      var tid = Number(row.team_id) || 0;
      if (!tid) continue;
      if (!map[tid]) map[tid] = [];
      map[tid].push(row);
    }
    Object.keys(map).forEach(function (key) {
      map[key].sort(function (a, b) {
        var seqA = Number(a.sold_seq) || 0;
        var seqB = Number(b.sold_seq) || 0;
        if (seqA !== seqB) return seqB - seqA;
        return (Number(b.id) || 0) - (Number(a.id) || 0);
      });
    });
    return map;
  }

  function teamSig(team, players) {
    var parts = [
      team.remaining_points, team.remaining_players_count,
      team.total_point, team.max_players, team.name, team.logo_url
    ];
    var i;
    for (i = 0; i < players.length; i++) {
      var p = players[i];
      parts.push(p.id, p.points, p.role, p.name, p.photo_url);
    }
    return parts.join('|');
  }

  function photoNode(url, label) {
    url = facePhoto(url);
    if (url) {
      var img = document.createElement('img');
      img.className = 'sq-photo';
      img.alt = '';
      img.src = url;
      return img;
    }
    var ph = document.createElement('span');
    ph.className = 'sq-ph';
    ph.textContent = (label || '?').slice(0, 2).toUpperCase();
    return ph;
  }

  function buildCard(player) {
    var card = document.createElement('article');
    card.className = 'sq-card';
    card.setAttribute('data-pid', String(player.id));
    card.title = player.name || '';
    var frame = document.createElement('div');
    frame.className = 'sq-frame';
    frame.appendChild(photoNode(player.photo_url, shortName(player.name) || player.name));
    card.appendChild(frame);
    var meta = document.createElement('div');
    meta.className = 'sq-meta';
    var name = document.createElement('div');
    name.className = 'sq-name';
    name.textContent = displayName(player.name);
    var role = document.createElement('div');
    role.className = 'sq-role';
    role.textContent = roleLabel(player.role);
    var pts = document.createElement('div');
    pts.className = 'sq-pts';
    pts.textContent = fmt(player.points);
    meta.appendChild(name);
    meta.appendChild(role);
    meta.appendChild(pts);
    card.appendChild(meta);
    return card;
  }

  function updateCard(card, player) {
    var name = displayName(player.name);
    var nameEl = card.querySelector('.sq-name');
    setText(nameEl, name);
    if (card.title !== (player.name || '')) card.title = player.name || '';
    var pts = card.querySelector('.sq-pts');
    setText(pts, fmt(player.points));
    var role = card.querySelector('.sq-role');
    setText(role, roleLabel(player.role));
    var want = facePhoto(player.photo_url);
    var frame = card.querySelector('.sq-frame') || card;
    var img = frame.querySelector('.sq-photo');
    var ph = frame.querySelector('.sq-ph');
    if (want) {
      if (!img) {
        if (ph) ph.remove();
        frame.insertBefore(photoNode(want, player.name), frame.firstChild);
      } else if (img.getAttribute('src') !== want) {
        img.src = want;
      }
    } else if (!ph) {
      if (img) img.remove();
      frame.insertBefore(photoNode('', player.name), frame.firstChild);
    }
  }

  function reconcile(strip, players, slots) {
    var byId = {};
    var child = strip.firstChild;
    while (child) {
      if (child.getAttribute) byId[child.getAttribute('data-pid')] = child;
      child = child.nextSibling;
    }
    var frag = document.createDocumentFragment();
    var keep = {};
    var i;
    for (i = 0; i < players.length; i++) {
      var player = players[i];
      var id = String(player.id);
      keep[id] = 1;
      var node = byId[id];
      if (!node) node = buildCard(player);
      else updateCard(node, player);
      frag.appendChild(node);
    }
    var old = strip.firstChild;
    while (old) {
      var next = old.nextSibling;
      if (!keep[old.getAttribute('data-pid')]) strip.removeChild(old);
      old = next;
    }
    strip.appendChild(frag);
  }

  function fillStats(row, team) {
    var maxPlayers = Math.max(0, Math.round(Number(team.max_players) || 0));
    var remaining = Math.max(0, Math.round(Number(team.remaining_players_count) || 0));
    var added = Math.max(0, maxPlayers - remaining);
    setText(row.querySelector('[data-k="pts"]'), fmt(team.remaining_points) + ' / ' + fmt(team.total_point));
    setText(row.querySelector('[data-k="left"]'), added + ' / ' + maxPlayers);
  }

  function buildRow(team, players, index, slots) {
    var row = document.createElement('section');
    row.className = 'sq-row';
    row.setAttribute('data-auction', String(team.id || ''));
    row.style.setProperty('--accent', ACCENTS[index % ACCENTS.length]);
    var teamBox = document.createElement('div');
    teamBox.className = 'sq-team';
    var logo = safeSrc(team.logo_url);
    var mark = document.createElement(logo ? 'img' : 'span');
    if (logo) {
      mark.className = 'sq-logo';
      mark.alt = '';
      mark.src = logo;
      mark.addEventListener('error', function () {
        var ph = document.createElement('span');
        ph.className = 'sq-logo-ph';
        ph.textContent = initials(team.name);
        mark.replaceWith(ph);
      });
    } else {
      mark.className = 'sq-logo-ph';
      mark.textContent = initials(team.name);
    }
    var copy = document.createElement('div');
    copy.className = 'sq-team-copy';
    var name = document.createElement('div');
    name.className = 'sq-tname';
    name.textContent = String(team.name || 'Team').toUpperCase();
    var pts = document.createElement('div');
    pts.className = 'sq-statline';
    pts.innerHTML = '<span>Pts</span><b data-k="pts"></b>';
    var left = document.createElement('div');
    left.className = 'sq-statline';
    left.innerHTML = '<span>Squad</span><b data-k="left"></b>';
    copy.appendChild(name);
    copy.appendChild(pts);
    copy.appendChild(left);
    teamBox.appendChild(mark);
    teamBox.appendChild(copy);
    var strip = document.createElement('div');
    strip.className = 'sq-players';
    row.appendChild(teamBox);
    row.appendChild(strip);
    fillStats(row, team);
    reconcile(strip, players, slots);
    return row;
  }

  function paintHeader(meta) {
    meta = meta || {};
    var name = meta.name || (app && app.getAttribute('data-name')) || '';
    var edition = meta.edition || (app && app.getAttribute('data-edition')) || '';
    var logo = safeSrc(meta.logo_url || (app && app.getAttribute('data-logo')) || '');
    setText(document.getElementById('sqTourName'), name);
    var chip = document.getElementById('sqEdition');
    if (chip) {
      setText(chip, edition);
      chip.hidden = !edition;
    }
    var img = document.querySelector('.sq-tour-logo');
    if (img) {
      if (logo) {
        if (img.getAttribute('src') !== logo) img.src = logo;
        img.hidden = false;
      } else {
        img.hidden = true;
      }
    }
    if (name) document.title = name + ' — Squad View';
  }

  function applySquad(payload) {
    if (!payload || !Array.isArray(payload.teams) || !rowsEl) return;
    paintHeader(payload.squad_meta || {});
    var byTeam = indexSold(payload);
    var teams = payload.teams.slice().sort(function (a, b) {
      return (Number(a.id) || 0) - (Number(b.id) || 0);
    });
    var slots = 1;
    var i;
    for (i = 0; i < teams.length; i++) {
      var roster = byTeam[Number(teams[i].team_id) || 0] || [];
      slots = Math.max(slots, roster.length);
    }
    var order = teams.map(function (t) { return t.id; }).join(',');
    if (slots !== state.slots) {
      app.style.setProperty('--slots', String(slots));
      rowsEl.style.setProperty('--slots', String(slots));
      state.slots = slots;
      state.sigs = {};
    }
    if (!teams.length) {
      rowsEl.style.setProperty('--teams', '1');
      rowsEl.innerHTML = '<div class="sq-empty">No teams on this tournament yet</div>';
      state.order = '';
      state.sigs = {};
    } else if (order !== state.order) {
      var frag = document.createDocumentFragment();
      for (i = 0; i < teams.length; i++) {
        var players = byTeam[Number(teams[i].team_id) || 0] || [];
        frag.appendChild(buildRow(teams[i], players, i, slots));
        state.sigs[teams[i].id] = teamSig(teams[i], players);
      }
      rowsEl.innerHTML = '';
      rowsEl.appendChild(frag);
      rowsEl.style.setProperty('--teams', String(teams.length));
      state.order = order;
    } else {
      for (i = 0; i < teams.length; i++) {
        var team = teams[i];
        var list = byTeam[Number(team.team_id) || 0] || [];
        var sig = teamSig(team, list);
        if (state.sigs[team.id] === sig) continue;
        var row = rowsEl.querySelector('[data-auction="' + team.id + '"]');
        if (!row) continue;
        fillStats(row, team);
        var nameEl = row.querySelector('.sq-tname');
        setText(nameEl, String(team.name || 'Team').toUpperCase());
        reconcile(row.querySelector('.sq-players'), list, slots);
        state.sigs[team.id] = sig;
      }
    }
    var purse = 0;
    var size = 0;
    for (i = 0; i < teams.length; i++) {
      purse = Math.max(purse, Number(teams[i].total_point) || 0);
      size = Math.max(size, Number(teams[i].max_players) || 0);
    }
    setText(document.getElementById('sqTeams'), 'Total teams  ' + teams.length);
    setText(document.getElementById('sqSize'), 'Squad size  ' + (size || slots));
    setText(document.getElementById('sqPurse'), 'Max points  ' + fmt(purse));
    fitBoard();
  }

  function fitBoard() {
    if (!app) return;
    var slots = Math.max(1, state.slots || 1);
    var designW = Math.max(window.innerWidth, 190 + slots * 128);
    var scale = window.innerWidth / designW;
    if (scale > 0.995) {
      app.style.width = '';
      app.style.height = '';
      app.style.transform = '';
      return;
    }
    app.style.width = designW + 'px';
    app.style.height = (window.innerHeight / scale) + 'px';
    app.style.transformOrigin = '0 0';
    app.style.transform = 'scale(' + scale + ')';
  }

  function refresh() {
    if (!jsonUrl) return Promise.resolve();
    return fetch(jsonUrl, { cache: 'no-store', headers: { Accept: 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (payload) {
        applySquad(payload);
        setLive('live');
      })
      .catch(function () {
        setLive('wait');
      });
  }
  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }
  function startPoll() {
    stopPoll();
    refresh();
    pollTimer = setInterval(refresh, 8000);
  }

  paintHeader({});
  var fs = document.getElementById('sqFs');
  function syncFs() {
    document.body.classList.toggle('is-fs', !!document.fullscreenElement);
  }
  if (fs) {
    fs.addEventListener('click', function () {
      if (document.fullscreenElement) {
        if (document.exitFullscreen) document.exitFullscreen();
      } else if (root.requestFullscreen) {
        root.requestFullscreen();
      }
    });
  }
  document.addEventListener('fullscreenchange', syncFs);
  if (app) {
    app.addEventListener('dblclick', function () {
      if (fs) fs.click();
    });
  }
  window.addEventListener('resize', function () { fitBoard(); });
  window.addEventListener('offline', function () { setLive('down'); });
  window.addEventListener('online', function () { setLive('wait'); refresh(); });

  if (window.AuctionChampSSE && window.AuctionChampSSE.enabled(root)) {
    window.AuctionChampSSE.bind({
      url: root.getAttribute('data-sse-url'),
      apply: function (payload) {
        applySquad(payload);
        setLive('live');
      },
      startPoll: startPoll,
      stopPoll: stopPoll,
      onError: function () { setLive('wait'); },
      onPing: function () { setLive('live'); }
    });
  } else {
    startPoll();
  }
})();
