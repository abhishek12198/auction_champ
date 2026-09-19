odoo.define('auction_module.TournamentSettingsUser', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    var NAV = [
        {id: 'today', label: 'Summary'},
        {id: 'players', label: 'Players'},
        {id: 'teams', label: 'Auction Team and Rules'},
        {id: 'look', label: 'Look of the day'},
        {id: 'register', label: 'Registration'},
        {id: 'venue', label: 'When & where'},
        {id: 'payment', label: 'Poster & pay'},
        {id: 'liveday', label: 'Auction day'},
        {id: 'extras', label: 'Rules & extras'},
    ];

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/"/g, '&quot;');
    }

    function yn(flag) {
        return flag ? 'Yes' : 'No';
    }

    var TournamentSettingsUser = AbstractAction.extend({
        hasControlPanel: false,

        events: {
            'click .tsu-nav-btn': '_onNav',
            'click .tsu-tab': '_onTab',
            'click .tsu-back, .tsu-crumb-dash': '_onBack',
            'click .tsu-save': '_onSave',
            'click [data-action]': '_onAction',
            'click [data-copy]': '_onCopy',
            'click [data-screen]': '_onJump',
            'click .tsu-more-close': '_onMoreClose',
            'click .tsu-date-remove': '_onDateRemove',
            'change .tsu-toggle': '_onToggle',
            'change .tsu-input': '_onInput',
            'change .tsu-date-add': '_onDateAdd',
            'input .tsu-date-wrap input[type="date"]': '_onDateFill',
            'change .tsu-date-wrap input[type="date"]': '_onDateFill',
            'change .tsu-file': '_onFile',
            'click .tsu-card.is-edit': '_onEditCard',
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var ctx = (action && action.context) || {};
            var params = (action && action.params) || {};
            this.tournamentId = ctx.tournament_id || params.tournament_id || null;
            this.screen = ctx.settings_screen || params.settings_screen ||
                this._readRememberedScreen() || 'today';
            this.data = null;
            this.dirty = {};
            this.moreOpen = false;
        },

        start: function () {
            this.$el.addClass('o_tournament_settings_user');
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                return self._load();
            });
        },

        _notify: function (type, message) {
            if (this.displayNotification) {
                this.displayNotification({type: type, message: message, sticky: false});
            }
        },

        _load: function () {
            var self = this;
            return this._rpc({
                model: 'auction.tournament',
                method: 'get_user_settings_payload',
                args: [this.tournamentId],
            }).then(function (data) {
                self.data = data || {};
                if (self.data.id) {
                    self.tournamentId = self.data.id;
                }
                self.dirty = {};
                self._render();
            }, function () {
                self.data = {ok: false, error: 'Could not load tournament settings.'};
                self._render();
            });
        },

        _render: function () {
            var d = this.data || {};
            if (!d.ok) {
                this.$el.html(
                    '<div class="tsu-empty">' + esc(d.error || 'No tournament found.') + '</div>'
                );
                return;
            }
            this.$el.html([
                this._topHtml(d),
                '<div class="tsu-body">',
                    this._navHtml(),
                    '<div class="tsu-main">' + this._screenHtml(d) + '</div>',
                '</div>',
                this._bottomHtml(),
                this._moreHtml(),
            ].join(''));
        },

        _topHtml: function () {
            return [
                '<div class="tsu-top">',
                    '<div class="tsu-top-crumb">',
                        '<a href="#" class="tsu-crumb-dash">Player Dashboard</a>',
                        '<span class="tsu-crumb-sep"> / </span>',
                        '<span>Tournament Settings</span>',
                    '</div>',
                    this._btn('Back', {cls: 'tsu-back', icon: 'fa-arrow-left'}),
                    this._btn('Save', {cls: 'tsu-save', icon: 'fa-save'}),
                '</div>',
            ].join('');
        },

        _navHtml: function () {
            var self = this;
            var buttons = NAV.map(function (item) {
                return '<button type="button" class="tsu-nav-btn' +
                    (item.id === self.screen ? ' is-active' : '') +
                    '" data-nav="' + item.id + '">' + esc(item.label) + '</button>';
            }).join('');
            return '<nav class="tsu-nav">' + buttons + '</nav>';
        },

        _bottomHtml: function () {
            var tab = this.screen;
            var moreActive = ['look', 'register', 'venue', 'payment', 'liveday', 'extras'].indexOf(tab) !== -1;
            return [
                '<div class="tsu-bottom">',
                    '<button type="button" class="tsu-tab' + (tab === 'today' ? ' is-active' : '') + '" data-nav="today">Summary</button>',
                    '<button type="button" class="tsu-tab' + (tab === 'players' ? ' is-active' : '') + '" data-nav="players">Players</button>',
                    '<button type="button" class="tsu-tab' + (tab === 'teams' ? ' is-active' : '') + '" data-nav="teams">Teams</button>',
                    '<button type="button" class="tsu-tab' + (moreActive ? ' is-active' : '') + '" data-nav="more">More</button>',
                '</div>',
            ].join('');
        },

        _moreHtml: function () {
            var rest = NAV.slice(3).map(function (item) {
                return '<button type="button" class="tsu-nav-btn" data-nav="' + item.id + '">' +
                    esc(item.label) + '</button>';
            }).join('');
            return '<div class="tsu-more' + (this.moreOpen ? ' is-open' : '') + '">' +
                '<div class="tsu-more-sheet">' + rest +
                this._btn('Close', {cls: 'tsu-more-close', icon: 'fa-times'}) +
                '</div></div>';
        },

        _screenHtml: function (d) {
            var body;
            if (this.screen === 'players') {
                body = this._playersHtml(d);
            } else if (this.screen === 'teams') {
                body = this._teamsHtml(d);
            } else if (this.screen === 'look') {
                body = this._lookHtml(d);
            } else if (this.screen === 'register') {
                body = this._registerHtml(d);
            } else if (this.screen === 'venue') {
                body = this._venueHtml(d);
            } else if (this.screen === 'payment') {
                body = this._paymentHtml(d);
            } else if (this.screen === 'liveday') {
                body = this._liveHtml(d);
            } else if (this.screen === 'extras') {
                body = this._extrasHtml(d);
            } else {
                body = this._todayHtml(d);
            }
            return this._brandHtml(d) + body;
        },

        _brandHtml: function (d) {
            return [
                '<div class="tsu-brand">',
                    this._logoHtml(d),
                    '<div class="tsu-brand-text">',
                        '<h2 class="tsu-h">' + esc(d.name) + '</h2>',
                        '<p class="tsu-sub">' + esc(d.sport) + ' · ' + esc(d.code) + ' · name is locked</p>',
                        '<div class="tsu-hint">Tap the logo to replace it, then Save</div>',
                    '</div>',
                '</div>',
            ].join('');
        },

        _pillInk: function (hex) {
            var raw = String(hex || '').replace('#', '');
            if (raw.length === 3) {
                raw = raw[0] + raw[0] + raw[1] + raw[1] + raw[2] + raw[2];
            }
            if (raw.length !== 6) {
                return '#fff';
            }
            var r = parseInt(raw.slice(0, 2), 16);
            var g = parseInt(raw.slice(2, 4), 16);
            var b = parseInt(raw.slice(4, 6), 16);
            return ((r * 299) + (g * 587) + (b * 114)) / 1000 > 170 ? '#12243f' : '#fff';
        },

        _pageHead: function (title, sub, actions) {
            return [
                '<div class="tsu-page-head">',
                    '<h2 class="tsu-h">' + esc(title) + '</h2>',
                    (sub ? '<p class="tsu-sub">' + esc(sub) + '</p>' : ''),
                    (actions ? '<div class="tsu-actions">' + actions + '</div>' : ''),
                '</div>',
            ].join('');
        },

        _btn: function (label, opts) {
            opts = opts || {};
            var cls = 'tsu-btn' + (opts.cls ? ' ' + opts.cls : '');
            if (opts.disabled || opts.locked) {
                cls += ' is-disabled';
            }
            var attrs = '';
            if (opts.action) attrs += ' data-action="' + esc(opts.action) + '"';
            if (opts.copy) attrs += ' data-copy="' + esc(opts.copy) + '"';
            if (opts.screen) attrs += ' data-screen="' + esc(opts.screen) + '"';
            if (opts.locked) attrs += ' data-locked="1"';
            if (opts.title) attrs += ' title="' + esc(opts.title) + '"';
            if (opts.disabled) attrs += ' disabled="disabled"';
            return '<button type="button" class="' + cls + '"' + attrs + '>' +
                (opts.icon ? '<i class="fa ' + opts.icon + '"></i>' : '') +
                '<span>' + esc(label) + '</span></button>';
        },

        _liveBoardOpenOpts: function (d, extra) {
            extra = extra || {};
            var stopped = !d.live_board_active;
            extra.action = extra.action || 'action_open_live_board';
            extra.icon = extra.icon || 'fa-television';
            extra.locked = stopped;
            extra.disabled = stopped;
            extra.title = stopped ? 'Turn on Live board first' : (extra.title || '');
            return extra;
        },

        _card: function (opts) {
            var cls = 'tsu-card' +
                (opts.gold ? ' is-gold' : '') +
                (opts.locked ? ' is-locked' : '') +
                (opts.action || opts.screen ? ' is-click' : '');
            var attrs = '';
            if (opts.action) attrs += ' data-action="' + esc(opts.action) + '"';
            if (opts.screen) attrs += ' data-screen="' + esc(opts.screen) + '"';
            return '<div class="' + cls + '"' + attrs + '>' +
                (opts.k ? '<span class="tsu-k">' + esc(opts.k) + '</span>' : '') +
                (opts.v !== undefined ? '<div class="tsu-v">' + opts.v + '</div>' : '') +
                (opts.hint ? '<div class="tsu-hint">' + esc(opts.hint) + '</div>' : '') +
                (opts.body || '') +
                '</div>';
        },

        _todayHtml: function (d) {
            var cap = d.max_registrations ? (d.registered + ' / ' + d.max_registrations) : String(d.registered);
            var setup = [
                (d.team_count ? 'Teams done' : 'Add teams'),
                (d.registered ? 'Players done' : 'Add players'),
                (d.has_auction_rules ? 'Rules set' : 'Rules next'),
                (d.has_payment_qr ? 'QR done' : 'QR'),
                (d.has_poster ? 'Poster done' : 'Poster'),
            ].join(' · ');
            var hasTeams = !!(d.team_count || d.has_teams);
            return [
                this._pageHead('Summary', 'Setup and switches for this tournament', [
                    (d.urls && d.urls.registration
                        ? this._btn('Copy Registration Link', {copy: d.urls.registration, icon: 'fa-link'})
                        : this._btn('Copy Registration Link', {screen: 'register', icon: 'fa-link'})),
                    this._btn('Remove Duplicates', {action: 'action_remove_duplicates', icon: 'fa-clone', cls: 'tsu-btn-danger'}),
                    this._btn('Restore Transactions', {action: 'action_open_revoke_transactions', icon: 'fa-undo', cls: 'tsu-btn-gold'}),
                    this._btn('Bid Summary', {action: 'action_open_bid_summary', icon: 'fa-bar-chart'}),
                    this._btn('Live Board', this._liveBoardOpenOpts(d)),
                ].join('')),
                '<div class="tsu-grid tsu-grid-3">',
                    this._card({
                        k: 'Registered players',
                        v: esc(cap),
                        hint: 'Open registered player list',
                        action: 'action_view_registered_players',
                    }),
                    this._card({
                        k: 'Teams ready',
                        v: esc(d.team_count),
                        hint: d.team_count ? 'Open team view' : 'Add a team to get started',
                        action: 'action_user_settings_teams',
                    }),
                    this._card({
                        k: 'Auction rules',
                        v: d.has_auction_rules ? 'Set' : 'Rules not set',
                        gold: !d.has_auction_rules,
                        hint: d.has_auction_rules ? 'Open current rules' : (hasTeams ? 'Set purse and max players' : 'Add teams first'),
                        action: d.has_auction_rules ? 'action_view_auction_rules' : 'action_set_auction_rules',
                    }),
                '</div>',
                '<div class="tsu-grid tsu-grid-3">',
                    this._switchCard('Player registration', 'registration_open', d.registration_open, d.registration_open ? 'Open' : 'Closed', 'Public form accepts players'),
                    this._switchCard('Live board', 'live_board_active', d.live_board_active, d.live_board_active ? 'On air' : 'Stopped', 'Audience page updates during the auction'),
                    this._switchCard('Board code', 'live_board_code_protected', d.live_board_code_protected, d.live_board_code_protected ? 'Code required' : 'Anyone can open', 'Ask for a code before opening live board'),
                '</div>',
                this._card({k: 'Finish setup', hint: setup}),
            ].join('');
        },

        _switchCard: function (title, field, on, value, hint) {
            return '<div class="tsu-card is-edit"><div class="tsu-switch">' +
                '<div><span class="tsu-k">' + esc(title) + '</span>' +
                '<div class="tsu-v">' + esc(value) + '</div>' +
                '<div class="tsu-hint">' + esc(hint) + '</div></div>' +
                '<label class="tsu-switch-ui">' +
                    '<input type="checkbox" class="tsu-toggle" data-field="' + field + '"' +
                    (on ? ' checked' : '') + '/>' +
                    '<span class="tsu-switch-track"><span class="tsu-switch-knob"></span></span>' +
                '</label></div></div>';
        },

        _fieldVal: function (field, fallback) {
            if (this.dirty[field] !== undefined) {
                return this.dirty[field];
            }
            return fallback;
        },

        _editCard: function (label, body, hint) {
            return '<div class="tsu-card tsu-field is-edit">' +
                '<label>' + esc(label) + '</label>' +
                body +
                (hint ? '<div class="tsu-hint">' + esc(hint) + '</div>' : '') +
                '</div>';
        },

        _editNumber: function (label, field, value, suffix, hint) {
            return this._editCard(label,
                '<div class="tsu-edit-row">' +
                    '<input type="number" min="0" max="300" class="tsu-input tsu-edit-input" data-field="' +
                    esc(field) + '" value="' + esc(value) + '"/>' +
                    (suffix ? '<span class="tsu-edit-suffix">' + esc(suffix) + '</span>' : '') +
                '</div>',
                hint);
        },

        _editSelect: function (label, field, options, selected, hint) {
            var html = '<select class="tsu-input tsu-edit-input" data-field="' + esc(field) + '">';
            (options || []).forEach(function (opt) {
                var id = opt.id;
                html += '<option value="' + esc(id) + '"' +
                    (String(id) === String(selected) ? ' selected' : '') + '>' +
                    esc(opt.name || opt.symbol || '') + '</option>';
            });
            html += '</select>';
            return this._editCard(label, html, hint);
        },

        _playersHtml: function (d) {
            var tiles = [
                {k: 'Registered', v: d.registered, a: 'action_view_registered_players'},
                {k: 'In auction', v: d.auction_players, a: 'action_view_auction_players'},
                {k: 'Sold', v: d.sold, a: 'action_view_sold_players'},
                {k: 'Icon', v: d.icon, a: 'action_view_icon_players'},
                {k: 'Unsold', v: d.unsold, a: 'action_view_unsold_players'},
                {k: 'Jersey', v: d.jersey, a: d.enable_jersey ? 'action_view_jersey_players' : ''},
                {k: 'Deleted', v: d.deleted, a: 'action_view_deleted_players'},
            ];
            return [
                this._pageHead('Players', 'Who is in this auction', [
                    this._btn('Add Player', {action: 'action_register_player', icon: 'fa-user-plus'}),
                    this._btn('Upload Excel', {action: 'action_upload_players', icon: 'fa-upload', cls: 'tsu-btn-green'}),
                    this._btn('Sort categories', {action: 'action_open_player_categorization', icon: 'fa-sort-amount-asc'}),
                    this._btn('Export sold', {action: 'action_export_sold_unsold', icon: 'fa-download', cls: 'tsu-btn-green'}),
                    this._btn('Print Player Cards', {action: 'action_print_player_cards', icon: 'fa-print', cls: 'tsu-btn-green'}),
                    this._btn('Remove Duplicates', {action: 'action_remove_duplicates', icon: 'fa-clone', cls: 'tsu-btn-danger'}),
                    this._btn('Restore Transactions', {action: 'action_open_revoke_transactions', icon: 'fa-undo', cls: 'tsu-btn-gold'}),
                ].join('')),
                '<div class="tsu-grid tsu-grid-7">' + tiles.map(function (t) {
                    return '<div class="tsu-card is-click" ' + (t.a ? 'data-action="' + t.a + '"' : '') + '>' +
                        '<span class="tsu-k">' + esc(t.k) + '</span><div class="tsu-v">' + esc(t.v) + '</div></div>';
                }).join('') + '</div>',
                this._card({
                    locked: true,
                    k: 'How the next player appears',
                    v: esc(d.appearance || 'Lucky Dip'),
                    hint: 'Locked for dashboard users. Admin can switch to Roll Call.',
                }),
            ].join('');
        },

        _teamsHtml: function (d) {
            var self = this;
            var teamCards = (d.teams || []).map(function (team) {
                var mark = (team.name || '?').slice(0, 1).toUpperCase();
                var logo = team.logo_url
                    ? '<img src="' + esc(team.logo_url) + '" alt=""/>'
                    : '<div class="tsu-team-ph">' + esc(mark) + '</div>';
                return '<div class="tsu-card is-click" data-action="action_user_settings_teams">' +
                    '<div class="tsu-team">' + logo +
                    '<div><div class="tsu-v">' + esc(team.name) + '</div>' +
                    '<div class="tsu-hint">' + esc(team.manager || 'No manager') + ' · logo</div></div></div></div>';
            }).join('');
            if (!teamCards) {
                teamCards = this._card({hint: 'No teams yet. Upload or add a team.'});
            }
            var tierPills = (d.tiers || []).map(function (tier) {
                var bg = tier.color || '#3498db';
                var marks = '';
                if (tier.icon) {
                    marks += '<i class="fa fa-star" title="Icon tier"></i>';
                }
                if (tier.mystery) {
                    marks += '<i class="fa fa-user-secret" title="Mystery tier"></i>';
                }
                return '<span class="tsu-tier-pill" style="background:' + esc(bg) +
                    ';color:' + self._pillInk(bg) + '">' +
                    marks + '<span>' + esc(tier.name || 'Tier') + '</span></span>';
            }).join('');
            return [
                this._pageHead('Auction Team and Rules', 'Teams, tiers, and Start Auction together', [
                    d.has_auction_rules
                        ? this._btn('Auction Rules', {action: 'action_view_auction_rules', icon: 'fa-gavel'})
                        : this._btn('Set Auction Rules', {
                            action: 'action_set_auction_rules',
                            icon: 'fa-gavel',
                            locked: !(d.team_count || d.has_teams),
                            title: (d.team_count || d.has_teams) ? '' : 'Add teams first',
                        }),
                    this._btn('Upload teams', {action: 'action_upload_teams', icon: 'fa-upload', cls: 'tsu-btn-green'}),
                    this._btn('Add Team', {action: 'action_user_settings_add_team', icon: 'fa-users'}),
                    d.show_football_attrs
                        ? this._btn('Football extra labels', {action: 'action_user_settings_attributes', icon: 'fa-futbol-o'})
                        : '',
                ].join('')),
                '<div class="tsu-grid tsu-grid-3">' + teamCards + '</div>',
                this._card({
                    k: 'Tiers',
                    hint: tierPills ? '' : 'No tiers yet',
                    action: 'action_user_settings_tiers',
                    body: tierPills ? '<div class="tsu-tier-pills">' + tierPills + '</div>' : '',
                }),
            ].join('');
        },

        _lookHtml: function (d) {
            var sold = this._fieldVal('sold_display_seconds', d.sold_seconds);
            var next = this._fieldVal('next_player_countdown', d.next_countdown);
            var jerseyOn = this.dirty.enable_jersey_section !== undefined
                ? this.dirty.enable_jersey_section
                : d.enable_jersey;
            var unitId = this._fieldVal('point_unit_id', d.point_unit_id);
            var unitOpts = (d.point_units || []).map(function (unit) {
                var label = unit.name || unit.symbol || 'Unit';
                if (unit.symbol && unit.name && unit.symbol !== unit.name) {
                    label = unit.name + ' (' + unit.symbol + ')';
                }
                return {id: unit.id, name: label};
            });
            return [
                this._pageHead('Look of the day', 'Gold cards can be changed. Tap a value, then Save'),
                '<div class="tsu-grid tsu-grid-2">',
                    this._fileCard('Tournament logo', 'logo', d.logo_url, 'Same mark as the dashboard. Pick a file, then Save'),
                '</div>',
                '<div class="tsu-grid tsu-grid-3">',
                    this._card({locked: true, k: 'Theme', v: esc(d.theme), hint: 'LOCKED'}),
                    this._editNumber('Sold display', 'sold_display_seconds', sold, 'seconds', 'Tap to change how long SOLD stays up'),
                    this._editNumber('Next player countdown', 'next_player_countdown', next, 'seconds', 'Tap to change the next-player countdown'),
                    this._card({locked: true, k: 'Preset bids', v: esc(d.preset_points || '—'), hint: 'LOCKED'}),
                    this._editSelect('Jersey extras', 'enable_jersey_section', [
                        {id: 1, name: 'On'},
                        {id: 0, name: 'Off'},
                    ], jerseyOn ? 1 : 0, 'Show jersey fields on registration'),
                    this._editSelect('Point unit', 'point_unit_id', unitOpts, unitId, 'Shown with player values'),
                '</div>',
                this._card({locked: true, hint: 'Theme and preset bids stay locked. Ask admin to change those.'}),
            ].join('');
        },

        _linkCard: function (title, url, openAction, extra, extraClass, openClass, openOpts) {
            var safe = url || '';
            openOpts = openOpts || {};
            return '<div class="tsu-card' + (extraClass ? ' ' + extraClass : '') + '">' +
                '<span class="tsu-k">' + esc(title) + '</span>' +
                '<div class="tsu-url">' + esc(safe || 'Not available yet') + '</div>' +
                '<div class="tsu-actions">' +
                    (safe ? this._btn('Copy', {copy: safe, icon: 'fa-clipboard'}) : '') +
                    (openAction ? this._btn('Open', {
                        action: openAction,
                        cls: openClass || '',
                        icon: 'fa-external-link',
                        locked: !!openOpts.locked,
                        disabled: !!openOpts.disabled,
                        title: openOpts.title || (openClass === 'tsu-mobile-disable' ? 'Projector is for larger screens' : ''),
                    }) : '') +
                    (extra || '') +
                '</div></div>';
        },

        _registerHtml: function (d) {
            var u = d.urls || {};
            var wa = this._fieldVal('whatsapp_group_link', d.whatsapp_group_link || u.whatsapp || '');
            return [
                this._pageHead('Registration', 'Copy cards instead of raw URL fields', [
                    u.registration
                        ? this._btn('Copy reg link', {copy: u.registration, icon: 'fa-link'})
                        : '',
                    this._btn('WhatsApp', {action: 'action_share_whatsapp', icon: 'fa-whatsapp'}),
                    this._btn('Admin add-player', {action: 'action_open_admin_registration_link', icon: 'fa-user-plus'}),
                    this._btn('Payment tracker', {action: 'action_open_payment_tracker', icon: 'fa-credit-card'}),
                    (d.expose_contact
                        ? this._btn('Mask Contacts', {action: 'action_remask_player_contact', icon: 'fa-eye-slash'})
                        : this._btn('Unmask Contacts', {action: 'action_open_expose_contact_privacy_wizard', icon: 'fa-eye'})),
                ].join('')),
                '<div class="tsu-grid tsu-grid-2">',
                    this._linkCard('Player registration', u.registration, 'action_open_registration_link',
                        this._btn('WhatsApp', {action: 'action_share_whatsapp', icon: 'fa-whatsapp'})),
                    this._editCard('WhatsApp group',
                        '<input type="url" class="tsu-input tsu-edit-input" data-field="whatsapp_group_link" value="' +
                        esc(wa) + '" placeholder="https://chat.whatsapp.com/..."/>' +
                        (wa ? '<div class="tsu-actions" style="margin-top:8px">' +
                            this._btn('Copy', {copy: wa, icon: 'fa-clipboard'}) + '</div>' : ''),
                        'Paste the group invite, then Save'),
                    this._linkCard('Admin add-player form', u.admin_registration, 'action_open_admin_registration_link'),
                    this._linkCard('Payment tracker', u.payment, 'action_open_payment_tracker'),
                '</div>',
                '<div class="tsu-grid tsu-grid-2">',
                    this._card({locked: true, k: 'Public form flags', hint:
                        'Max ' + (d.max_registrations || '—') +
                        ' · Seats left ' + yn(d.show_capacity) +
                        ' · Names ' + yn(d.show_registered) +
                        ' · Icons ' + yn(d.show_icon_reg) +
                        ' · Org ID ' + yn(d.expose_org_id) +
                        ' · Address ' + yn(d.expose_address) +
                        ' · Address required ' + yn(d.address_required) +
                        ' · LOCKED'}),
                    this._card({
                        k: 'Player phone numbers',
                        v: d.expose_contact ? 'Unmasked' : 'Masked',
                        hint: d.expose_contact
                            ? 'Numbers are visible. Tap Mask Contacts to hide them.'
                            : 'Numbers are hidden. Tap Unmask Contacts to show them.',
                    }),
                '</div>',
            ].join('');
        },

        _datesList: function (d) {
            if (this.dirty.tournament_dates !== undefined) {
                return String(this.dirty.tournament_dates || '').split(',').filter(Boolean);
            }
            return ((d && d.dates) || []).slice();
        },

        _dateLabel: function (iso) {
            var parts = String(iso || '').split('-');
            if (parts.length !== 3) {
                return iso || '';
            }
            var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            var month = parseInt(parts[1], 10) - 1;
            return parts[2] + ' ' + (months[month] || parts[1]) + ' ' + parts[0];
        },

        _venueHtml: function (d) {
            var self = this;
            var opts = (d.locations || []).map(function (loc) {
                return '<option value="' + loc.id + '"' + (loc.id === d.venue_id ? ' selected' : '') + '>' +
                    esc(loc.name) + '</option>';
            }).join('');
            var dates = this._datesList(d);
            var tags = dates.map(function (iso) {
                return '<span class="tsu-date-tag">' + esc(self._dateLabel(iso)) +
                    '<button type="button" class="tsu-date-remove" data-date="' + esc(iso) +
                    '" title="Remove date">&times;</button></span>';
            }).join('');
            return [
                this._pageHead('When and where', 'Venue and auction date can be saved from here'),
                '<div class="tsu-grid tsu-grid-2">',
                    '<div class="tsu-card tsu-field is-edit">' +
                        '<label>Tournament dates</label>' +
                        '<div class="tsu-date-box">' +
                            (tags || '<div class="tsu-hint">No dates yet. Add a day below.</div>') +
                        '</div>' +
                        '<label class="tsu-date-wrap">' +
                            '<input type="date" class="tsu-date-add" title="Add a tournament date" placeholder="DD/MM/YY"/>' +
                            '<span class="tsu-date-ph">DD/MM/YY</span>' +
                        '</label>' +
                        '<div class="tsu-hint">Add one or more match days, then Save</div></div>',
                    '<div class="tsu-card tsu-field is-edit"><label>Ground / venue</label>' +
                        '<select class="tsu-input tsu-edit-input" data-field="venue">' +
                        '<option value="">—</option>' + opts + '</select></div>',
                    '<div class="tsu-card tsu-field is-edit"><label>Auction date</label>' +
                        '<label class="tsu-date-wrap' + (d.auction_date ? ' is-filled' : '') + '">' +
                            '<input type="date" class="tsu-input tsu-edit-input" data-field="auction_date" value="' + esc(d.auction_date) + '" placeholder="DD/MM/YY"/>' +
                            '<span class="tsu-date-ph">DD/MM/YY</span>' +
                        '</label></div>',
                    '<div class="tsu-card tsu-field is-edit"><label>Auction hall</label>' +
                        '<input type="text" class="tsu-input tsu-edit-input" data-field="auction_venue" value="' + esc(d.auction_venue) + '"/></div>',
                '</div>',
                this._card({
                    locked: true,
                    k: 'Organisers',
                    v: esc((d.organizers || []).join(', ') || '—'),
                    hint: (d.organizer_contact || '') + ' · LOCKED',
                }),
            ].join('');
        },

        _logoHtml: function (d) {
            var img = d.logo_url
                ? '<img class="tsu-tour-logo" data-preview="logo" src="' + esc(d.logo_url) + '" alt="" ' +
                  'onerror="this.style.display=\'none\';this.nextElementSibling&&(this.nextElementSibling.style.display=\'\');"/>' +
                  '<span class="tsu-tour-logo-ph" data-logo-ph="1" style="display:none">&#127942;</span>'
                : '<img class="tsu-tour-logo" data-preview="logo" alt="" style="display:none"/>' +
                  '<span class="tsu-tour-logo-ph" data-logo-ph="1">&#127942;</span>';
            return '<label class="tsu-tour-logo-wrap" title="Change tournament logo">' +
                img +
                '<input type="file" accept="image/*" class="tsu-file tsu-logo-file" data-field="logo"/>' +
                '</label>';
        },

        _fileCard: function (title, field, url, hint) {
            return '<div class="tsu-card tsu-drop is-edit"><span class="tsu-k">' + esc(title) + '</span>' +
                (url
                    ? '<img data-preview="' + esc(field) + '" src="' + esc(url) + '" alt=""/>'
                    : '<img data-preview="' + esc(field) + '" alt="" style="display:none"/>') +
                (url ? '' : '<div class="tsu-hint tsu-drop-empty">Drop image or replace</div>') +
                '<div class="tsu-hint">' + esc(hint) + '</div>' +
                '<input type="file" accept="image/*" class="tsu-file" data-field="' + field + '"/></div>';
        },

        _paymentHtml: function (d) {
            return [
                this._pageHead('Poster and payment', 'These saves work for dashboard users'),
                '<div class="tsu-grid tsu-grid-2">',
                    this._fileCard('Tournament poster', 'poster_image', d.poster_url, 'Used on share cards and the public page'),
                    this._fileCard('Social share image', 'social_share_image', d.social_url, 'Optional square crop'),
                    this._fileCard('Payment QR', 'payment_qr_image', d.payment_qr_url, 'UPI / bank QR'),
                    '<div class="tsu-card tsu-field is-edit"><label>Payment note</label>' +
                        '<textarea class="tsu-input tsu-edit-input" data-field="payment_instruction">' + esc(d.payment_instruction) + '</textarea>' +
                        '<label style="margin-top:10px"><input type="checkbox" class="tsu-input" data-field="payment_proof_required"' +
                        (d.payment_proof_required ? ' checked' : '') + '/> Proof required</label></div>',
                '</div>',
            ].join('');
        },

        _liveHtml: function (d) {
            var u = d.urls || {};
            return [
                this._pageHead('Auction day', 'What the room opens after setup', [
                    (u.projector
                        ? this._btn('Copy projector', {copy: u.projector, icon: 'fa-clipboard'})
                        : ''),
                    this._btn('Open projector', {
                        action: 'action_open_projector_link',
                        cls: 'tsu-mobile-disable',
                        icon: 'fa-desktop',
                        title: 'Projector is for larger screens',
                    }),
                    this._btn('Live Board', this._liveBoardOpenOpts(d)),
                    this._btn('Bid Summary', {action: 'action_open_bid_summary', icon: 'fa-bar-chart'}),
                    this._btn('YouTube overlay', {action: 'action_open_youtube_overlay', icon: 'fa-youtube-play'}),
                    this._btn('YouTube watch', {action: 'action_open_youtube_watch', icon: 'fa-play-circle'}),
                ].join('')),
                '<div class="tsu-grid tsu-grid-2">',
                    this._linkCard('Projector', u.projector, 'action_open_projector_link', '', '', 'tsu-mobile-disable'),
                    this._linkCard('Public live board', u.live_board, 'action_open_live_board', '', '', '', this._liveBoardOpenOpts(d)),
                    this._linkCard('Bid Summary', u.bid_summary, 'action_open_bid_summary'),
                    this._linkCard('YouTube overlay', u.youtube_overlay, 'action_open_youtube_overlay'),
                '</div>',
                '<div class="tsu-card tsu-field is-edit"><label>YouTube stream URL</label>' +
                    '<input type="url" class="tsu-input tsu-edit-input" data-field="youtube_url" value="' + esc(d.youtube_url) + '"/></div>',
                this._switchCard('Sound on live bids', 'live_bid_sound', d.live_bid_sound, d.live_bid_sound ? 'On' : 'Off', 'Same live bid sound toggle'),
            ].join('');
        },

        _extrasHtml: function (d) {
            var ads = (d.advertisers || []).map(function (ad) {
                return '<li>' + esc(ad.name) + (ad.active ? '' : ' (off)') + '</li>';
            }).join('');
            return [
                this._pageHead('Rules and extras', 'Pools, sponsors, and extra labels', [
                    d.show_pools
                        ? this._btn('Open pool generator', {action: 'action_open_pool_generator', icon: 'fa-th'})
                        : '',
                    d.show_football_attrs
                        ? this._btn('Football extra labels', {action: 'action_user_settings_attributes', icon: 'fa-futbol-o'})
                        : '',
                    this._btn('Advertisers', {action: 'action_user_settings_advertisers', icon: 'fa-bullhorn'}),
                ].join('')),
                this._card({
                    locked: true,
                    k: 'Rules shown to players',
                    hint: 'HTML editor. Locked for non-admin save today. Ask admin to update rules.',
                }),
                '<div class="tsu-card is-click" data-action="action_user_settings_advertisers">' +
                    '<span class="tsu-k">Advertisers / sponsors</span>' +
                    (ads ? '<ul class="tsu-list">' + ads + '</ul>' : '<div class="tsu-hint">No sponsors yet</div>') +
                '</div>',
                d.show_pools ? '' : this._card({locked: true, hint: 'Pools and fixtures appear if you have that group.'}),
            ].join('');
        },

        _onNav: function (ev) {
            var id = ev.currentTarget.getAttribute('data-nav');
            if (!id) return;
            ev.preventDefault();
            if (id === 'more') {
                this.moreOpen = true;
                this.$('.tsu-more').addClass('is-open');
                return;
            }
            this.screen = id;
            this.moreOpen = false;
            this._rememberScreen();
            this._render();
        },

        _onTab: function (ev) {
            this._onNav(ev);
        },

        _onJump: function (ev) {
            var screen = ev.currentTarget.getAttribute('data-screen');
            if (!screen) return;
            ev.preventDefault();
            ev.stopPropagation();
            this.screen = screen;
            this._rememberScreen();
            this._render();
        },

        _onMoreClose: function () {
            this.moreOpen = false;
            this.$('.tsu-more').removeClass('is-open');
        },

        _screenKey: function () {
            return this.tournamentId ? 'tsu.screen.' + this.tournamentId : '';
        },

        _readRememberedScreen: function () {
            var key = this._screenKey();
            if (!key) return '';
            try {
                return sessionStorage.getItem(key) || '';
            } catch (e) {
                return '';
            }
        },

        _rememberScreen: function () {
            var key = this._screenKey();
            if (!key || !this.screen) return;
            try {
                sessionStorage.setItem(key, this.screen);
            } catch (e) { /* */ }
        },

        _onBack: function (ev) {
            if (ev) {
                ev.preventDefault();
            }
            this.trigger_up('history_back');
        },

        _setDates: function (dates) {
            var unique = [];
            (dates || []).forEach(function (iso) {
                if (iso && unique.indexOf(iso) === -1) {
                    unique.push(iso);
                }
            });
            unique.sort();
            this.dirty.tournament_dates = unique.join(',') || false;
            if (this.data) {
                this.data.dates = unique;
            }
            this._render();
        },

        _onDateFill: function (ev) {
            var wrap = ev.currentTarget.closest && ev.currentTarget.closest('.tsu-date-wrap');
            if (wrap) {
                wrap.classList.toggle('is-filled', !!ev.currentTarget.value);
            }
        },

        _onDateAdd: function (ev) {
            var iso = ev.currentTarget.value;
            if (!iso) return;
            var dates = this._datesList(this.data || {});
            dates.push(iso);
            this._setDates(dates);
        },

        _onDateRemove: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var iso = ev.currentTarget.getAttribute('data-date');
            var dates = this._datesList(this.data || {}).filter(function (item) {
                return item !== iso;
            });
            this._setDates(dates);
        },

        _onEditCard: function (ev) {
            if (ev.target.closest('input, select, textarea, button, label, a, .tsu-date-remove')) {
                return;
            }
            var field = ev.currentTarget.querySelector('.tsu-edit-input, .tsu-input, select, textarea, input[type="checkbox"]');
            if (field) {
                field.focus();
                if (typeof field.select === 'function' && field.type && field.type !== 'checkbox' && field.type !== 'file') {
                    field.select();
                }
            }
        },

        _onInput: function (ev) {
            var field = ev.currentTarget.getAttribute('data-field');
            if (!field) return;
            var val = ev.currentTarget.value;
            if (ev.currentTarget.type === 'checkbox') {
                this.dirty[field] = ev.currentTarget.checked;
            } else if (field === 'venue' || field === 'point_unit_id') {
                this.dirty[field] = val ? parseInt(val, 10) : false;
            } else if (field === 'sold_display_seconds' || field === 'next_player_countdown') {
                this.dirty[field] = val === '' ? 0 : parseInt(val, 10) || 0;
            } else if (field === 'enable_jersey_section') {
                this.dirty[field] = val === '1' || val === 'true';
            } else {
                this.dirty[field] = val;
            }
        },

        _onFile: function (ev) {
            var field = ev.currentTarget.getAttribute('data-field');
            var file = ev.currentTarget.files && ev.currentTarget.files[0];
            if (!field || !file) return;
            var self = this;
            var reader = new FileReader();
            reader.onload = function () {
                var raw = String(reader.result || '');
                var parts = raw.split(',');
                self.dirty[field] = parts.length > 1 ? parts[1] : raw;
                self.$('img[data-preview="' + field + '"]').attr('src', raw).show();
                if (field === 'logo') {
                    self.$('[data-logo-ph]').hide();
                }
                var wrap = ev.currentTarget.closest && ev.currentTarget.closest('.tsu-drop');
                if (wrap) {
                    var empty = wrap.querySelector('.tsu-drop-empty');
                    if (empty) {
                        empty.style.display = 'none';
                    }
                }
                self._notify('info', 'Image ready — tap Save');
            };
            reader.readAsDataURL(file);
        },

        _onSave: function () {
            var self = this;
            if (!this.data || !this.data.id) return;
            if (!Object.keys(this.dirty).length) {
                this._notify('info', 'Nothing to save');
                return;
            }
            this._rpc({
                model: 'auction.tournament',
                method: 'save_user_settings',
                args: [[this.data.id], this.dirty],
            }).then(function (data) {
                self.data = data;
                self.dirty = {};
                self._render();
                self._notify('success', 'Saved');
            }, function (err) {
                self._notify('danger', self._errMsg(err, 'Could not save'));
            });
        },

        _onToggle: function (ev) {
            var field = ev.currentTarget.getAttribute('data-field');
            var map = {
                registration_open: 'action_toggle_registration',
                live_board_active: 'action_toggle_live_board',
                live_board_code_protected: 'action_toggle_live_board_code_protected',
            };
            if (map[field]) {
                this._call(map[field]);
                return;
            }
            if (field === 'live_bid_sound') {
                this.dirty.live_bid_sound = ev.currentTarget.checked;
                this._onSave();
            }
        },

        _onAction: function (ev) {
            var name = ev.currentTarget.getAttribute('data-action');
            if (!name) return;
            ev.preventDefault();
            ev.stopPropagation();
            if (ev.currentTarget.getAttribute('data-locked')) {
                this._notify('warning', ev.currentTarget.getAttribute('title') || 'Add teams first');
                return;
            }
            this._call(name);
        },

        _prepareAction: function (action) {
            if (!action || typeof action !== 'object') {
                return action;
            }
            if (action.type !== 'ir.actions.act_window') {
                if (action.type === 'ir.actions.client' && !Array.isArray(action.views)) {
                    action.views = [];
                }
                return action;
            }
            if (action.target === 'new') {
                if (!Array.isArray(action.views) || !action.views.length) {
                    action.views = [[false, 'form']];
                }
                return action;
            }
            var fallback = action.res_model === 'auction.team.player'
                ? 'kanban,list,form'
                : 'list,form';
            if (!Array.isArray(action.views) || !action.views.length) {
                action.views = String(action.view_mode || fallback).split(',').map(function (mode) {
                    return [false, mode.trim()];
                });
            }
            action.views = (action.views || []).map(function (view) {
                var mode = view && view[1] === 'tree' ? 'list' : (view && view[1]);
                return [view && view[0], mode];
            });
            if (action.view_mode) {
                action.view_mode = String(action.view_mode).replace(/\btree\b/g, 'list');
            }
            // Player lists: same as dashboard / Draft menu — kanban, list, then form.
            if (action.res_model === 'auction.team.player' && !action.res_id) {
                var kanban = null;
                var rest = [];
                action.views.forEach(function (view) {
                    if (view[1] === 'kanban') {
                        kanban = view;
                    } else {
                        rest.push(view);
                    }
                });
                if (kanban) {
                    action.views = [kanban].concat(rest);
                }
                action.view_mode = action.views.map(function (view) {
                    return view[1];
                }).join(',');
                action.view_type = action.views[0] && action.views[0][1];
            }
            return action;
        },

        _call: function (name) {
            var self = this;
            if (!this.data || !this.data.id) return;
            return this._rpc({
                model: 'auction.tournament',
                method: 'call_user_settings_action',
                args: [[this.data.id], name],
            }).then(function (action) {
                if (action && action.type) {
                    action.context = Object.assign({}, action.context || {}, {
                        from_user_settings: true,
                        settings_screen: self.screen,
                    });
                    if (action.type === 'ir.actions.client') {
                        action.params = Object.assign({}, action.params || {}, {
                            from_user_settings: true,
                            settings_screen: self.screen,
                            tournament_id: (action.params && action.params.tournament_id) || self.data.id,
                        });
                    }
                    self._rememberScreen();
                    return self.do_action(self._prepareAction(action), {
                        on_close: function () {
                            if (!self.isDestroyed()) {
                                return self._load();
                            }
                        },
                        on_reverse_breadcrumb: function () {
                            if (!self.isDestroyed()) {
                                return self._load();
                            }
                        },
                    }).then(null, function (err) {
                        self._notify('danger', self._errMsg(err, 'Could not open this screen'));
                    });
                }
                return self._load();
            }, function (err) {
                self._notify('danger', self._errMsg(err, 'Action failed'));
            });
        },

        _onCopy: function (ev) {
            var text = ev.currentTarget.getAttribute('data-copy') || '';
            ev.preventDefault();
            ev.stopPropagation();
            if (!text) return;
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text);
            } else {
                var box = document.createElement('textarea');
                box.value = text;
                document.body.appendChild(box);
                box.select();
                document.execCommand('copy');
                document.body.removeChild(box);
            }
            this._notify('success', 'Copied');
        },

        _errMsg: function (err, fallback) {
            try {
                return err.message.data.message || err.data.message || fallback;
            } catch (e) {
                return fallback;
            }
        },
    });

    core.action_registry.add('auction_module.tournament_settings_user', TournamentSettingsUser);
    core.action_registry.add('tournament_settings_user', TournamentSettingsUser);
    return TournamentSettingsUser;
});
