odoo.define('auction_module.AuctionDashboard', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var PIE_COLORS = ['#64b5f6', '#ffca28', '#66bb6a', '#ef5350'];
    var PIE_LABELS = ['Draft', 'In Auction', 'Sold', 'Unsold'];
    var PIE_KEYS   = ['draft', 'auction', 'sold', 'unsold'];

    var AuctionDashboard = AbstractAction.extend({
        events: {
            'click .ad-refresh-btn': '_onRefresh',
        },

        _chart: null,
        _timer: null,

        start: function () {
            this.$el.addClass('o_auction_dashboard');
            this.$el.html(this._buildLayout());
            var result = this._super.apply(this, arguments);
            this._loadData();
            var self = this;
            this._timer = setInterval(function () { self._loadData(); }, 30000);
            return result;
        },

        destroy: function () {
            if (this._timer) { clearInterval(this._timer); this._timer = null; }
            if (this._chart) { this._chart.destroy(); this._chart = null; }
            this._super.apply(this, arguments);
        },

        _buildLayout: function () {
            return [
                '<div class="ad-hdr">',
                    '<span class="ad-hdr-title" id="ad-title">Auction Dashboard</span>',
                    '<span class="ad-live-badge">&#9679; Live</span>',
                    '<button class="ad-refresh-btn">&#8635; Refresh</button>',
                '</div>',
                '<div class="ad-body">',
                    /* ── Left column 60%: stat cards + pie ── */
                    '<div class="ad-left">',
                        '<div class="ad-stat-cards">',
                            '<div class="ad-stat draft"><span class="ad-stat-num" id="ad-stat-draft">0</span><span class="ad-stat-lbl">Draft</span></div>',
                            '<div class="ad-stat auction"><span class="ad-stat-num" id="ad-stat-auction">0</span><span class="ad-stat-lbl">In Auction</span></div>',
                            '<div class="ad-stat sold"><span class="ad-stat-num" id="ad-stat-sold">0</span><span class="ad-stat-lbl">Sold</span></div>',
                            '<div class="ad-stat unsold"><span class="ad-stat-num" id="ad-stat-unsold">0</span><span class="ad-stat-lbl">Unsold</span></div>',
                        '</div>',
                        '<div class="ad-card ad-pie-card">',
                            '<div class="ad-card-title">Player Registration</div>',
                            '<div class="ad-pie-wrap"><canvas id="ad-pie-canvas" width="220" height="220"></canvas></div>',
                            '<div class="ad-legend" id="ad-legend"></div>',
                        '</div>',
                    '</div>',
                    /* ── Right column 40%: team table only ── */
                    '<div class="ad-right">',
                        '<div class="ad-card ad-table-card">',
                            '<div class="ad-card-title">Team Statistics</div>',
                            '<div class="ad-table-scroll">',
                                '<table class="ad-table">',
                                    '<thead><tr>',
                                        '<th>Team</th>',
                                        '<th>Owner</th>',
                                        '<th>Bought</th>',
                                        '<th>Slots Left</th>',
                                        '<th>Total Pts</th>',
                                        '<th>Spent</th>',
                                        '<th>Pts Left</th>',
                                        '<th>Max Call</th>',
                                    '</tr></thead>',
                                    '<tbody id="ad-table-body">',
                                        '<tr><td colspan="8" class="ad-no-data">Loading...</td></tr>',
                                    '</tbody>',
                                '</table>',
                            '</div>',
                        '</div>',
                    '</div>',
                '</div>',
                /* ── Bottom strip 100%: highest bid per team ── */
                '<div class="ad-card ad-bid-card-wrap">',
                    '<div class="ad-card-title">&#9733; Highest Bid Per Team</div>',
                    '<div class="ad-bid-scroll" id="ad-bid-cards"></div>',
                '</div>',
            ].join('');
        },

        _onRefresh: function () {
            this._loadData();
        },

        _loadData: function () {
            var self = this;
            fetch('/auction/dashboard/data', { cache: 'no-store' })
                .then(function (r) { return r.json(); })
                .then(function (data) { self._render(data); })
                .catch(function (e) { console.error('[AuctionDashboard]', e); });
        },

        _render: function (data) {
            var counts = data.player_counts || {};
            var teams  = data.teams || [];
            var tourn  = data.tournament || {};

            if (tourn.name) {
                var title = tourn.name;
                if (tourn.description) title += ' \u2014 ' + tourn.description;
                this.$('#ad-title').text(title);
            }

            // Stat number cards
            this.$('#ad-stat-draft').text(counts.draft || 0);
            this.$('#ad-stat-auction').text(counts.auction || 0);
            this.$('#ad-stat-sold').text(counts.sold || 0);
            this.$('#ad-stat-unsold').text(counts.unsold || 0);

            this._renderPie(counts);
            this._renderLegend(counts);
            this._renderTable(teams);
            this._renderBidCards(teams);
        },

        _renderPie: function (counts) {
            var ChartClass = window.Chart;
            if (!ChartClass) return;
            var data = PIE_KEYS.map(function (k) { return counts[k] || 0; });

            if (this._chart) {
                this._chart.data.datasets[0].data = data;
                this._chart.update();
                return;
            }

            var canvas = this.$('#ad-pie-canvas')[0];
            if (!canvas) return;

            this._chart = new ChartClass(canvas.getContext('2d'), {
                type: 'doughnut',
                data: {
                    labels: PIE_LABELS,
                    datasets: [{
                        data: data,
                        backgroundColor: PIE_COLORS,
                        borderWidth: 2,
                        borderColor: 'rgba(255,255,255,.15)',
                        hoverOffset: 6,
                    }],
                },
                options: {
                    cutout: '62%',
                    plugins: { legend: { display: false } },
                    animation: { duration: 700 },
                },
            });
        },

        _renderLegend: function (counts) {
            var total = PIE_KEYS.reduce(function (s, k) { return s + (counts[k] || 0); }, 0);
            var html = PIE_LABELS.map(function (lbl, i) {
                return '<div class="ad-legend-row">' +
                    '<span class="ad-dot" style="background:' + PIE_COLORS[i] + '"></span>' +
                    '<span>' + lbl + ': <b>' + (counts[PIE_KEYS[i]] || 0) + '</b></span>' +
                    '</div>';
            }).join('');
            html += '<div class="ad-legend-total">Total Players: <b>' + total + '</b></div>';
            this.$('#ad-legend').html(html);
        },

        _fmt: function (n) {
            return (n !== null && n !== undefined) ? Number(n).toLocaleString() : '\u2014';
        },

        _spent: function (team) {
            return (team.total_points || 0) - (team.remaining_points || 0);
        },

        _pct: function (team) {
            if (!team.total_points) return 0;
            return Math.min(100, Math.round(this._spent(team) / team.total_points * 100));
        },

        _barColor: function (team) {
            var p = team.total_points ? this._spent(team) / team.total_points : 0;
            if (p < 0.5) return '#66bb6a';
            if (p < 0.8) return '#ffca28';
            return '#ef5350';
        },

        _badgeClass: function (team) {
            var p = team.total_points ? (team.remaining_points || 0) / team.total_points : 1;
            if (p > 0.4)  return 'ad-badge ad-badge-g';
            if (p > 0.15) return 'ad-badge ad-badge-y';
            return 'ad-badge ad-badge-r';
        },

        _renderTable: function (teams) {
            var self = this;
            if (!teams.length) {
                this.$('#ad-table-body').html(
                    '<tr><td colspan="8" class="ad-no-data">No team data yet.</td></tr>'
                );
                return;
            }
            var rows = teams.map(function (team) {
                var logo = team.logo_url
                    ? '<img src="' + team.logo_url + '" class="ad-tbl-logo" onerror="this.style.display=\'none\'">'
                    : '<span class="ad-tbl-logo-ph">' + (team.name || 'T').charAt(0).toUpperCase() + '</span>';
                var spent   = self._spent(team);
                var pct     = self._pct(team);
                var barClr  = self._barColor(team);
                var bClass  = self._badgeClass(team);
                return '<tr>' +
                    '<td><div class="ad-team-cell">' + logo + '<span>' + (team.name || '') + '</span></div></td>' +
                    '<td>' + (team.manager || '\u2014') + '</td>' +
                    '<td class="ad-center">' + (team.players_bought || 0) + '</td>' +
                    '<td class="ad-center">' + (team.remaining_players || 0) + '</td>' +
                    '<td>' + self._fmt(team.total_points) + '</td>' +
                    '<td>' + self._fmt(spent) +
                        '<div class="ad-prog-wrap"><div class="ad-prog-bar" style="width:' + pct + '%;background:' + barClr + '"></div></div>' +
                    '</td>' +
                    '<td><span class="' + bClass + '">' + self._fmt(team.remaining_points) + '</span></td>' +
                    '<td class="ad-max-call">' + self._fmt(team.max_call) + '</td>' +
                    '</tr>';
            }).join('');
            this.$('#ad-table-body').html(rows);
        },

        _renderBidCards: function (teams) {
            var self = this;
            if (!teams.length) {
                this.$('#ad-bid-cards').html('<div class="ad-no-data">No team data yet.</div>');
                return;
            }
            var cards = teams.map(function (team) {
                var logo = team.logo_url
                    ? '<img src="' + team.logo_url + '" class="ad-bid-logo" onerror="this.style.display=\'none\'">'
                    : '<span class="ad-bid-logo-ph">' + (team.name || 'T').charAt(0).toUpperCase() + '</span>';
                var playerSection;
                if (team.top_player) {
                    var tp = team.top_player;
                    var photo = tp.photo_url
                        ? '<img src="' + tp.photo_url + '" class="ad-bid-photo" onerror="this.style.display=\'none\'">'
                        : '<span class="ad-bid-photo-ph">' + (tp.name || '?').charAt(0).toUpperCase() + '</span>';
                    playerSection =
                        '<div class="ad-bid-body">' +
                            photo +
                            '<div class="ad-bid-info">' +
                                '<div class="ad-bid-name">' + (tp.name || '') + '</div>' +
                                '<div class="ad-bid-role">' + (tp.role || '\u2014') + '</div>' +
                                '<div class="ad-bid-pts">' + self._fmt(tp.points) + ' pts</div>' +
                            '</div>' +
                        '</div>';
                } else {
                    playerSection = '<div class="ad-bid-empty">No players yet</div>';
                }
                return '<div class="ad-bid-card">' +
                    '<div class="ad-bid-hdr">' + logo +
                        '<span class="ad-bid-team-name">' + (team.name || '') + '</span>' +
                    '</div>' +
                    playerSection +
                    '</div>';
            }).join('');
            this.$('#ad-bid-cards').html(cards);
        },
    });

    core.action_registry.add('auction_dashboard', AuctionDashboard);

    return AuctionDashboard;
});
