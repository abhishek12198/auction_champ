odoo.define('auction_module.PaymentMarker', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function dash(v) {
        return v ? esc(v) : '<span class="o_pm_muted">—</span>';
    }

    function telHref(contact) {
        var s = String(contact || '').replace(/[^\d+]/g, '');
        return s ? 'tel:' + s : '';
    }

    var PaymentMarker = AbstractAction.extend({
        className: 'o_payment_marker_action',
        // Avoid Odoo control-panel breadcrumb (white text) sitting on a light strip.
        hasControlPanel: false,
        events: {
            'click .o_pm_refresh': '_onRefresh',
            'click .o_pm_theme': '_onToggleTheme',
            'click .o_pm_expand': '_onToggleExpand',
            'input .o_pm_search': '_onSearch',
            'keyup .o_pm_search': '_onSearch',
            'search .o_pm_search': '_onSearch',
            'change .o_pm_search': '_onSearch',
            'compositionend .o_pm_search': '_onSearch',
            'keydown .o_pm_search': '_onSearchKeydown',
            'click .o_pm_tab': '_onTab',
            'change .o_pm_pay_filter': '_onPayFilter',
            'change .o_pm_group_by': '_onGroupBy',
            'change .o_pm_sort_by': '_onSortBy',
            'change .o_pm_tournament': '_onTournamentChange',
            'click .o_pm_dir_btn': '_onSortDir',
            'click .o_pm_team_chip': '_onTeamChip',
            'click .o_pm_pay_btn': '_onTogglePay',
            'click .o_pm_upload_btn': '_onUploadClick',
            'change .o_pm_proof_file': '_onUploadFile',
            'click .o_pm_unlink_btn': '_onUnlinkProof',
            'click .o_pm_proof_btn': '_onOpenProof',
            'click .o_pm_lb_close, .o_pm_lb': '_onCloseProof',
            'click .o_pm_export_btn': '_onExportToggle',
            'click .o_pm_export_xls': '_onExportXls',
            'click .o_pm_export_pdf': '_onExportPdf',
            'click .o_pm_prev': '_onPrevPage',
            'click .o_pm_next': '_onNextPage',
            'click th.sortable': '_onThSort',
            'click .o_pm_reveal_btn': '_onRevealContact',
            'click .o_pm_hide_btn': '_onHideContact',
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var ctx = (action && action.context) || {};
            var params = (action && action.params) || {};
            this.tournamentId = params.tournament_id || ctx.tournament_id || false;
            this.players = [];
            this.teams = [];
            this.tournaments = [];
            this.urls = {};
            this.tournament = {};
            this.showTournamentFilter = false;
            this.isSaas = false;
            this.expanded = localStorage.getItem('pm-expanded') === '1';
            this.revealedContacts = {};
            this.S = {
                stateFilter: 'all',
                payFilter: 'all',
                teamFilter: '',
                groupBy: 'none',
                sortField: 'sl_no',
                sortDir: 'asc',
                search: '',
                page: 1,
                pageSize: 40,
            };
            this._searchTmr = null;
            this._uploadPid = null;
        },

        start: function () {
            var self = this;
            // Explicit class — AbstractAction className alone is unreliable in this shell.
            this.$el.addClass('o_payment_marker_action');
            var result = this._super.apply(this, arguments);
            this.$el.html(this._shellHtml());
            if (localStorage.getItem('pm-theme') === 'dark') {
                this.$el.addClass('o_pm_dark');
                this.$('.o_pm_app').addClass('o_pm_dark');
            }
            this._syncExpandUi(this.expanded);
            return Promise.resolve(result).then(function () {
                return self._loadData();
            });
        },

        destroy: function () {
            document.body.classList.remove('o_pm_sidebar_collapsed');
            this._super.apply(this, arguments);
        },

        _syncExpandUi: function (on) {
            this.expanded = !!on;
            document.body.classList.toggle('o_pm_sidebar_collapsed', this.expanded);
            localStorage.setItem('pm-expanded', this.expanded ? '1' : '0');
            this.$el.toggleClass('o_pm_expanded', this.expanded);
            // Never replace button HTML — only update label/title.
            this.$('.o_pm_expand').attr(
                'title',
                this.expanded ? 'Exit expanded view' : 'Expand (collapse left menu)'
            );
            this.$('.o_pm_expand_lbl').text(this.expanded ? 'Collapse' : 'Expand');
        },

        _applyExpand: function (on) {
            this._syncExpandUi(on);
        },

        _shellHtml: function () {
            return [
                '<div class="o_pm_app">',
                '  <header class="o_pm_header">',
                '    <div class="o_pm_header_left">',
                '      <div class="o_pm_nav_logo_fb" id="o_pm_logo">AC</div>',
                '      <div class="o_pm_header_text">',
                '        <div class="o_pm_kicker">Payment Tracker</div>',
                '        <div class="o_pm_title" id="o_pm_tourn">Loading…</div>',
                '      </div>',
                '    </div>',
                '    <div class="o_pm_header_actions">',
                '      <button type="button" class="o_pm_btn o_pm_btn_gold o_pm_expand" title="Expand">',
                '        <span class="o_pm_btn_ico">⛶</span>',
                '        <span class="o_pm_expand_lbl">Expand</span>',
                '      </button>',
                '      <button type="button" class="o_pm_btn o_pm_btn_ghost o_pm_theme" title="Theme">',
                '        <span class="o_pm_theme_lbl">☀️ Light</span>',
                '      </button>',
                '      <button type="button" class="o_pm_btn o_pm_btn_primary o_pm_refresh" title="Refresh">',
                '        <span class="o_pm_btn_ico">↻</span>',
                '        <span class="o_pm_refresh_lbl">Refresh</span>',
                '      </button>',
                '      <div class="o_pm_export_wrap">',
                '        <button type="button" class="o_pm_btn o_pm_btn_ghost o_pm_export_btn" title="Export">',
                '          <span class="o_pm_btn_ico">↓</span>',
                '          <span class="o_pm_export_lbl">Export</span>',
                '          <span class="o_pm_btn_caret">▾</span>',
                '        </button>',
                '        <div class="o_pm_export_menu">',
                '          <div class="o_pm_export_item o_pm_export_xls">Excel (.xls)</div>',
                '          <div class="o_pm_export_item o_pm_export_pdf">PDF</div>',
                '        </div>',
                '      </div>',
                '    </div>',
                '  </header>',

                '  <section class="o_pm_stats">',
                '    <div class="o_pm_stat"><span class="o_pm_stat_num" id="o_pm_total">0</span><span class="o_pm_stat_lbl">Total</span></div>',
                '    <div class="o_pm_progress"><div class="o_pm_progress_bar" id="o_pm_bar"></div></div>',
                '    <div class="o_pm_stat o_pm_paid"><span class="o_pm_stat_num" id="o_pm_paid">0</span><span class="o_pm_stat_lbl">Paid</span></div>',
                '    <div class="o_pm_stat o_pm_unpaid"><span class="o_pm_stat_num" id="o_pm_unpaid">0</span><span class="o_pm_stat_lbl">Unpaid</span></div>',
                '    <div class="o_pm_state_chips" id="o_pm_state_chips"></div>',
                '  </section>',

                '  <section class="o_pm_filters_panel">',
                '    <div class="o_pm_filter_row o_pm_filter_primary">',
                '      <div class="o_pm_field o_pm_field_tourn" id="o_pm_tourn_wrap" style="display:none">',
                '        <label>Tournament</label>',
                '        <select class="o_pm_tournament"></select>',
                '      </div>',
                '      <div class="o_pm_field o_pm_field_search">',
                '        <label>Search</label>',
                '        <input type="text" class="o_pm_search" placeholder="Name, serial, team, manager, contact…" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false" enterkeyhint="search"/>',
                '      </div>',
                '      <div class="o_pm_field">',
                '        <label>Payment</label>',
                '        <select class="o_pm_pay_filter">',
                '          <option value="all">All</option>',
                '          <option value="paid">Paid</option>',
                '          <option value="unpaid">Unpaid</option>',
                '        </select>',
                '      </div>',
                '      <div class="o_pm_field">',
                '        <label>Group</label>',
                '        <select class="o_pm_group_by">',
                '          <option value="none">None</option>',
                '          <option value="state">State</option>',
                '          <option value="team">Team</option>',
                '          <option value="payment">Payment</option>',
                '          <option value="tier">Tier</option>',
                '        </select>',
                '      </div>',
                '      <div class="o_pm_field o_pm_field_sort">',
                '        <label>Sort</label>',
                '        <div class="o_pm_sort_pair">',
                '          <select class="o_pm_sort_by">',
                '            <option value="sl_no">Sl No</option>',
                '            <option value="name">Name</option>',
                '            <option value="contact">Contact</option>',
                '            <option value="amount_paid">Payment</option>',
                '            <option value="team">Team</option>',
                '            <option value="manager">Manager</option>',
                '            <option value="state">State</option>',
                '            <option value="tier">Tier</option>',
                '          </select>',
                '          <button type="button" class="o_pm_dir_btn" title="Direction">↑</button>',
                '        </div>',
                '      </div>',
                '    </div>',
                '    <div class="o_pm_filter_row o_pm_filter_secondary">',
                '      <div class="o_pm_tabs">',
                '        <button type="button" class="o_pm_tab active" data-state="all">All</button>',
                '        <button type="button" class="o_pm_tab" data-state="draft">Draft</button>',
                '        <button type="button" class="o_pm_tab" data-state="auction">In Auction</button>',
                '        <button type="button" class="o_pm_tab" data-state="sold">Sold</button>',
                '        <button type="button" class="o_pm_tab" data-state="unsold">Unsold</button>',
                '      </div>',
                '      <div class="o_pm_team_chips" id="o_pm_team_chips" style="display:none"></div>',
                '    </div>',
                '  </section>',

                '  <section class="o_pm_content">',
                '    <div class="o_pm_table_wrap">',
                '      <table class="o_pm_table">',
                '        <thead><tr>',
                '          <th class="sortable" data-sort="sl_no">#</th>',
                '          <th>Player</th>',
                '          <th class="sortable" data-sort="contact">Contact</th>',
                '          <th class="sortable" data-sort="amount_paid">Payment</th>',
                '          <th class="sortable" data-sort="team">Team</th>',
                '          <th class="sortable" data-sort="manager">Manager</th>',
                '          <th class="sortable" data-sort="state">State</th>',
                '          <th>Proof</th>',
                '        </tr></thead>',
                '        <tbody id="o_pm_tbody"></tbody>',
                '      </table>',
                '    </div>',
                '    <div class="o_pm_cards" id="o_pm_cards"></div>',
                '    <div class="o_pm_empty" id="o_pm_empty" style="display:none">No players match the current filters.</div>',
                '  </section>',

                '  <footer class="o_pm_footer">',
                '    <span class="o_pm_count" id="o_pm_count">0 players</span>',
                '    <span class="o_pm_page_info" id="o_pm_page_info"></span>',
                '    <div class="o_pm_pager">',
                '      <button type="button" class="o_pm_btn o_pm_btn_ghost o_pm_prev">‹ Prev</button>',
                '      <span id="o_pm_page_lbl">1</span>',
                '      <button type="button" class="o_pm_btn o_pm_btn_ghost o_pm_next">Next ›</button>',
                '    </div>',
                '  </footer>',

                '  <div class="o_pm_toast" id="o_pm_toast"></div>',
                '  <input type="file" class="o_pm_proof_file" accept="image/*" style="display:none"/>',
                '  <div class="o_pm_lb" id="o_pm_lb" style="display:none">',
                '    <div class="o_pm_lb_box">',
                '      <div class="o_pm_lb_head"><span id="o_pm_lb_title">Payment Proof</span>',
                '        <button type="button" class="o_pm_lb_close">✕</button></div>',
                '      <div class="o_pm_lb_body" id="o_pm_lb_body"></div>',
                '    </div>',
                '  </div>',
                '</div>',
            ].join('');
        },

        _loadData: function () {
            var self = this;
            this.$('#o_pm_tourn').text('Loading…');
            return this._rpc({
                route: '/auction/payment-marker/data',
                params: {tournament_id: this.tournamentId || null},
            }).then(function (res) {
                if (!res || !res.ok) {
                    self.$el.html(
                        '<div class="o_pm_error"><h3>Payment Tracker</h3><p>' +
                        esc((res && res.error) || 'Unable to load data.') +
                        '</p></div>'
                    );
                    return;
                }
                self.players = res.players || [];
                self.teams = res.teams || [];
                self.urls = res.urls || {};
                self.tournament = res.tournament || {};
                self.tournaments = res.tournaments || [];
                self.showTournamentFilter = !!res.show_tournament_filter;
                self.isSaas = !!res.is_saas;
                self.S.pageSize = res.page_size || 40;
                self.tournamentId = self.tournament.id || self.tournamentId;
                self._paintHeader();
                self._paintTournamentFilter();
                self._paintTeamChips();
                self._applyExpand(self.expanded);
                self._render(true);
            }).guardedCatch(function () {
                self.$el.html(
                    '<div class="o_pm_error"><h3>Payment Tracker</h3>' +
                    '<p>Network error while loading Payment Tracker.</p></div>'
                );
            });
        },

        _paintHeader: function () {
            var t = this.tournament;
            this.$('#o_pm_tourn').text(t.name || 'Tournament');
            var $logo = this.$('#o_pm_logo');
            var logoAttrs =
                ' class="o_pm_nav_logo" id="o_pm_logo" width="42" height="42"' +
                ' style="width:42px;height:42px;max-width:42px;max-height:42px;' +
                'object-fit:cover;border-radius:8px;display:block;flex-shrink:0;"';
            if (t.logo_url && $logo.length && !$logo.is('img')) {
                $logo.replaceWith(
                    '<img' + logoAttrs + ' src="' + esc(t.logo_url) + '" alt=""/>'
                );
            } else if (t.logo_url && $logo.is('img')) {
                $logo.attr('src', t.logo_url);
            }
            this.$('.o_pm_theme_lbl').text(
                this.$el.hasClass('o_pm_dark') ? '🌙 Dark' : '☀️ Light'
            );
        },

        _paintTournamentFilter: function () {
            var $wrap = this.$('#o_pm_tourn_wrap');
            var $sel = this.$('.o_pm_tournament');
            if (!this.showTournamentFilter || !this.tournaments.length) {
                $wrap.hide();
                return;
            }
            var tid = this.tournamentId;
            var html = this.tournaments.map(function (t) {
                return '<option value="' + t.id + '"' +
                    (String(t.id) === String(tid) ? ' selected' : '') + '>' +
                    esc(t.name) + '</option>';
            }).join('');
            $sel.html(html);
            $wrap.show();
        },

        _paintTeamChips: function () {
            var $wrap = this.$('#o_pm_team_chips');
            if (!this.teams.length) {
                $wrap.hide().empty();
                return;
            }
            var html = ['<button type="button" class="o_pm_team_chip active" data-team="">All Teams</button>'];
            this.teams.forEach(function (t) {
                var logo = t.has_logo
                    ? '<img class="o_pm_chip_logo" src="/web/image/auction.team/' + t.id + '/logo" alt=""/>'
                    : '<span class="o_pm_chip_fb">' + esc((t.name || '?').slice(0, 2)) + '</span>';
                html.push(
                    '<button type="button" class="o_pm_team_chip" data-team="' + esc(t.name) + '">' +
                    logo + '<span>' + esc(t.name) + '</span></button>'
                );
            });
            $wrap.html(html.join('')).show();
        },

        _getFiltered: function () {
            var S = this.S;
            var q = (S.search || '').toLowerCase();
            var rows = this.players.slice();
            if (S.stateFilter !== 'all') {
                rows = rows.filter(function (p) { return p.state === S.stateFilter; });
            }
            if (S.payFilter === 'paid') {
                rows = rows.filter(function (p) { return p.amount_paid; });
            }
            if (S.payFilter === 'unpaid') {
                rows = rows.filter(function (p) { return !p.amount_paid; });
            }
            if (S.teamFilter) {
                rows = rows.filter(function (p) { return p.team === S.teamFilter; });
            }
            if (q) {
                var digitsOnly = /^\d+$/.test(q);
                if (digitsOnly && q.length <= 3) {
                    // Prefer serial-number matches for short digit queries
                    var serialHits = rows.filter(function (p) {
                        return String(p.sl_no == null ? '' : p.sl_no).indexOf(q) !== -1;
                    });
                    if (serialHits.length) {
                        rows = serialHits;
                    } else {
                        // No serial match → fall back to full search
                        rows = rows.filter(function (p) {
                            return [
                                p.name, p.sl_no, p.team, p.manager, p.contact,
                                p.masked_contact, p.tier, p.role, p.state, p.state_label,
                            ].join(' ').toLowerCase().indexOf(q) !== -1;
                        });
                    }
                } else {
                    rows = rows.filter(function (p) {
                        return [
                            p.name, p.sl_no, p.team, p.manager, p.contact,
                            p.masked_contact, p.tier, p.role, p.state, p.state_label,
                        ].join(' ').toLowerCase().indexOf(q) !== -1;
                    });
                }
            }
            var field = S.sortField;
            var dir = S.sortDir === 'asc' ? 1 : -1;
            rows.sort(function (a, b) {
                var av = a[field];
                var bv = b[field];
                if (field === 'amount_paid') {
                    av = a.amount_paid ? 1 : 0;
                    bv = b.amount_paid ? 1 : 0;
                }
                if (av == null) av = '';
                if (bv == null) bv = '';
                if (av < bv) return -1 * dir;
                if (av > bv) return 1 * dir;
                return 0;
            });
            return rows;
        },

        _renderStats: function (rows) {
            var total = this.players.length;
            var paid = this.players.filter(function (p) { return p.amount_paid; }).length;
            this.$('#o_pm_total').text(total);
            this.$('#o_pm_paid').text(paid);
            this.$('#o_pm_unpaid').text(total - paid);
            var pct = total ? Math.round((paid / total) * 100) : 0;
            this.$('#o_pm_bar').css('width', pct + '%');
            var by = {draft: [0, 0], auction: [0, 0], sold: [0, 0], unsold: [0, 0]};
            this.players.forEach(function (p) {
                if (!by[p.state]) return;
                by[p.state][0] += 1;
                if (p.amount_paid) by[p.state][1] += 1;
            });
            this.$('#o_pm_state_chips').html([
                '<span class="o_pm_ss draft">Draft ' + by.draft[1] + '/' + by.draft[0] + '</span>',
                '<span class="o_pm_ss auction">Auction ' + by.auction[1] + '/' + by.auction[0] + '</span>',
                '<span class="o_pm_ss sold">Sold ' + by.sold[1] + '/' + by.sold[0] + '</span>',
                '<span class="o_pm_ss unsold">Unsold ' + by.unsold[1] + '/' + by.unsold[0] + '</span>',
            ].join(''));
            this.$('#o_pm_count').text(rows.length + ' match' + (rows.length === 1 ? '' : 'es') +
                ' · ' + total + ' total');
        },

        _badge: function (st) {
            var map = {draft: 'Draft', auction: 'In Auction', sold: 'Sold', unsold: 'Unsold'};
            return '<span class="o_pm_badge o_pm_badge_' + esc(st) + '">' + esc(map[st] || st) + '</span>';
        },

        _proofBtns: function (p, labeled) {
            var proofBtns = '';
            if (p.proof_att_id) {
                proofBtns +=
                    '<button type="button" class="o_pm_icon_act o_pm_proof_btn" data-id="' + p.id +
                    '" data-name="' + esc(p.name) + '" title="View proof">🧾' +
                    (labeled ? ' View' : '') + '</button>' +
                    '<button type="button" class="o_pm_icon_act o_pm_unlink_btn" data-id="' + p.id +
                    '" title="Remove proof">🗑</button>';
            }
            proofBtns +=
                '<button type="button" class="o_pm_icon_act o_pm_upload_btn" data-id="' + p.id +
                '" title="Upload proof">📤' + (labeled ? ' Upload' : '') + '</button>';
            return proofBtns;
        },

        _rowHtml: function (p, idx) {
            var paid = p.amount_paid ? '1' : '0';
            var proofBtns = this._proofBtns(p, false);
            return [
                '<tr>',
                '<td class="o_pm_col_sl">' + (p.sl_no || idx + 1) + '</td>',
                '<td><div class="o_pm_player"><img src="/web/image/auction.team.player/' + p.id +
                    '/photo" onerror="this.src=\'/auction_module/static/img/default_icon.png\'" alt=""/>',
                '<div><div class="o_pm_pname">' + esc(p.name) + '</div>',
                (p.role ? '<div class="o_pm_prole">' + esc(p.role) + '</div>' : ''),
                '</div></div></td>',
                '<td>' + esc(p.masked_contact || p.contact || '') + '</td>',
                '<td><button type="button" class="o_pm_pay_btn ' + (p.amount_paid ? 'is-paid' : 'is-unpaid') +
                    '" data-id="' + p.id + '" data-paid="' + paid + '">' +
                    (p.amount_paid ? '✓ Paid' : '✗ Unpaid') + '</button></td>',
                '<td>' + dash(p.team) + '</td>',
                '<td>' + dash(p.manager) + '</td>',
                '<td>' + this._badge(p.state) + '</td>',
                '<td class="o_pm_proof_cell">' + proofBtns + '</td>',
                '</tr>',
            ].join('');
        },

        _cardContactHtml: function (p) {
            var contact = p.contact || '';
            var masked = p.masked_contact || contact || '—';
            if (!contact) {
                return [
                    '<div class="o_pm_card_field o_pm_card_contact">',
                    '  <span class="o_pm_card_lbl">Contact</span>',
                    '  <span class="o_pm_card_val o_pm_muted">—</span>',
                    '</div>',
                ].join('');
            }
            var revealed = !!this.revealedContacts[p.id];
            var display = revealed ? contact : masked;
            var call = telHref(contact);
            var actions = revealed
                ? [
                    '<a class="o_pm_call_btn" href="' + esc(call) + '" title="Call" aria-label="Call">📞</a>',
                    '<button type="button" class="o_pm_hide_btn" data-id="' + p.id + '" title="Hide number" aria-label="Hide number">🙈</button>',
                ].join('')
                : '<button type="button" class="o_pm_reveal_btn" data-id="' + p.id + '" title="Show number" aria-label="Show number">👁</button>';
            return [
                '<div class="o_pm_card_field o_pm_card_contact' + (revealed ? ' is-revealed' : '') + '">',
                '  <span class="o_pm_card_lbl">Contact</span>',
                '  <div class="o_pm_contact_row">',
                '    <span class="o_pm_card_val o_pm_contact_val">' + esc(display) + '</span>',
                '    <div class="o_pm_contact_acts">' + actions + '</div>',
                '  </div>',
                '</div>',
            ].join('');
        },

        _cardHtml: function (p, idx) {
            var paid = p.amount_paid ? '1' : '0';
            return [
                '<article class="o_pm_card">',
                '  <div class="o_pm_card_top">',
                '    <div class="o_pm_player">',
                '      <img src="/web/image/auction.team.player/' + p.id +
                    '/photo" onerror="this.src=\'/auction_module/static/img/default_icon.png\'" alt=""/>',
                '      <div>',
                '        <div class="o_pm_card_sl">#' + (p.sl_no || idx + 1) + '</div>',
                '        <div class="o_pm_pname">' + esc(p.name) + '</div>',
                (p.role ? '        <div class="o_pm_prole">' + esc(p.role) + '</div>' : ''),
                '      </div>',
                '    </div>',
                '    ' + this._badge(p.state),
                '  </div>',
                '  <div class="o_pm_card_grid">',
                '    ' + this._cardContactHtml(p),
                '    <div class="o_pm_card_field"><span class="o_pm_card_lbl">Team</span>' +
                    '<span class="o_pm_card_val">' + (p.team ? esc(p.team) : '—') + '</span></div>',
                '    <div class="o_pm_card_field"><span class="o_pm_card_lbl">Manager</span>' +
                    '<span class="o_pm_card_val">' + (p.manager ? esc(p.manager) : '—') + '</span></div>',
                (p.tier ?
                    '    <div class="o_pm_card_field"><span class="o_pm_card_lbl">Tier</span>' +
                    '<span class="o_pm_card_val">' + esc(p.tier) + '</span></div>' : ''),
                '  </div>',
                '  <div class="o_pm_card_actions">',
                '    <button type="button" class="o_pm_pay_btn ' + (p.amount_paid ? 'is-paid' : 'is-unpaid') +
                    '" data-id="' + p.id + '" data-paid="' + paid + '">' +
                    (p.amount_paid ? '✓ Paid' : '✗ Unpaid') + '</button>',
                '    <div class="o_pm_card_proof">' + this._proofBtns(p, true) + '</div>',
                '  </div>',
                '</article>',
            ].join('');
        },

        _render: function (resetPage) {
            if (resetPage) this.S.page = 1;
            var rows = this._getFiltered();
            this._renderStats(rows);
            var $tb = this.$('#o_pm_tbody').empty();
            var $cards = this.$('#o_pm_cards').empty();
            var $empty = this.$('#o_pm_empty');
            if (!rows.length) {
                $empty.show();
                this.$('#o_pm_page_lbl').text('1 / 1');
                this.$('#o_pm_page_info').text('');
                return;
            }
            $empty.hide();

            var html = [];
            var cards = [];
            var self = this;
            var pages = 1;
            var start = 0;

            if (this.S.groupBy === 'none') {
                pages = Math.max(1, Math.ceil(rows.length / this.S.pageSize));
                if (this.S.page > pages) this.S.page = pages;
                start = (this.S.page - 1) * this.S.pageSize;
                var pageRows = rows.slice(start, start + this.S.pageSize);
                var end = start + pageRows.length;
                pageRows.forEach(function (p, i) {
                    html.push(self._rowHtml(p, start + i));
                    cards.push(self._cardHtml(p, start + i));
                });
                this.$('#o_pm_page_lbl').text(this.S.page + ' / ' + pages);
                this.$('#o_pm_page_info').text(
                    'Showing ' + (start + 1) + '–' + end + ' of ' + rows.length +
                    ' · ' + this.S.pageSize + ' per page'
                );
            } else {
                var groups = {};
                var order = [];
                var labels = {draft: 'Draft', auction: 'In Auction', sold: 'Sold', unsold: 'Unsold'};
                rows.forEach(function (p) {
                    var key = '__all__';
                    if (self.S.groupBy === 'state') key = p.state;
                    else if (self.S.groupBy === 'team') key = p.team || '(No Team)';
                    else if (self.S.groupBy === 'payment') key = p.amount_paid ? 'Paid' : 'Unpaid';
                    else if (self.S.groupBy === 'tier') key = p.tier || '(No Tier)';
                    if (!groups[key]) { groups[key] = []; order.push(key); }
                    groups[key].push(p);
                });
                order.forEach(function (k) {
                    var label = self.S.groupBy === 'state' ? (labels[k] || k) : k;
                    html.push(
                        '<tr class="o_pm_group"><td colspan="8"><strong>' + esc(label) +
                        '</strong> <span class="o_pm_muted">(' + groups[k].length + ')</span></td></tr>'
                    );
                    cards.push(
                        '<div class="o_pm_card_group"><strong>' + esc(label) +
                        '</strong> <span class="o_pm_muted">(' + groups[k].length + ')</span></div>'
                    );
                    groups[k].forEach(function (p, i) {
                        html.push(self._rowHtml(p, i));
                        cards.push(self._cardHtml(p, i));
                    });
                });
                this.$('#o_pm_page_lbl').text('All');
                this.$('#o_pm_page_info').text(rows.length + ' players (grouped)');
            }
            $tb.html(html.join(''));
            $cards.html(cards.join(''));
        },

        _toast: function (msg, ok) {
            var $t = this.$('#o_pm_toast');
            $t.text(msg).toggleClass('ok', !!ok).toggleClass('err', !ok).addClass('show');
            clearTimeout(this._toastTmr);
            this._toastTmr = setTimeout(function () { $t.removeClass('show'); }, 2500);
        },

        _onRefresh: function () { this._loadData(); },
        _onToggleTheme: function () {
            this.$el.toggleClass('o_pm_dark');
            this.$('.o_pm_app').toggleClass('o_pm_dark', this.$el.hasClass('o_pm_dark'));
            localStorage.setItem('pm-theme', this.$el.hasClass('o_pm_dark') ? 'dark' : 'light');
            this.$('.o_pm_theme_lbl').text(
                this.$el.hasClass('o_pm_dark') ? '🌙 Dark' : '☀️ Light'
            );
        },
        _onToggleExpand: function () {
            this._syncExpandUi(!this.expanded);
        },
        _onTournamentChange: function (ev) {
            this.tournamentId = parseInt(ev.currentTarget.value, 10) || false;
            this._loadData();
        },
        _applySearchValue: function (raw) {
            var val = String(raw == null ? '' : raw).trim();
            if (this.S.search === val) {
                return;
            }
            this.S.search = val;
            this._render(true);
        },
        _onSearch: function (ev) {
            var self = this;
            var el = ev.currentTarget;
            clearTimeout(this._searchTmr);
            // Read value on timer fire — more reliable with mobile keyboards / composition.
            this._searchTmr = setTimeout(function () {
                var latest = self.$('.o_pm_search').val();
                if (latest == null && el) latest = el.value;
                self._applySearchValue(latest);
            }, 180);
        },
        _onSearchKeydown: function (ev) {
            var key = ev.key || ev.keyCode;
            if (key === 'Enter' || key === 13) {
                ev.preventDefault();
                clearTimeout(this._searchTmr);
                this._applySearchValue(ev.currentTarget.value);
            }
        },
        _onTab: function (ev) {
            this.$('.o_pm_tab').removeClass('active');
            $(ev.currentTarget).addClass('active');
            this.S.stateFilter = $(ev.currentTarget).data('state');
            this._render(true);
        },
        _onPayFilter: function (ev) {
            this.S.payFilter = ev.currentTarget.value;
            this._render(true);
        },
        _onGroupBy: function (ev) {
            this.S.groupBy = ev.currentTarget.value;
            this._render(true);
        },
        _onSortBy: function (ev) {
            this.S.sortField = ev.currentTarget.value;
            this._render(false);
        },
        _onSortDir: function () {
            this.S.sortDir = this.S.sortDir === 'asc' ? 'desc' : 'asc';
            this.$('.o_pm_dir_btn').text(this.S.sortDir === 'asc' ? '↑' : '↓');
            this._render(false);
        },
        _onThSort: function (ev) {
            var field = $(ev.currentTarget).data('sort');
            if (!field) return;
            if (this.S.sortField === field) {
                this.S.sortDir = this.S.sortDir === 'asc' ? 'desc' : 'asc';
            } else {
                this.S.sortField = field;
                this.S.sortDir = 'asc';
            }
            this.$('.o_pm_sort_by').val(this.S.sortField);
            this.$('.o_pm_dir_btn').text(this.S.sortDir === 'asc' ? '↑' : '↓');
            this._render(false);
        },
        _onRevealContact: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var pid = parseInt($(ev.currentTarget).data('id'), 10);
            if (!pid) return;
            this.revealedContacts[pid] = true;
            this._refreshCardContact(pid, $(ev.currentTarget).closest('.o_pm_card_contact'));
        },
        _onHideContact: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var pid = parseInt($(ev.currentTarget).data('id'), 10);
            if (!pid) return;
            delete this.revealedContacts[pid];
            this._refreshCardContact(pid, $(ev.currentTarget).closest('.o_pm_card_contact'));
        },
        _refreshCardContact: function (pid, $field) {
            var p = null;
            for (var i = 0; i < this.players.length; i++) {
                if (this.players[i].id === pid) { p = this.players[i]; break; }
            }
            if (!p || !$field || !$field.length) {
                this._render(false);
                return;
            }
            $field.replaceWith(this._cardContactHtml(p));
        },
        _onTeamChip: function (ev) {
            this.$('.o_pm_team_chip').removeClass('active');
            $(ev.currentTarget).addClass('active');
            this.S.teamFilter = String($(ev.currentTarget).data('team') || '');
            this._render(true);
        },
        _onPrevPage: function () {
            if (this.S.page > 1) { this.S.page -= 1; this._render(false); }
        },
        _onNextPage: function () {
            var rows = this._getFiltered();
            var pages = Math.max(1, Math.ceil(rows.length / this.S.pageSize));
            if (this.S.page < pages) { this.S.page += 1; this._render(false); }
        },
        _onExportToggle: function (ev) {
            ev.stopPropagation();
            this.$('.o_pm_export_wrap').toggleClass('open');
        },
        _onTogglePay: function (ev) {
            var self = this;
            var $btn = $(ev.currentTarget);
            var pid = parseInt($btn.data('id'), 10);
            var next = $btn.data('paid') !== 1 && $btn.data('paid') !== '1';
            $btn.addClass('saving');
            fetch(this.urls.toggle, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'same-origin',
                body: JSON.stringify({
                    jsonrpc: '2.0', id: 1, method: 'call',
                    params: {player_id: pid, paid: next},
                }),
            }).then(function (r) { return r.json(); })
              .then(function (d) {
                  $btn.removeClass('saving');
                  if (d.result && d.result.success) {
                      for (var i = 0; i < self.players.length; i++) {
                          if (self.players[i].id === pid) {
                              self.players[i].amount_paid = next;
                              break;
                          }
                      }
                      self._render(false);
                      self._toast(next ? 'Marked as Paid' : 'Marked as Unpaid', next);
                  } else {
                      self._toast((d.result && d.result.error) || 'Could not save', false);
                  }
              }).catch(function () {
                  $btn.removeClass('saving');
                  self._toast('Network error', false);
              });
        },
        _onUploadClick: function (ev) {
            this._uploadPid = parseInt($(ev.currentTarget).data('id'), 10);
            this.$('.o_pm_proof_file').val('').click();
        },
        _onUploadFile: function (ev) {
            var self = this;
            var file = ev.currentTarget.files && ev.currentTarget.files[0];
            var pid = this._uploadPid;
            if (!file || !pid) return;
            var fd = new FormData();
            fd.append('file', file);
            fd.append('player_id', pid);
            this._toast('Uploading…', true);
            fetch(this.urls.upload, {method: 'POST', credentials: 'same-origin', body: fd})
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d.success) {
                        for (var i = 0; i < self.players.length; i++) {
                            if (self.players[i].id === pid) {
                                self.players[i].proof_att_id = 1;
                                self.players[i].proof_data = d.proof_data || '';
                                self.players[i].amount_paid = true;
                                break;
                            }
                        }
                        self._render(false);
                        self._toast('Screenshot uploaded — marked Paid', true);
                    } else {
                        self._toast(d.error || 'Upload failed', false);
                    }
                }).catch(function () { self._toast('Upload error', false); });
        },
        _onUnlinkProof: function (ev) {
            var self = this;
            var pid = parseInt($(ev.currentTarget).data('id'), 10);
            if (!confirm('Remove payment proof for this player?')) return;
            var fd = new FormData();
            fd.append('player_id', pid);
            fetch(this.urls.unlink, {method: 'POST', credentials: 'same-origin', body: fd})
                .then(function (r) { return r.json(); })
                .then(function (d) {
                    if (d.success) {
                        for (var i = 0; i < self.players.length; i++) {
                            if (self.players[i].id === pid) {
                                self.players[i].proof_att_id = 0;
                                self.players[i].proof_data = '';
                                break;
                            }
                        }
                        self._render(false);
                        self._toast('Proof removed', true);
                    } else {
                        self._toast(d.error || 'Failed', false);
                    }
                }).catch(function () { self._toast('Network error', false); });
        },
        _onOpenProof: function (ev) {
            var pid = parseInt($(ev.currentTarget).data('id'), 10);
            var name = $(ev.currentTarget).data('name') || '';
            var p = null;
            for (var i = 0; i < this.players.length; i++) {
                if (this.players[i].id === pid) { p = this.players[i]; break; }
            }
            this.$('#o_pm_lb_title').text((name ? name + ' — ' : '') + 'Payment Proof');
            var $body = this.$('#o_pm_lb_body').empty();
            this.$('#o_pm_lb').show();
            if (!p || !p.proof_att_id) {
                $body.html('<p class="o_pm_muted">No screenshot uploaded.</p>');
                return;
            }
            if (p.proof_data) {
                $body.html('<img src="' + p.proof_data + '" alt="Proof"/>');
                return;
            }
            $body.html('<p class="o_pm_muted">Loading…</p>');
            var img = new Image();
            img.alt = 'Proof';
            img.onload = function () { $body.empty().append(img); };
            img.onerror = function () {
                $body.html('<p class="o_pm_muted">Could not load payment proof.</p>');
            };
            img.src = this.urls.proof_base + pid + '?t=' + Date.now();
        },
        _onCloseProof: function (ev) {
            var $t = $(ev.target);
            if ($t.closest('.o_pm_lb_box').length && !$t.hasClass('o_pm_lb_close')) {
                return;
            }
            this.$('#o_pm_lb').hide();
            this.$('#o_pm_lb_body').empty();
        },
        _onExportXls: function () {
            this.$('.o_pm_export_wrap').removeClass('open');
            var rows = this._getFiltered();
            var xml = '<?xml version="1.0"?><?mso-application progid="Excel.Sheet"?>';
            xml += '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"';
            xml += ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">';
            xml += '<Styles>';
            xml += '<Style ss:ID="header"><Font ss:Bold="1" ss:Color="#FFFFFF"/>';
            xml += '<Interior ss:Color="#0D1E3A" ss:Pattern="Solid"/></Style>';
            xml += '<Style ss:ID="unpaid"><Font ss:Bold="1" ss:Color="#B91C1C"/>';
            xml += '<Interior ss:Color="#FEE2E2" ss:Pattern="Solid"/></Style>';
            xml += '<Style ss:ID="paid"><Font ss:Color="#0D1E3A"/></Style>';
            xml += '</Styles>';
            xml += '<Worksheet ss:Name="Payments"><Table>';
            xml += '<Row ss:StyleID="header">';
            xml += '<Cell><Data ss:Type="String">#</Data></Cell><Cell><Data ss:Type="String">Name</Data></Cell>';
            xml += '<Cell><Data ss:Type="String">Contact</Data></Cell><Cell><Data ss:Type="String">Payment</Data></Cell>';
            xml += '<Cell><Data ss:Type="String">State</Data></Cell><Cell><Data ss:Type="String">Team</Data></Cell>';
            xml += '<Cell><Data ss:Type="String">Manager</Data></Cell><Cell><Data ss:Type="String">Tier</Data></Cell></Row>';
            rows.forEach(function (p, i) {
                var style = p.amount_paid ? 'paid' : 'unpaid';
                xml += '<Row ss:StyleID="' + style + '">';
                xml += '<Cell><Data ss:Type="Number">' + (p.sl_no || i + 1) + '</Data></Cell>';
                xml += '<Cell><Data ss:Type="String">' + esc(String(p.name || '').toUpperCase()) + '</Data></Cell>';
                xml += '<Cell><Data ss:Type="String">' + esc(p.contact) + '</Data></Cell>';
                xml += '<Cell><Data ss:Type="String">' + (p.amount_paid ? 'Paid' : 'Unpaid') + '</Data></Cell>';
                xml += '<Cell><Data ss:Type="String">' + esc(String(p.state_label || p.state || '').toUpperCase()) + '</Data></Cell>';
                xml += '<Cell><Data ss:Type="String">' + esc(p.team) + '</Data></Cell>';
                xml += '<Cell><Data ss:Type="String">' + esc(p.manager) + '</Data></Cell>';
                xml += '<Cell><Data ss:Type="String">' + esc(p.tier) + '</Data></Cell>';
                xml += '</Row>';
            });
            xml += '</Table></Worksheet></Workbook>';
            var blob = new Blob([xml], {type: 'application/vnd.ms-excel'});
            var a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'payment_marker.xls';
            a.click();
        },
        _onExportPdf: function () {
            this.$('.o_pm_export_wrap').removeClass('open');
            var rows = this._getFiltered();
            var w = window.open('', '_blank');
            if (!w) return;
            var origin = window.location.origin;
            var logoUrl = origin + '/auction_module/static/img/logo_navy.svg';
            var perPage = 28;
            var pageCount = Math.max(1, Math.ceil(rows.length / perPage));
            var tournName = esc(this.tournament.name || 'Payment Tracker');
            var cols = ['#', 'Player', 'Contact', 'Payment', 'State', 'Team', 'Manager', 'Tier'];

            function rowHtml(p, i) {
                var cls = p.amount_paid ? '' : ' class="unpaid"';
                return '<tr' + cls + '><td>' + (p.sl_no || i + 1) + '</td><td>' +
                    esc(String(p.name || '').toUpperCase()) + '</td><td>' +
                    esc(p.contact) + '</td><td>' + (p.amount_paid ? 'Paid' : 'Unpaid') + '</td><td>' +
                    esc(String(p.state_label || p.state || '').toUpperCase()) + '</td><td>' + esc(p.team) + '</td><td>' +
                    esc(p.manager) + '</td><td>' + esc(p.tier) + '</td></tr>';
            }

            var html = [
                '<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Payment Tracker</title>',
                '<style>',
                '  *{box-sizing:border-box}',
                '  html,body{margin:0;padding:0;color:#0d1e3a;background:#fff;',
                '    font-family:Rajdhani,Trebuchet MS,sans-serif}',
                '  .pdf-page{padding:8px 14px 10px;display:block}',
                '  .pdf-page + .pdf-page{page-break-before:always}',
                '  .pdf-header{display:flex;align-items:center;justify-content:space-between;gap:12px;',
                '    padding:4px 0 8px;border-bottom:2px solid #0d1e3a;margin-bottom:8px}',
                '  .pdf-brand img{height:28px;width:auto;display:block}',
                '  .pdf-meta{text-align:right}',
                '  .pdf-kicker{font-size:9px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:#2252b5;margin:0 0 2px}',
                '  .pdf-title{font-size:14px;font-weight:800;margin:0;color:#0d1e3a;text-transform:uppercase;line-height:1.2}',
                '  .pdf-sub{font-size:9px;color:#5a6b85;margin:2px 0 0}',
                '  .pdf-body{margin:0}',
                '  table{border-collapse:collapse;width:100%;table-layout:fixed}',
                '  th,td{border:1px solid #dbe3f0;padding:3px 5px;font-size:10px;text-align:left;line-height:1.25;',
                '    vertical-align:middle;word-wrap:break-word}',
                '  th{background:#0d1e3a;color:#fff;font-weight:700;letter-spacing:.03em;text-transform:uppercase;font-size:9px}',
                '  tr:nth-child(even) td{background:#f5f7fb}',
                '  tr.unpaid td{background:#fee2e2 !important;color:#b91c1c;font-weight:700}',
                '  .pdf-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;',
                '    padding:6px 0 0;margin-top:6px;border-top:1px solid #dbe3f0;',
                '    font-size:9px;font-weight:700;color:#5a6b85}',
                '  .pdf-footer-brand{display:flex;align-items:center;gap:6px}',
                '  .pdf-footer img{height:14px;width:auto;display:block}',
                '  @media print{',
                '    body{margin:0}',
                '    .pdf-page{page-break-after:always;page-break-inside:avoid}',
                '    .pdf-page:last-child{page-break-after:auto}',
                '    .pdf-header,th,tr.unpaid td{-webkit-print-color-adjust:exact;print-color-adjust:exact}',
                '    @page{margin:8mm 7mm 8mm;size:A4 portrait}',
                '  }',
                '</style></head><body>',
            ].join('');

            for (var page = 0; page < pageCount; page++) {
                var start = page * perPage;
                var chunk = rows.slice(start, start + perPage);
                html += '<section class="pdf-page">';
                html += '<header class="pdf-header">';
                html += '<div class="pdf-brand"><img src="' + logoUrl + '" alt="Auction Champ"/></div>';
                html += '<div class="pdf-meta">';
                html += '<div class="pdf-kicker">Payment Tracker</div>';
                html += '<h1 class="pdf-title">' + tournName + '</h1>';
                html += '<div class="pdf-sub">' + rows.length + ' player' +
                    (rows.length === 1 ? '' : 's') +
                    ' · Page ' + (page + 1) + ' of ' + pageCount +
                    ' · Showing ' + (chunk.length ? (start + 1) : 0) +
                    (chunk.length ? '–' + (start + chunk.length) : '') +
                    '</div>';
                html += '</div></header>';
                html += '<div class="pdf-body"><table><thead><tr>';
                cols.forEach(function (h) { html += '<th>' + h + '</th>'; });
                html += '</tr></thead><tbody>';
                if (!chunk.length) {
                    html += '<tr><td colspan="8" style="text-align:center;color:#5a6b85">No players</td></tr>';
                } else {
                    chunk.forEach(function (p, i) {
                        html += rowHtml(p, start + i);
                    });
                }
                html += '</tbody></table></div>';
                html += '<footer class="pdf-footer">';
                html += '<div class="pdf-footer-brand"><span>Powered by</span>';
                html += '<img src="' + logoUrl + '" alt="Auction Champ"/></div>';
                html += '<span>Page ' + (page + 1) + ' / ' + pageCount + '</span>';
                html += '</footer></section>';
            }

            html += '</body></html>';
            w.document.write(html);
            w.document.close();
            setTimeout(function () { w.print(); }, 500);
        },
    });

    core.action_registry.add('auction_module.payment_marker', PaymentMarker);
    return PaymentMarker;
});
