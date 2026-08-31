odoo.define('auction_module.AuctionHistoryBoard', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var PAGE_SIZE = 80;

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    var AuctionHistoryBoard = AbstractAction.extend({
        className: 'o_ah_board_action',
        hasControlPanel: false,
        events: {
            'click .o_ah_refresh': '_onRefresh',
            'click .o_ah_back': '_onBack',
            'input .o_ah_search': '_onSearchInput',
            'keydown .o_ah_search': '_onSearchKey',
            'click .o_ah_search_clear': '_onSearchClear',
            'click .o_ah_prev': '_onPrev',
            'click .o_ah_next': '_onNext',
            'click .o_ah_page_btn': '_onPageBtn',
            'click .o_ah_filter': '_onFilter',
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var ctx = (action && action.context) || {};
            var params = (action && action.params) || {};
            this.tournamentId = params.tournament_id || ctx.tournament_id || false;
            this.page = 1;
            this.pageSize = PAGE_SIZE;
            this.search = '';
            this.filter = 'all'; // all | sold | unsold | other
            this.data = null;
            this._searchTmr = null;
            this._allRecordsCache = null; // only when filtering client-side beyond server search
        },

        start: function () {
            var self = this;
            this.$el.addClass('o_ah_board_action');
            var result = this._super.apply(this, arguments);
            this.$el.html(this._shellHtml());
            return Promise.resolve(result).then(function () {
                return self._load();
            });
        },

        destroy: function () {
            if (this._searchTmr) {
                clearTimeout(this._searchTmr);
            }
            this._super.apply(this, arguments);
        },

        _shellHtml: function () {
            return [
                '<div class="o_ah_app">',
                '  <header class="o_ah_hdr">',
                '    <div class="o_ah_hdr_left">',
                '      <button type="button" class="o_ah_btn o_ah_btn_ghost o_ah_back" title="Back to tournament">&#8592;</button>',
                '      <div class="o_ah_logo_ph" aria-hidden="true">AH</div>',
                '      <div class="o_ah_hdr_text">',
                '        <div class="o_ah_kicker">Auction History</div>',
                '        <div class="o_ah_title" id="o_ah_title">Loading\u2026</div>',
                '        <div class="o_ah_sub" id="o_ah_sub"></div>',
                '      </div>',
                '    </div>',
                '    <div class="o_ah_hdr_actions">',
                '      <button type="button" class="o_ah_btn o_ah_btn_gold o_ah_refresh" title="Refresh">',
                '        <span class="o_ah_btn_ico">&#8635;</span>',
                '        <span class="o_ah_btn_lbl">Refresh</span>',
                '      </button>',
                '    </div>',
                '  </header>',
                '  <div class="o_ah_toolbar">',
                '    <div class="o_ah_search_wrap">',
                '      <input type="search" class="o_ah_search" placeholder="Search player, team, serial\u2026" enterkeyhint="search"/>',
                '      <button type="button" class="o_ah_search_clear" title="Clear">&#10005;</button>',
                '    </div>',
                '    <div class="o_ah_filters" id="o_ah_filters">',
                '      <button type="button" class="o_ah_filter active" data-filter="all">All</button>',
                '      <button type="button" class="o_ah_filter" data-filter="sold">Sold</button>',
                '      <button type="button" class="o_ah_filter" data-filter="unsold">Unsold</button>',
                '      <button type="button" class="o_ah_filter" data-filter="other">Other</button>',
                '    </div>',
                '  </div>',
                '  <div class="o_ah_body" id="o_ah_body">',
                '    <div class="o_ah_loading">Loading auction history\u2026</div>',
                '  </div>',
                '  <footer class="o_ah_pager" id="o_ah_pager"></footer>',
                '</div>',
            ].join('');
        },

        _load: function () {
            var self = this;
            if (!this.tournamentId) {
                this.$('#o_ah_body').html(
                    '<div class="o_ah_empty"><strong>No tournament selected</strong>' +
                    '<p>Open Auction History from a tournament form.</p></div>'
                );
                return Promise.resolve();
            }
            this.$('#o_ah_body').html('<div class="o_ah_loading">Loading auction history\u2026</div>');
            return this._rpc({
                model: 'auction.history',
                method: 'get_history_board',
                args: [this.tournamentId, this.page, this.pageSize, this.search, this.filter],
            }).then(function (data) {
                self.data = data || {};
                self.page = data.page || 1;
                self._render();
            }).guardedCatch(function (err) {
                console.error('Auction history load failed', err);
                self.$('#o_ah_body').html(
                    '<div class="o_ah_empty"><strong>Could not load history</strong>' +
                    '<p>Check server logs and try Refresh.</p></div>'
                );
            });
        },

        _visibleRecords: function () {
            return (this.data && this.data.records) || [];
        },

        _render: function () {
            var d = this.data || {};
            this.$('#o_ah_title').text(d.tournament_name || 'Auction History');
            var total = d.total || 0;
            this.$('#o_ah_sub').text(
                total
                    ? (d.start + '\u2013' + d.end + ' of ' + total)
                    : 'No auction events yet'
            );

            this.$('.o_ah_filter').removeClass('active');
            this.$('.o_ah_filter[data-filter="' + this.filter + '"]').addClass('active');

            var rows = this._visibleRecords();
            if (!rows.length) {
                this.$('#o_ah_body').html(
                    '<div class="o_ah_empty">' +
                    '<strong>No matching events</strong>' +
                    '<p>Try another filter or clear the search.</p></div>'
                );
            } else {
                this.$('#o_ah_body').html(
                    '<div class="o_ah_list">' + rows.map(this._rowHtml.bind(this)).join('') + '</div>'
                );
            }
            this._renderPager();
        },

        _rowHtml: function (r) {
            var event = r.event || 'other';
            var badge = {
                sold: 'SOLD',
                unsold: 'UNSOLD',
                other: 'UPDATE',
            }[event] || 'EVENT';

            var photo = r.photo_url
                ? '<img class="o_ah_photo" src="' + esc(r.photo_url) + '" alt=""/>'
                : '<div class="o_ah_photo o_ah_photo_ph">&#9787;</div>';

            var sl = r.sl_no
                ? '<span class="o_ah_sl">#' + esc(r.sl_no) + '</span>'
                : '';

            var teamBlock = '';
            if (event === 'sold' && (r.team_name || r.team_logo_url)) {
                var logo = r.team_logo_url
                    ? '<img class="o_ah_team_logo" src="' + esc(r.team_logo_url) + '" alt=""/>'
                    : '<div class="o_ah_team_logo o_ah_team_logo_ph">&#9917;</div>';
                var price = r.points_display
                    ? '<span class="o_ah_price">' + esc(r.points_display) + '</span>'
                    : '';
                teamBlock = [
                    '<div class="o_ah_team">',
                    '  <span class="o_ah_team_lbl">Sold to</span>',
                    '  <div class="o_ah_team_row">',
                    logo,
                    '    <div class="o_ah_team_meta">',
                    '      <div class="o_ah_team_name">' + esc(r.team_name || '—') + '</div>',
                    price,
                    '    </div>',
                    '  </div>',
                    '</div>',
                ].join('');
            } else if (event === 'unsold') {
                teamBlock = '<div class="o_ah_team o_ah_team_unsold"><span class="o_ah_team_lbl">Result</span>' +
                    '<div class="o_ah_team_name">Unsold</div></div>';
            } else if (r.message) {
                teamBlock = '<div class="o_ah_msg">' + esc(r.message) + '</div>';
            }

            return [
                '<article class="o_ah_row o_ah_row_' + esc(event) + '">',
                '  <div class="o_ah_rail"><span class="o_ah_dot"></span></div>',
                '  <div class="o_ah_card">',
                '    <div class="o_ah_card_main">',
                '      <div class="o_ah_player">',
                photo,
                '        <div class="o_ah_player_meta">',
                '          <div class="o_ah_player_top">' + sl +
                '            <span class="o_ah_badge o_ah_badge_' + esc(event) + '">' + badge + '</span>',
                '          </div>',
                '          <div class="o_ah_player_name">' + esc(r.player_name || 'Unknown player') + '</div>',
                '        </div>',
                '      </div>',
                '      <div class="o_ah_mid">' + teamBlock + '</div>',
                '    </div>',
                '    <div class="o_ah_time">',
                '      <div class="o_ah_date">' + esc(r.date_label || '') + '</div>',
                '      <div class="o_ah_clock">' + esc(r.timestamp_short || '') + '</div>',
                '    </div>',
                '  </div>',
                '</article>',
            ].join('');
        },

        _renderPager: function () {
            var d = this.data || {};
            var total = d.total || 0;
            var pages = d.total_pages || 1;
            var page = d.page || 1;
            if (!total) {
                this.$('#o_ah_pager').html('');
                return;
            }

            var buttons = this._pageButtons(page, pages);
            var html = [
                '<div class="o_ah_pager_inner">',
                '  <div class="o_ah_pager_info">' +
                    esc(d.start) + '\u2013' + esc(d.end) + ' / ' + esc(total) +
                '  </div>',
                '  <div class="o_ah_pager_nav">',
                '    <button type="button" class="o_ah_prev" aria-label="Previous page"' +
                    (page <= 1 ? ' disabled' : '') + '>&#8249; Previous</button>',
                buttons,
                '    <button type="button" class="o_ah_next" aria-label="Next page"' +
                    (page >= pages ? ' disabled' : '') + '>Next &#8250;</button>',
                '  </div>',
                '</div>',
            ].join('');
            this.$('#o_ah_pager').html(html);
            this._scrollPagerToActive();
        },

        _scrollPagerToActive: function () {
            var $nav = this.$('.o_ah_pager_nav');
            var $active = $nav.find('.o_ah_page_btn.active');
            if (!$nav.length || !$active.length) {
                return;
            }
            var navEl = $nav[0];
            var btnEl = $active[0];
            var target = btnEl.offsetLeft - (navEl.clientWidth / 2) + (btnEl.offsetWidth / 2);
            navEl.scrollLeft = Math.max(0, target);
        },

        _pageButtons: function (page, pages) {
            // Show a compact window of page numbers around current (like Odoo list)
            var start = Math.max(1, page - 2);
            var end = Math.min(pages, page + 2);
            if (end - start < 4) {
                start = Math.max(1, end - 4);
                end = Math.min(pages, start + 4);
            }
            var parts = [];
            if (start > 1) {
                parts.push(this._pageBtn(1, page));
                if (start > 2) {
                    parts.push('<span class="o_ah_ellipsis">\u2026</span>');
                }
            }
            for (var i = start; i <= end; i++) {
                parts.push(this._pageBtn(i, page));
            }
            if (end < pages) {
                if (end < pages - 1) {
                    parts.push('<span class="o_ah_ellipsis">\u2026</span>');
                }
                parts.push(this._pageBtn(pages, page));
            }
            return parts.join('');
        },

        _pageBtn: function (n, current) {
            return '<button type="button" class="o_ah_page_btn' +
                (n === current ? ' active' : '') +
                '" data-page="' + n + '">' + n + '</button>';
        },

        _onRefresh: function () {
            this._load();
        },

        _onBack: function () {
            if (this.tournamentId) {
                this.do_action({
                    type: 'ir.actions.act_window',
                    res_model: 'auction.tournament',
                    res_id: this.tournamentId,
                    views: [[false, 'form']],
                    target: 'current',
                });
            } else {
                this.do_action({'type': 'ir.actions.act_window_close'});
            }
        },

        _onSearchInput: function () {
            var self = this;
            if (this._searchTmr) {
                clearTimeout(this._searchTmr);
            }
            this._searchTmr = setTimeout(function () {
                self.search = (self.$('.o_ah_search').val() || '').trim();
                self.page = 1;
                self._load();
            }, 280);
        },

        _onSearchKey: function (ev) {
            if (ev.key === 'Enter') {
                if (this._searchTmr) {
                    clearTimeout(this._searchTmr);
                }
                this.search = (this.$('.o_ah_search').val() || '').trim();
                this.page = 1;
                this._load();
            }
        },

        _onSearchClear: function () {
            this.$('.o_ah_search').val('');
            this.search = '';
            this.page = 1;
            this._load();
        },

        _onPrev: function () {
            if (this.page <= 1) {
                return;
            }
            this.page -= 1;
            this._load();
        },

        _onNext: function () {
            var pages = (this.data && this.data.total_pages) || 1;
            if (this.page >= pages) {
                return;
            }
            this.page += 1;
            this._load();
        },

        _onPageBtn: function (ev) {
            var p = parseInt(this.$(ev.currentTarget).data('page'), 10);
            if (!p || p === this.page) {
                return;
            }
            this.page = p;
            this._load();
        },

        _onFilter: function (ev) {
            var f = this.$(ev.currentTarget).data('filter') || 'all';
            if (f === this.filter) {
                return;
            }
            this.filter = f;
            this.page = 1;
            this._load();
        },
    });

    core.action_registry.add('auction_module.auction_history_board', AuctionHistoryBoard);
    return AuctionHistoryBoard;
});
