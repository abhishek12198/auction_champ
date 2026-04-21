odoo.define('auction_module.PlayerDashboard', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    // ── Chart palette ────────────────────────────────────────────────────────
    var STATE_COLORS  = ['#64b5f6', '#ffca28', '#66bb6a', '#ef5350'];
    var STATE_LABELS  = ['Draft', 'In Auction', 'Sold', 'Unsold'];
    var STATE_KEYS    = ['draft', 'auction', 'sold', 'unsold'];
    var ROLE_PALETTE  = ['#ab47bc','#26c6da','#ff7043','#66bb6a','#ffa726','#78909c','#ec407a','#42a5f5'];
    var BAR_COLOR     = 'rgba(100,181,246,0.85)';
    var BAR_BORDER    = '#1565c0';
    var TIER_PALETTE  = ['#ffd54f','#80cbc4','#ce93d8','#a5d6a7','#ef9a9a','#90caf9','#bcaaa4'];
    var TEAM_PALETTE  = ['#f48fb1','#80deea','#a5d6a7','#ffe082','#b39ddb','#80cbc4','#ff8a65','#90caf9','#c5e1a5','#ffcc80'];

    var PlayerDashboard = AbstractAction.extend({
        events: {
            'click .pd-refresh-btn':  '_onRefresh',
            'click .pd-theme-toggle': '_onToggleTheme',
            'click .pd-stat':         '_onStatClick',
        },

        // Mapping from stat card class → [action name, domain]
        _STAT_ACTIONS: {
            'total':   ['All Players',         []],
            'draft':   ['Draft Players',        [['state', '=', 'draft']]],
            'auction': ['Players In Auction',   [['state', '=', 'auction']]],
            'sold':    ['Sold Players',         [['state', '=', 'sold']]],
            'unsold':  ['Unsold Players',       [['state', '=', 'unsold']]],
            'icon':    ['Icon / Key Players',   [['icon_player', '=', true]]],
            'paid':    ['Paid Players',         [['amount_paid', '=', true]]],
            'unpaid':  ['Unpaid Players',       [['amount_paid', '=', false]]],
        },

        _charts: {},
        _timer: null,
        _viewIds: {},

        start: function () {
            this.$el.addClass('o_player_dashboard');
            this.$el.html(this._buildLayout());
            var result = this._super.apply(this, arguments);
            if (localStorage.getItem('pd_theme') === 'light') {
                this.$el.addClass('pd-light');
                this.$el.find('.pd-theme-toggle').html('&#9790; Dark');
            }
            this._loadData();
            var self = this;
            this._timer = setInterval(function () { self._loadData(); }, 30000);
            return result;
        },

        destroy: function () {
            if (this._timer) { clearInterval(this._timer); }
            Object.values(this._charts).forEach(function (c) { if (c) c.destroy(); });
            this._super.apply(this, arguments);
        },

        // ── Layout ───────────────────────────────────────────────────────────
        _buildLayout: function () {
            return [
                '<div class="pd-hdr">',
                    '<div class="pd-hdr-logo-wrap">',
                        '<span class="pd-hdr-logo-ph">&#128100;</span>',
                    '</div>',
                    '<div class="pd-hdr-text">',
                        '<span class="pd-hdr-title">Player Detail Dashboard</span>',
                        '<span class="pd-hdr-sub" id="pd-sub">All Players &mdash; Registration Analytics</span>',
                    '</div>',
                    '<span class="pd-live-badge">&#9679; Live</span>',
                    '<button class="pd-theme-toggle">&#9790; Dark</button>',
                    '<button class="pd-refresh-btn">&#8635; Refresh</button>',
                '</div>',

                /* ── Stat cards ── */
                '<div class="pd-stat-row">',
                    '<div class="pd-stat total"><span class="pd-stat-num" id="pd-total">0</span><span class="pd-stat-lbl">Total</span></div>',
                    '<div class="pd-stat draft"><span class="pd-stat-num" id="pd-draft">0</span><span class="pd-stat-lbl">Draft</span></div>',
                    '<div class="pd-stat auction"><span class="pd-stat-num" id="pd-auction">0</span><span class="pd-stat-lbl">In Auction</span></div>',
                    '<div class="pd-stat sold"><span class="pd-stat-num" id="pd-sold">0</span><span class="pd-stat-lbl">Sold</span></div>',
                    '<div class="pd-stat unsold"><span class="pd-stat-num" id="pd-unsold">0</span><span class="pd-stat-lbl">Unsold</span></div>',
                    '<div class="pd-stat icon"><span class="pd-stat-num" id="pd-icon">0</span><span class="pd-stat-lbl">Icon Players</span></div>',
                    '<div class="pd-stat paid"><span class="pd-stat-num" id="pd-paid">0</span><span class="pd-stat-lbl">Paid</span></div>',
                    '<div class="pd-stat unpaid"><span class="pd-stat-num" id="pd-unpaid">0</span><span class="pd-stat-lbl">Unpaid</span></div>',
                '</div>',

                /* ── Row 1: State pie + Daily bar ── */
                '<div class="pd-row">',
                    '<div class="pd-card pd-half">',
                        '<div class="pd-card-title">&#127941; Player State Distribution</div>',
                        '<div class="pd-chart-wrap"><canvas id="pd-pie-state"></canvas></div>',
                        '<div class="pd-legend" id="pd-pie-legend"></div>',
                    '</div>',
                    '<div class="pd-card pd-half">',
                        '<div class="pd-card-title">&#128197; Daily Registrations (Last 5 Days)</div>',
                        '<div class="pd-chart-wrap"><canvas id="pd-bar-daily"></canvas></div>',
                    '</div>',
                '</div>',

                /* ── Row 2: Role donut + Tier bar ── */
                '<div class="pd-row">',
                    '<div class="pd-card pd-half">',
                        '<div class="pd-card-title">&#127931; Role Distribution</div>',
                        '<div class="pd-chart-wrap"><canvas id="pd-donut-role"></canvas></div>',
                        '<div class="pd-legend" id="pd-role-legend"></div>',
                    '</div>',
                    '<div class="pd-card pd-half">',
                        '<div class="pd-card-title">&#127942; Tier Distribution</div>',
                        '<div class="pd-chart-wrap"><canvas id="pd-bar-tier"></canvas></div>',
                    '</div>',
                '</div>',

                /* ── Row 3: Players per Team bar + Payment donut ── */
                '<div class="pd-row">',
                    '<div class="pd-card pd-half">',
                        '<div class="pd-card-title">&#127952; Players per Team</div>',
                        '<div class="pd-chart-wrap"><canvas id="pd-bar-team"></canvas></div>',
                    '</div>',
                    '<div class="pd-card pd-half">',
                        '<div class="pd-card-title">&#128176; Payment Status</div>',
                        '<div class="pd-chart-wrap pd-chart-small"><canvas id="pd-donut-pay"></canvas></div>',
                        '<div class="pd-legend" id="pd-pay-legend"></div>',
                    '</div>',
                '</div>',

                /* ── Row 4: Icon / Key Players table ── */
                '<div class="pd-row">',
                    '<div class="pd-card pd-full">',
                        '<div class="pd-card-title">&#11088; Icon / Key Players &mdash; Team Assignment</div>',
                        '<div class="pd-table-wrap">',
                            '<table class="pd-table" id="pd-icon-table">',
                                '<thead><tr>',
                                    '<th>#</th><th>Photo</th><th>Player</th><th>Role</th>',
                                    '<th>Tier</th><th>Team</th><th>Sold For (Pts)</th>',
                                '</tr></thead>',
                                '<tbody id="pd-icon-tbody"><tr><td colspan="7" class="pd-empty">Loading...</td></tr></tbody>',
                            '</table>',
                        '</div>',
                    '</div>',
                '</div>',

                /* ── Row 5: Last 10 draft players table ── */
                '<div class="pd-row">',
                    '<div class="pd-card pd-full">',
                        '<div class="pd-card-title">&#128203; Last 10 Players Added to Draft</div>',
                        '<div class="pd-table-wrap">',
                            '<table class="pd-table" id="pd-draft-table">',
                                '<thead><tr>',
                                    '<th>#</th><th>Photo</th><th>Name</th><th>Role</th>',
                                    '<th>Tier</th><th>Base Price</th><th>Added On</th>',
                                '</tr></thead>',
                                '<tbody id="pd-draft-tbody"><tr><td colspan="7" class="pd-empty">Loading...</td></tr></tbody>',
                            '</table>',
                        '</div>',
                    '</div>',
                '</div>',
            ].join('');
        },

        // ── Data load ────────────────────────────────────────────────────────
        _loadData: function () {
            var self = this;
            fetch('/auction/player-dashboard/data', { cache: 'no-store' })
                .then(function (r) { return r.json(); })
                .then(function (d) { self._render(d); })
                .catch(function (e) { console.error('Player dashboard load failed', e); });
        },

        _render: function (d) {
            // cache resolved view IDs for stat card navigation
            this._viewIds = d.view_ids || {};

            var sc = d.state_counts || {};
            this.$('#pd-total').text(this._fmt(d.total));
            this.$('#pd-draft').text(this._fmt(sc.draft));
            this.$('#pd-auction').text(this._fmt(sc.auction));
            this.$('#pd-sold').text(this._fmt(sc.sold));
            this.$('#pd-unsold').text(this._fmt(sc.unsold));
            this.$('#pd-icon').text(this._fmt(d.icon_count));
            this.$('#pd-paid').text(this._fmt(d.paid_count));
            this.$('#pd-unpaid').text(this._fmt(d.unpaid_count));

            this._renderStatePie(sc);
            this._renderDailyBar(d.daily || []);
            this._renderRoleDonut(d.roles || []);
            this._renderTierBar(d.tiers || []);
            this._renderTeamBar(d.team_player_counts || []);
            this._renderPayDonut(d.paid_count, d.unpaid_count);
            this._renderIconTable(d.icon_players || []);
            this._renderDraftTable(d.draft_players || []);
        },

        // ── Charts ───────────────────────────────────────────────────────────
        _gridColor: function () {
            return this.$el.hasClass('pd-light') ? 'rgba(0,0,0,.08)' : 'rgba(255,255,255,.08)';
        },
        _tickColor: function () {
            return this.$el.hasClass('pd-light') ? '#444' : 'rgba(255,255,255,.7)';
        },

        _renderStatePie: function (sc) {
            var data = STATE_KEYS.map(function (k) { return sc[k] || 0; });
            this._drawPie('pd-pie-state', STATE_LABELS, data, STATE_COLORS, 'pd-pie-legend');
        },

        _renderRoleDonut: function (roles) {
            var labels = roles.map(function (r) { return r.label; });
            var data   = roles.map(function (r) { return r.count; });
            var colors = labels.map(function (_, i) { return ROLE_PALETTE[i % ROLE_PALETTE.length]; });
            this._drawPie('pd-donut-role', labels, data, colors, 'pd-role-legend', true);
        },

        _renderPayDonut: function (paid, unpaid) {
            this._drawPie('pd-donut-pay', ['Paid', 'Unpaid'], [paid || 0, unpaid || 0],
                ['#66bb6a', '#ef5350'], 'pd-pay-legend', true);
        },

        _drawPie: function (canvasId, labels, data, colors, legendId, donut) {
            var self = this;
            var ctx = this.$('#' + canvasId)[0];
            if (!ctx) return;
            if (this._charts[canvasId]) { this._charts[canvasId].destroy(); }
            this._charts[canvasId] = new Chart(ctx, {
                type: donut ? 'doughnut' : 'pie',
                data: { labels: labels, datasets: [{ data: data, backgroundColor: colors, borderWidth: 2, borderColor: 'transparent' }] },
                options: {
                    responsive: true, maintainAspectRatio: true,
                    plugins: { legend: { display: false } },
                    cutout: donut ? '55%' : 0,
                },
            });
            if (legendId) {
                var total = data.reduce(function (a, b) { return a + b; }, 0);
                var html = labels.map(function (lbl, i) {
                    var pct = total ? Math.round((data[i] / total) * 100) : 0;
                    return '<span class="pd-leg-item"><span class="pd-leg-dot" style="background:' + colors[i] + '"></span>' +
                        lbl + ' <b>' + data[i] + '</b> <small>(' + pct + '%)</small></span>';
                }).join('');
                self.$('#' + legendId).html(html);
            }
        },

        _renderDailyBar: function (daily) {
            var ctx = this.$('#pd-bar-daily')[0];
            if (!ctx) return;
            if (this._charts['pd-bar-daily']) { this._charts['pd-bar-daily'].destroy(); }
            this._charts['pd-bar-daily'] = new Chart(ctx, {
                type: 'bar',
                data: { labels: daily.map(function (d) { return d.label; }),
                        datasets: [{ label: 'Registrations', data: daily.map(function (d) { return d.count; }),
                            backgroundColor: BAR_COLOR, borderColor: BAR_BORDER, borderWidth: 1, borderRadius: 6 }] },
                options: this._barOpts(),
            });
        },

        _renderTierBar: function (tiers) {
            var ctx = this.$('#pd-bar-tier')[0];
            if (!ctx) return;
            if (this._charts['pd-bar-tier']) { this._charts['pd-bar-tier'].destroy(); }
            var colors = tiers.map(function (_, i) { return TIER_PALETTE[i % TIER_PALETTE.length]; });
            this._charts['pd-bar-tier'] = new Chart(ctx, {
                type: 'bar',
                data: { labels: tiers.map(function (t) { return t.label; }),
                        datasets: [{ label: 'Players', data: tiers.map(function (t) { return t.count; }),
                            backgroundColor: colors, borderWidth: 1, borderRadius: 6 }] },
                options: this._barOpts(),
            });
        },

        _renderTeamBar: function (teams) {
            var ctx = this.$('#pd-bar-team')[0];
            if (!ctx) return;
            if (this._charts['pd-bar-team']) { this._charts['pd-bar-team'].destroy(); }
            var colors = teams.map(function (_, i) { return TEAM_PALETTE[i % TEAM_PALETTE.length]; });
            this._charts['pd-bar-team'] = new Chart(ctx, {
                type: 'bar',
                data: { labels: teams.map(function (t) { return t.label; }),
                        datasets: [{ label: 'Players', data: teams.map(function (t) { return t.count; }),
                            backgroundColor: colors, borderWidth: 1, borderRadius: 6 }] },
                options: this._barOpts(),
            });
        },

        _barOpts: function () {
            var self = this;
            return {
                responsive: true, maintainAspectRatio: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { color: function () { return self._gridColor(); } },
                         ticks: { color: function () { return self._tickColor(); }, maxRotation: 35 } },
                    y: { beginAtZero: true,
                         grid: { color: function () { return self._gridColor(); } },
                         ticks: { color: function () { return self._tickColor(); }, stepSize: 1 } },
                },
            };
        },

        // ── Icon players table ───────────────────────────────────────────────
        _renderIconTable: function (players) {
            var rows = '';
            if (!players.length) {
                rows = '<tr><td colspan="7" class="pd-empty">No icon/key players assigned yet.</td></tr>';
            } else {
                players.forEach(function (p, i) {
                    var photo = p.photo_url
                        ? '<img src="' + p.photo_url + '" class="pd-tbl-photo" onerror="this.style.display=\'none\'">'
                        : '<span class="pd-tbl-photo-ph">&#11088;</span>';
                    var teamLogo = p.team_logo
                        ? '<img src="' + p.team_logo + '" class="pd-team-logo" onerror="this.style.display=\'none\'">'
                        : '';
                    var pts = p.points ? p.points.toLocaleString() : '&mdash;';
                    rows += '<tr>' +
                        '<td>' + (i + 1) + '</td>' +
                        '<td>' + photo + '</td>' +
                        '<td class="pd-tbl-name">' + (p.name || '') + '</td>' +
                        '<td><span class="pd-role-badge">' + (p.role || '&mdash;') + '</span></td>' +
                        '<td>' + (p.tier || '&mdash;') + '</td>' +
                        '<td class="pd-team-cell">' + teamLogo +
                            '<span class="pd-team-name">' + (p.team || 'Unassigned') + '</span></td>' +
                        '<td class="pd-pts">' + pts + '</td>' +
                        '</tr>';
                });
            }
            this.$('#pd-icon-tbody').html(rows);
        },

        // ── Draft table ──────────────────────────────────────────────────────
        _renderDraftTable: function (players) {
            var rows = '';
            if (!players.length) {
                rows = '<tr><td colspan="7" class="pd-empty">No draft players found.</td></tr>';
            } else {
                players.forEach(function (p, i) {
                    var photo = p.photo_url
                        ? '<img src="' + p.photo_url + '" class="pd-tbl-photo" onerror="this.style.display=\'none\'">'
                        : '<span class="pd-tbl-photo-ph">&#128100;</span>';
                    var bp = p.base_price ? p.base_price.toLocaleString() : '&mdash;';
                    rows += '<tr>' +
                        '<td>' + (i + 1) + '</td>' +
                        '<td>' + photo + '</td>' +
                        '<td class="pd-tbl-name">' + (p.name || '') + '</td>' +
                        '<td><span class="pd-role-badge">' + (p.role || '&mdash;') + '</span></td>' +
                        '<td>' + (p.tier || '&mdash;') + '</td>' +
                        '<td>' + bp + '</td>' +
                        '<td class="pd-date">' + (p.create_date || '') + '</td>' +
                        '</tr>';
                });
            }
            this.$('#pd-draft-tbody').html(rows);
        },

        // ── Stat card navigation ─────────────────────────────────────────────
        _onStatClick: function (ev) {
            var $card = $(ev.currentTarget);
            var key = null;
            var keys = Object.keys(this._STAT_ACTIONS);
            for (var i = 0; i < keys.length; i++) {
                if ($card.hasClass(keys[i])) { key = keys[i]; break; }
            }
            if (!key) return;
            var pair   = this._STAT_ACTIONS[key];
            var vids   = this._viewIds || {};
            var kanban = vids.kanban || false;
            var list   = vids.list   || false;
            this.do_action({
                type:      'ir.actions.act_window',
                name:       pair[0],
                res_model: 'auction.team.player',
                views:     [[kanban, 'kanban'], [list, 'list']],
                domain:     pair[1],
                target:    'current',
                context:   { create: false, edit: false },
            });
        },

        // ── Theme toggle ─────────────────────────────────────────────────────
        _onToggleTheme: function () {
            var isLight = this.$el.toggleClass('pd-light').hasClass('pd-light');
            localStorage.setItem('pd_theme', isLight ? 'light' : 'dark');
            this.$('.pd-theme-toggle').html(isLight ? '&#9728; Light' : '&#9790; Dark');
            var self = this;
            Object.keys(this._charts).forEach(function (k) {
                if (self._charts[k]) { self._charts[k].destroy(); self._charts[k] = null; }
            });
            this._loadData();
        },

        _onRefresh: function () { this._loadData(); },

        _fmt: function (n) {
            return (n !== null && n !== undefined) ? Number(n).toLocaleString() : '\u2014';
        },
    });

    core.action_registry.add('player_dashboard', PlayerDashboard);
    return PlayerDashboard;
});
