odoo.define('auction_module.PoolGenerator', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var Dialog = require('web.Dialog');

    var POOL_COLORS = [
        '#1a4f9c', '#0e6e8c', '#1e5a8a', '#2456a8',
        '#17607a', '#2a4d8f', '#0f5575', '#1c4580',
    ];

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    var PoolGenerator = AbstractAction.extend({
        className: 'o_pool_generator',
        events: {
            'click .pg-step': '_onStepClick',
            'input .pg-search': '_onSearch',
            'click .pg-team-card': '_onToggleTeam',
            'click .pg-btn-select-all': '_onSelectAll',
            'click .pg-btn-clear': '_onClearTeams',
            'click .pg-btn-next': '_onNext',
            'click .pg-btn-back': '_onBack',
            'change .pg-pool-count': '_onPoolCountChange',
            'input .pg-pool-name': '_onPoolNameInput',
            'change .pg-pool-size': '_onPoolSizeChange',
            'click .pg-btn-equal-sizes': '_onEqualPoolSizes',
            'input .pg-reserve-search': '_onReserveSearch',
            'click .pg-btn-clear-reserves': '_onClearReserves',
            'click .pg-btn-generate': '_onGeneratePools',
            'click .pg-btn-reshuffle': '_onGeneratePools',
            'click .pg-btn-apply-names': '_onApplyNames',
            'click .pg-btn-snapshot-pools': '_onSnapshotPools',
            'click .pg-btn-save-tournament': '_onSaveToTournament',
            'click .pg-ftype': '_onFixtureType',
            'change .pg-outside-n': '_onOutsideN',
            'click .pg-btn-fixture': '_onGenerateFixture',
            'click .pg-btn-snapshot-fixture': '_onSnapshotFixture',
            'click .pg-fx-remove': '_onRemoveMatch',
            'click .pg-fx-move-up': '_onMoveMatch',
            'click .pg-fx-move-down': '_onMoveMatch',
            'change .pg-tournament-select': '_onTournamentChange',
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var ctx = (action && action.context) || {};
            var params = (action && action.params) || {};
            this.tournamentId = params.tournament_id || ctx.tournament_id || false;
            this.state = {
                step: 1,
                tournament: {},
                tournaments: [],
                showTournamentFilter: false,
                isAdmin: false,
                teams: [],
                selected: {},
                search: '',
                poolCount: 2,
                poolNames: [],
                structure: null,
                pools: [],
                tournamentName: '',
                fixtureTypes: [],
                fixtureType: 'pool_rr',
                outsideN: 1,
                fixture: null,
                reservations: {},
                reserveSearch: '',
                poolSizes: [],
                _poolSizeKey: '',
            };
            this._dragIdx = null;
            this._revealTimer = null;
            this._revealMsgTimer = null;
            this._reserveDragId = null;
            this._reservePickId = null;
        },

        _pgRpc: function (opts) {
            opts = opts || {};
            var tid = this.tournamentId || (this.state.tournament && this.state.tournament.id) || false;
            opts.context = Object.assign({}, opts.context || {}, {tournament_id: tid});
            return this._rpc(opts);
        },

        _applyBootstrap: function (data) {
            this.state.tournament = data.tournament || {};
            if (this.state.tournament.id) {
                this.tournamentId = this.state.tournament.id;
            }
            this.state.tournaments = data.tournaments || [];
            this.state.showTournamentFilter = !!data.show_tournament_filter;
            this.state.isAdmin = !!data.is_admin;
            this.state.teams = data.teams || [];
            this.state.poolCount = data.default_pool_count || 2;
            this.state.fixtureTypes = data.fixture_types || this.state.fixtureTypes || [];
            if (!this.state.fixtureType && this.state.fixtureTypes.length) {
                this.state.fixtureType = this.state.fixtureTypes[0].value;
            }
            // Reset draw state for a fresh tournament load
            this.state.selected = {};
            this.state.structure = null;
            this.state.pools = [];
            this.state.fixture = null;
            this.state.poolNames = [];
            this.state._namesFromSave = false;
            this.state.step = 1;
            this.state.search = '';
            this.state.reservations = {};
            this.state.reserveSearch = '';
            this.state.poolSizes = [];
            this.state._poolSizeKey = '';
            this._applySavedState(data);
            if (!this.state.fixtureType) {
                this.state.fixtureType = 'pool_rr';
            }
        },

        start: function () {
            var self = this;
            var result = this._super.apply(this, arguments);
            this.$el.css('position', 'relative');
            this.$el.html('<div class="pg-empty"><strong>Loading Pool Generator…</strong></div>');
            return Promise.resolve(result).then(function () {
                return self._pgRpc({
                    model: 'auction.team.pool.wizard',
                    method: 'client_bootstrap',
                    args: [self.tournamentId || false],
                }).then(function (data) {
                    self._applyBootstrap(data);
                    if (!(self.state.fixtureTypes && self.state.fixtureTypes.length)) {
                        self.state.fixtureTypes = data.fixture_types || [];
                        self.state.fixtureType = (self.state.fixtureTypes[0] && self.state.fixtureTypes[0].value) || 'pool_rr';
                    }
                    return self._loadPoolNames(self.state.poolCount);
                }).then(function () {
                    self._render();
                }).catch(function (err) {
                    console.error('[PoolGenerator]', err);
                    self.$el.html(
                        '<div class="pg-empty"><strong>Could not load Pool Generator</strong>' +
                        '<div>Check that a tournament is selected and you have access.</div></div>'
                    );
                });
            });
        },

        _onTournamentChange: function (ev) {
            var tid = parseInt(ev.currentTarget.value, 10) || false;
            if (!tid || tid === this.tournamentId) {
                return;
            }
            this.tournamentId = tid;
            this._reloadForTournament();
        },

        _reloadForTournament: function () {
            var self = this;
            this.$el.html('<div class="pg-empty"><strong>Loading tournament…</strong></div>');
            return this._pgRpc({
                model: 'auction.team.pool.wizard',
                method: 'client_bootstrap',
                args: [this.tournamentId || false],
            }).then(function (data) {
                self._applyBootstrap(data);
                self.state.fixtureTypes = data.fixture_types || self.state.fixtureTypes || [];
                if (!self.state.fixtureType && self.state.fixtureTypes.length) {
                    self.state.fixtureType = self.state.fixtureTypes[0].value;
                }
                return self._loadPoolNames(self.state.poolCount);
            }).then(function () {
                self._render();
                self._toast('Switched to ' + (self.state.tournament.name || 'tournament'));
            }).catch(function (err) {
                console.error('[PoolGenerator]', err);
                Dialog.alert(self, (err && err.data && err.data.message) || 'Failed to load tournament');
                self._render();
            });
        },

        _loadPoolNames: function (count) {
            var self = this;
            // Keep custom names if already restored from tournament save
            if (this.state.poolNames && this.state.poolNames.length === count && this.state._namesFromSave) {
                this.state._namesFromSave = false;
                return Promise.resolve();
            }
            return this._pgRpc({
                model: 'auction.team.pool.wizard',
                method: 'client_pool_labels',
                args: [count],
            }).then(function (rows) {
                var prev = self.state.poolNames || [];
                self.state.poolNames = (rows || []).map(function (row, i) {
                    return {
                        index: row.index,
                        default_label: row.default_label,
                        custom_name: (prev[i] && prev[i].custom_name) || row.custom_name,
                    };
                });
            });
        },

        _applySavedState: function (data) {
            var saved = data.saved_pools;
            if (saved && saved.structure && saved.pools) {
                this.state.structure = saved.structure;
                this.state.pools = saved.pools;
                this.state.tournamentName = saved.tournament_name || this.state.tournament.name || '';
                this.state.poolCount = saved.pool_count || saved.structure.length || 2;
                var names = saved.pool_names || [];
                this.state.poolNames = names.map(function (n, i) {
                    return {
                        index: i + 1,
                        default_label: n || ('Pool ' + String.fromCharCode(65 + i)),
                        custom_name: n || ('Pool ' + String.fromCharCode(65 + i)),
                    };
                });
                this.state._namesFromSave = true;
                var selected = {};
                (saved.team_ids || []).forEach(function (id) { selected[id] = true; });
                this.state.selected = selected;
                this.state.reservations = saved.reservations || {};
                this.state.poolSizes = (saved.pool_sizes || saved.structure.map(function (p) {
                    return (p || []).length;
                })).map(function (n) { return parseInt(n, 10) || 0; });
                this.state._poolSizeKey = (saved.team_ids || []).length + ':' + this.state.poolCount;
                this.state.step = 3;
                this.state.outsideN = this._defaultMatchesPerTeam();
            }
            if (data.saved_fixture && data.saved_fixture.matches) {
                this.state.fixture = data.saved_fixture;
                this.state.fixtureType = data.saved_fixture.fixture_type || this.state.fixtureType;
                this.state.outsideN = data.saved_fixture.outside_n || this._defaultMatchesPerTeam();
                if (this.state.structure) this.state.step = 4;
            }
        },

        _defaultMatchesPerTeam: function () {
            // (teams in pool) − 1; unequal pools → smallest pool size − 1
            var structure = this.state.structure || [];
            var sizes = structure.map(function (p) { return (p || []).length; })
                .filter(function (n) { return n > 1; });
            if (!sizes.length) return 1;
            return Math.max(1, Math.min.apply(null, sizes) - 1);
        },
        _selectedIds: function () {
            var ids = [];
            var sel = this.state.selected;
            Object.keys(sel).forEach(function (id) {
                if (sel[id]) ids.push(parseInt(id, 10));
            });
            return ids;
        },

        _reservedPoolFor: function (teamId) {
            var reserved = this.state.reservations || {};
            var v = reserved[teamId];
            if (v == null) v = reserved[String(teamId)];
            return parseInt(v, 10) || 0;
        },

        _reservedCount: function () {
            var self = this;
            return this._selectedIds().filter(function (id) {
                return self._reservedPoolFor(id) > 0;
            }).length;
        },

        _pruneReservations: function () {
            var ids = this._selectedIds();
            var idSet = {};
            ids.forEach(function (id) {
                idSet[id] = true;
                idSet[String(id)] = true;
            });
            var max = parseInt(this.state.poolCount, 10) || 0;
            var next = {};
            var reserved = this.state.reservations || {};
            Object.keys(reserved).forEach(function (key) {
                var tid = parseInt(key, 10);
                var pidx = parseInt(reserved[key], 10) || 0;
                if (!tid || !idSet[tid] || pidx < 1 || pidx > max) return;
                next[tid] = pidx;
            });
            this.state.reservations = next;
            return next;
        },

        _reservationPayload: function () {
            return this._pruneReservations();
        },

        _evenSplit: function (total, parts) {
            total = parseInt(total, 10) || 0;
            parts = parseInt(parts, 10) || 0;
            if (parts <= 0) return [];
            var base = Math.floor(Math.max(total, 0) / parts);
            var rem = Math.max(total, 0) % parts;
            var out = [];
            for (var i = 0; i < parts; i++) {
                out.push(base + (i < rem ? 1 : 0));
            }
            return out;
        },

        _syncPoolSizes: function (opts) {
            opts = opts || {};
            var total = this._selectedIds().length;
            var parts = parseInt(this.state.poolCount, 10) || 0;
            var key = total + ':' + parts;
            if (opts.reset || this.state._poolSizeKey !== key || !(this.state.poolSizes || []).length) {
                this.state.poolSizes = this._evenSplit(total, parts);
                this.state._poolSizeKey = key;
            }
            return this.state.poolSizes;
        },

        _poolSizeList: function () {
            this._syncPoolSizes();
            return (this.state.poolSizes || []).map(function (n) {
                return parseInt(n, 10) || 0;
            });
        },

        _poolSizeSum: function (sizes) {
            return (sizes || this.state.poolSizes || []).reduce(function (sum, n) {
                return sum + (parseInt(n, 10) || 0);
            }, 0);
        },

        _poolSizeFor: function (index1) {
            var sizes = this.state.poolSizes || [];
            return parseInt(sizes[index1 - 1], 10) || 0;
        },

        _poolSizesValid: function () {
            var sizes = this.state.poolSizes || [];
            var total = this._selectedIds().length;
            var parts = parseInt(this.state.poolCount, 10) || 0;
            if (!parts || sizes.length !== parts) return false;
            if (sizes.some(function (n) { return (parseInt(n, 10) || 0) < 1; })) return false;
            return this._poolSizeSum(sizes) === total;
        },

        _poolSizeHintHtml: function () {
            this._syncPoolSizes();
            var sizes = this.state.poolSizes || [];
            var total = this._selectedIds().length;
            var sum = this._poolSizeSum(sizes);
            var valid = this._poolSizesValid();
            var expr = sizes.length ? sizes.join(' + ') : '0';
            return (valid
                ? 'Teams per pool: <b>' + esc(expr) + '</b> = ' + sum + ' / ' + total
                : 'Teams per pool: <b>' + esc(expr) + '</b> = ' + sum + ' / ' + total +
                    ' — must equal selected teams, min 1 each');
        },

        _updatePoolSizeHint: function () {
            var $hint = this.$('.pg-size-hint');
            if ($hint.length) {
                $hint.toggleClass('is-bad', !this._poolSizesValid())
                    .html(this._poolSizeHintHtml());
            }
            var valid = this._poolSizesValid() && this._selectedIds().length >= 2;
            this.$('.pg-btn-generate').prop('disabled', !valid);
            var self = this;
            this.$('.pg-pool-size').each(function () {
                var idx = parseInt($(this).data('index'), 10);
                var val = self._poolSizeFor(idx);
                if (String($(this).val()) !== String(val)) $(this).val(val);
            });
        },

        _reserveHintText: function () {
            var ids = this._selectedIds();
            var reservedCount = this._reservedCount();
            if (!ids.length) return 'Select teams first.';
            if (reservedCount === ids.length) {
                return 'All teams reserved — this draw will be fully manual. Drag back to Auto to un-reserve.';
            }
            if (reservedCount) {
                return reservedCount + ' team(s) reserved; the rest in Auto will be assigned by the generator.';
            }
            return 'Optional. Drag a team into a pool to lock it there. Leave teams in Auto for random placement.';
        },

        _updateReserveHint: function () {
            this.$('.pg-reserve-hint-text').text(this._reserveHintText());
            this.$('.pg-btn-clear-reserves').prop('disabled', !this._reservedCount());
        },

        _nameList: function () {
            return this.state.poolNames.map(function (p) {
                return (p.custom_name || p.default_label || '').trim();
            });
        },

        _toast: function (msg) {
            var self = this;
            this.$('.pg-toast').remove();
            var $t = $('<div class="pg-toast"/>').text(msg);
            this.$el.append($t);
            setTimeout(function () { $t.fadeOut(200, function () { $t.remove(); }); }, 2200);
        },

        _tournamentLogoUrl: function () {
            var t = this.state.tournament || {};
            return t.logo_url || false;
        },

        _snapshotFilename: function (kind) {
            // kind: 'pool' | 'fixture' → e.g. "Estadio Tournament_pool.png"
            var name = (
                this.state.tournamentName ||
                (this.state.fixture && this.state.fixture.tournament) ||
                (this.state.tournament && this.state.tournament.name) ||
                'Tournament'
            );
            name = String(name)
                .replace(/[\\/:*?"<>|]+/g, '')
                .replace(/\s+/g, ' ')
                .trim()
                .replace(/[. ]+$/g, '');
            if (!name) name = 'Tournament';
            var suffix = kind === 'fixture' ? 'fixture' : 'pool';
            return name + '_' + suffix + '.png';
        },

        _stageBannerHtml: function (opts) {
            opts = opts || {};
            var logoUrl = this._tournamentLogoUrl();
            var logo = logoUrl
                ? '<img class="pg-stage-logo" src="' + esc(logoUrl) + '" alt=""/>'
                : '';
            var sub = opts.subtitle
                ? '<div class="pg-stage-sub">' + esc(opts.subtitle) + '</div>'
                : '';
            return [
                '<div class="pg-stage-banner' + (logo ? ' has-logo' : '') + '">',
                logo,
                '<div class="pg-stage-banner-text">',
                '<div class="pg-stage-kicker">' + esc(opts.kicker || '') + '</div>',
                '<div class="pg-stage-title">' + esc(opts.title || '') + '</div>',
                sub,
                '<div class="pg-stage-rule"></div>',
                '</div>',
                '</div>',
            ].join('');
        },

        _stageFootHtml: function () {
            return [
                '<div class="pg-stage-foot" aria-label="Powered by AuctionChamp">',
                '<span class="pg-stage-foot-lbl">Powered by</span>',
                '<img class="pg-stage-foot-logo" src="/auction_module/static/src/assets/images/logo.svg" alt="AuctionChamp"/>',
                '</div>',
            ].join('');
        },

        _render: function () {
            var t = this.state.tournament || {};
            var logo = t.logo_url
                ? '<img class="pg-hdr-logo" src="' + esc(t.logo_url) + '" alt=""/>'
                : '<div class="pg-hdr-logo-ph">🏟️</div>';

            var tournamentPicker = '';
            if (this.state.showTournamentFilter && this.state.tournaments.length) {
                var tid = this.tournamentId || t.id || false;
                var opts = this.state.tournaments.map(function (row) {
                    return '<option value="' + row.id + '"' +
                        (String(row.id) === String(tid) ? ' selected="selected"' : '') + '>' +
                        esc(row.name) + '</option>';
                }).join('');
                tournamentPicker = [
                    '<div class="pg-hdr-tournament">',
                    '<label class="pg-field-label" for="pg-tournament-select">Tournament</label>',
                    '<select id="pg-tournament-select" class="pg-select pg-tournament-select">' + opts + '</select>',
                    '</div>',
                ].join('');
            }

            var html = [
                '<div class="pg-shell">',
                '<div class="pg-hdr">',
                '<div class="pg-hdr-brand">',
                logo,
                '<div class="pg-hdr-text">',
                '<span class="pg-hdr-kicker">Auction Settings</span>',
                '<span class="pg-hdr-title">Pool Generator</span>',
                tournamentPicker
                    ? ''
                    : '<span class="pg-hdr-sub">' + esc(t.name || 'Select a working tournament from the systray') + '</span>',
                '</div>',
                '</div>',
                tournamentPicker,
                '<span class="pg-stat-pill">Teams <b>' + this._selectedIds().length + '</b> / ' + this.state.teams.length + '</span>',
                '</div>',
                this._renderSteps(),
                '<div class="pg-body">',
                this._renderStepBody(),
                '</div>',
                '</div>',
            ].join('');
            this.$el.html(html);
            if (this.state.step === 2) {
                this._paintReserveBoard();
                this._bindReserveDnD();
            }
            if (this.state.step === 3 && this.state.structure) {
                this._bindPoolTeamDnD();
            }
            if (this.state.step === 4 && this.state.fixture) {
                this._bindFixtureDnD();
            }
        },

        _renderSteps: function () {
            var steps = [
                {n: 1, label: 'Select Teams', short: 'Teams'},
                {n: 2, label: 'Configure Pools', short: 'Config'},
                {n: 3, label: 'Pool Draw', short: 'Draw'},
                {n: 4, label: 'Fixtures', short: 'Fixtures'},
            ];
            var step = this.state.step;
            var hasPools = !!this.state.structure;
            return '<div class="pg-steps" role="tablist" aria-label="Pool generator steps">' + steps.map(function (s) {
                var cls = 'pg-step';
                if (s.n === step) cls += ' is-active';
                if (s.n < step || (s.n === 3 && hasPools && step === 4)) cls += ' is-done';
                return '<button type="button" class="' + cls + '" data-step="' + s.n + '" role="tab" aria-selected="' +
                    (s.n === step ? 'true' : 'false') + '">' +
                    '<span class="pg-step-num">' + s.n + '</span>' +
                    '<span class="pg-step-lbl-full">' + esc(s.label) + '</span>' +
                    '<span class="pg-step-lbl-short">' + esc(s.short) + '</span>' +
                    '</button>';
            }).join('') + '</div>';
        },

        _renderStepBody: function () {
            if (this.state.step === 1) return this._renderSelect();
            if (this.state.step === 2) return this._renderConfig();
            if (this.state.step === 3) return this._renderPools();
            return this._renderFixture();
        },

        _renderSelect: function () {
            var self = this;
            var q = (this.state.search || '').toLowerCase();
            var cards = this.state.teams.filter(function (t) {
                if (!q) return true;
                return (t.name || '').toLowerCase().indexOf(q) !== -1 ||
                    (t.manager || '').toLowerCase().indexOf(q) !== -1;
            }).map(function (t) {
                var selected = !!self.state.selected[t.id];
                var logo = t.logo_url
                    ? '<img class="pg-team-logo" src="' + esc(t.logo_url) + '" alt=""/>'
                    : '<span class="pg-team-logo-ph">' + esc(t.initials || '?') + '</span>';
                return '<div class="pg-team-card' + (selected ? ' is-selected' : '') + '" data-id="' + t.id + '">' +
                    logo +
                    '<div class="pg-team-meta">' +
                    '<span class="pg-team-name">' + esc(t.name) + '</span>' +
                    (t.manager ? '<span class="pg-team-mgr">' + esc(t.manager) + '</span>' : '') +
                    '</div><span class="pg-check"></span></div>';
            }).join('');

            if (!this.state.teams.length) {
                cards = '<div class="pg-empty"><strong>No teams found</strong>' +
                    '<div>Create teams for the active tournament first.</div></div>';
            } else if (!cards) {
                cards = '<div class="pg-empty"><strong>No matches</strong><div>Try another search.</div></div>';
            }

            return [
                '<div class="pg-panel">',
                '<h2 class="pg-panel-title">Select Teams</h2>',
                '<p class="pg-panel-hint">Choose which teams enter the draw. You can search, select all, or pick individually.</p>',
                '<div class="pg-toolbar">',
                '<input class="pg-search" type="search" placeholder="Search teams…" value="' + esc(this.state.search) + '"/>',
                '<button type="button" class="pg-btn pg-btn-select-all">Select All</button>',
                '<button type="button" class="pg-btn pg-btn-clear">Clear</button>',
                '</div>',
                '<div class="pg-team-grid">' + cards + '</div>',
                '<div class="pg-footer-bar">',
                '<button type="button" class="pg-btn pg-btn-primary pg-btn-next" ' +
                    (this._selectedIds().length < 2 ? 'disabled' : '') + '>Continue to Configure</button>',
                '</div></div>',
            ].join('');
        },

        _renderConfig: function () {
            this._syncPoolSizes();
            var self = this;
            var total = this._selectedIds().length;
            var parts = parseInt(this.state.poolCount, 10) || 1;
            var maxPerPool = Math.max(1, total - (parts - 1));
            var names = this.state.poolNames.map(function (p) {
                return '<div class="pg-name-row">' +
                    '<span class="pg-name-idx">' + esc(p.default_label) + '</span>' +
                    '<input class="pg-input pg-pool-name" data-index="' + p.index + '" ' +
                    'value="' + esc(p.custom_name || '') + '" placeholder="' + esc(p.default_label) + '"/>' +
                    '<input class="pg-input pg-pool-size" type="number" min="1" max="' + maxPerPool +
                    '" data-index="' + p.index + '" value="' + self._poolSizeFor(p.index) +
                    '" title="Teams in this pool" aria-label="Teams in ' +
                    esc(p.custom_name || p.default_label) + '"/>' +
                    '</div>';
            }).join('');
            var sizeValid = this._poolSizesValid();
            return [
                '<div class="pg-panel">',
                '<h2 class="pg-panel-title">Configure Pools</h2>',
                '<p class="pg-panel-hint">Set how many pools to create, rename them, and choose how many teams each pool gets. ' +
                    'Defaults to an even split. Drag teams into a pool below to reserve them — leave the rest in Auto.</p>',
                '<div class="pg-config-grid">',
                '<div>',
                '<label class="pg-field-label">Number of Pools</label>',
                '<input class="pg-input pg-pool-count" type="number" min="1" max="' +
                    Math.max(1, total) + '" value="' + this.state.poolCount + '"/>',
                '<div style="margin-top:10px" class="pg-stat-pill">Selected teams <b>' +
                    total + '</b></div>',
                '</div>',
                '<div>',
                '<div class="pg-name-hd">',
                '<label class="pg-field-label">Pool Names &amp; Sizes</label>',
                '<button type="button" class="pg-btn pg-btn-equal-sizes">Split equally</button>',
                '</div>',
                '<div class="pg-name-cols" aria-hidden="true">' +
                    '<span></span><span>Name</span><span>Teams</span>' +
                '</div>',
                '<div class="pg-name-list">' + names + '</div>',
                '<div class="pg-size-hint' + (sizeValid ? '' : ' is-bad') + '">' +
                    this._poolSizeHintHtml() + '</div>',
                '</div></div>',
                this._renderReserveBlock(),
                '<div class="pg-footer-bar">',
                '<button type="button" class="pg-btn pg-btn-back">Back</button>',
                '<button type="button" class="pg-btn pg-btn-primary pg-btn-generate"' +
                    (sizeValid && total >= 2 ? '' : ' disabled') + '>Generate Pools</button>',
                '</div></div>',
            ].join('');
        },

        _renderReserveBlock: function () {
            var self = this;
            var reservedCount = this._reservedCount();
            var names = this.state.poolNames || [];
            var autoBucket = [
                '<div class="pg-reserve-bucket pg-reserve-auto" data-pool-index="0">',
                '<div class="pg-reserve-bucket-hd">',
                '<span class="pg-reserve-bucket-kicker">AUTO</span>',
                '<span class="pg-reserve-bucket-name">Generator</span>',
                '<span class="pg-reserve-bucket-count" data-count-for="0">0</span>',
                '</div>',
                '<div class="pg-reserve-drop" data-pool-index="0"></div>',
                '</div>',
            ].join('');
            var poolBuckets = names.map(function (p, i) {
                var color = POOL_COLORS[i % POOL_COLORS.length];
                var target = self._poolSizeFor(p.index);
                return '<div class="pg-reserve-bucket" data-pool-index="' + p.index +
                    '" style="--pool-c:' + color + '">' +
                    '<div class="pg-reserve-bucket-hd">' +
                    '<span class="pg-reserve-bucket-kicker">RESERVE</span>' +
                    '<span class="pg-reserve-bucket-name">' + esc(p.custom_name || p.default_label) + '</span>' +
                    '<span class="pg-reserve-bucket-count" data-count-for="' + p.index + '">0/' + target + '</span>' +
                    '</div>' +
                    '<div class="pg-reserve-drop" data-pool-index="' + p.index + '"></div>' +
                    '</div>';
            }).join('');
            return [
                '<div class="pg-reserve">',
                '<div class="pg-reserve-hd">',
                '<div>',
                '<label class="pg-field-label">Team pool preferences</label>',
                '<p class="pg-panel-hint pg-reserve-hint-text" style="margin:0">' +
                    esc(this._reserveHintText()) + '</p>',
                '</div>',
                '<div class="pg-reserve-hd-actions">',
                '<input class="pg-search pg-reserve-search" type="search" placeholder="Filter teams…" value="' +
                    esc(this.state.reserveSearch || '') + '"/>',
                '<button type="button" class="pg-btn pg-btn-clear-reserves"' +
                    (reservedCount ? '' : ' disabled') + '>Clear preferences</button>',
                '</div></div>',
                '<div class="pg-reserve-board" id="pg-reserve-board">',
                '<div class="pg-reserve-auto-wrap">' + autoBucket + '</div>',
                '<div class="pg-reserve-pools">' + poolBuckets + '</div>',
                '</div></div>',
            ].join('');
        },

        _reserveChipHtml: function (t, reserved) {
            var logo = t.logo_url
                ? '<img class="pg-reserve-chip-logo" src="' + esc(t.logo_url) + '" alt=""/>'
                : '<span class="pg-reserve-chip-ph">' + esc(t.initials || '?') + '</span>';
            var unreserve = reserved
                ? '<button type="button" class="pg-reserve-chip-x" data-team-id="' + t.id +
                    '" title="Move to Auto" aria-label="Move to Auto">×</button>'
                : '';
            return '<div class="pg-reserve-chip' + (reserved ? ' is-reserved' : '') +
                '" draggable="true" data-team-id="' + t.id + '" title="' + esc(t.name) + '">' +
                '<span class="pg-reserve-chip-grip" aria-hidden="true">⠿</span>' +
                logo +
                '<span class="pg-reserve-chip-name">' + esc(t.name) + '</span>' +
                unreserve + '</div>';
        },

        _paintReserveBoard: function () {
            var self = this;
            var board = this.el && this.el.querySelector('#pg-reserve-board');
            if (!board) return;
            var ids = this._selectedIds();
            var teamById = {};
            (this.state.teams || []).forEach(function (t) { teamById[t.id] = t; });
            var buckets = {};
            Array.prototype.forEach.call(board.querySelectorAll('.pg-reserve-drop'), function (el) {
                var idx = parseInt(el.getAttribute('data-pool-index'), 10) || 0;
                buckets[idx] = el;
                el.innerHTML = '';
            });
            ids.forEach(function (id) {
                var t = teamById[id] || {id: id, name: 'Team #' + id, initials: '?'};
                var pidx = self._reservedPoolFor(id);
                var target = buckets[pidx] || buckets[0];
                if (target) {
                    target.insertAdjacentHTML('beforeend', self._reserveChipHtml(t, pidx > 0));
                }
            });
            Object.keys(buckets).forEach(function (key) {
                var el = buckets[key];
                var pidx = Number(key);
                var n = el.querySelectorAll('.pg-reserve-chip').length;
                var target = pidx > 0 ? self._poolSizeFor(pidx) : 0;
                var countEl = board.querySelector('[data-count-for="' + key + '"]');
                if (countEl) {
                    countEl.textContent = pidx > 0 ? (n + '/' + target) : String(n);
                }
                var bucket = el.closest && el.closest('.pg-reserve-bucket');
                if (bucket) {
                    bucket.classList.toggle('is-full', pidx > 0 && target > 0 && n >= target);
                    bucket.classList.toggle('is-overfull', pidx > 0 && target > 0 && n > target);
                }
                if (!n) {
                    var empty = document.createElement('div');
                    empty.className = 'pg-reserve-empty';
                    if (!ids.length) {
                        empty.textContent = 'No teams selected';
                    } else if (pidx === 0) {
                        empty.textContent = 'All reserved — drop here to un-reserve';
                    } else {
                        empty.textContent = target
                            ? ('Drop up to ' + target + ' team' + (target === 1 ? '' : 's'))
                            : 'Drop teams here to reserve';
                    }
                    el.appendChild(empty);
                } else if (pidx > 0 && target > n) {
                    var more = document.createElement('div');
                    more.className = 'pg-reserve-empty pg-reserve-more';
                    more.textContent = (target - n) + ' more slot' + (target - n === 1 ? '' : 's');
                    el.appendChild(more);
                }
            });
            if (this._reservePickId) {
                var picked = board.querySelector(
                    '.pg-reserve-chip[data-team-id="' + this._reservePickId + '"]'
                );
                if (picked) picked.classList.add('is-picked');
            }
            this._updateReserveHint();
            this._filterReserveChips();
        },

        _filterReserveChips: function () {
            var q = (this.state.reserveSearch || '').toLowerCase();
            this.$('.pg-reserve-chip').each(function () {
                var name = ($(this).attr('title') || '').toLowerCase();
                $(this).toggleClass('is-filtered', !!q && name.indexOf(q) === -1);
            });
        },

        _setTeamReservation: function (teamId, poolIndex) {
            teamId = parseInt(teamId, 10);
            poolIndex = parseInt(poolIndex, 10) || 0;
            if (!teamId) return false;
            if (!this.state.reservations) this.state.reservations = {};
            var prev = this._reservedPoolFor(teamId);
            if (prev === poolIndex) return false;
            if (poolIndex > 0) {
                var target = this._poolSizeFor(poolIndex);
                var already = this._selectedIds().filter(function (id) {
                    return id !== teamId && this._reservedPoolFor(id) === poolIndex;
                }.bind(this)).length;
                if (target && already >= target) {
                    this._toast(
                        'That pool is full (' + target + ' teams). Increase its size or move a team out.'
                    );
                    return false;
                }
            }
            if (poolIndex < 1) {
                delete this.state.reservations[teamId];
                delete this.state.reservations[String(teamId)];
            } else {
                this.state.reservations[teamId] = poolIndex;
            }
            this._paintReserveBoard();
            return true;
        },

        _bindReserveDnD: function () {
            var self = this;
            var board = this.el && this.el.querySelector('#pg-reserve-board');
            if (!board || board._pgReserveBound) return;
            board._pgReserveBound = true;

            function clearOver() {
                Array.prototype.forEach.call(
                    board.querySelectorAll('.is-over, .is-dragging'),
                    function (n) { n.classList.remove('is-over', 'is-dragging'); }
                );
                board.classList.remove('is-dnd');
            }

            function dropIndexFrom(el) {
                if (!el || !el.closest) return null;
                var drop = el.closest('.pg-reserve-drop, .pg-reserve-bucket');
                if (!drop || !board.contains(drop)) return null;
                var idx = drop.getAttribute('data-pool-index');
                if (idx == null) return null;
                return parseInt(idx, 10) || 0;
            }

            board.addEventListener('dragstart', function (ev) {
                if (ev.target.closest && ev.target.closest('.pg-reserve-chip-x')) {
                    ev.preventDefault();
                    return;
                }
                var chip = ev.target.closest && ev.target.closest('.pg-reserve-chip');
                if (!chip || !board.contains(chip)) return;
                var teamId = parseInt(chip.getAttribute('data-team-id'), 10);
                self._reserveDragId = teamId;
                chip.classList.add('is-dragging');
                board.classList.add('is-dnd');
                try {
                    ev.dataTransfer.effectAllowed = 'move';
                    ev.dataTransfer.setData('text/plain', String(teamId));
                    if (ev.dataTransfer.setDragImage) {
                        ev.dataTransfer.setDragImage(chip, 20, 16);
                    }
                } catch (e) { /* ignore */ }
            });
            board.addEventListener('dragend', function () {
                clearOver();
                self._reserveDragId = null;
            });
            board.addEventListener('dragover', function (ev) {
                if (self._reserveDragId == null) return;
                var idx = dropIndexFrom(ev.target);
                if (idx == null) return;
                ev.preventDefault();
                try { ev.dataTransfer.dropEffect = 'move'; } catch (e) { /* ignore */ }
                Array.prototype.forEach.call(
                    board.querySelectorAll('.pg-reserve-bucket.is-over'),
                    function (n) { n.classList.remove('is-over'); }
                );
                var bucket = ev.target.closest && ev.target.closest('.pg-reserve-bucket');
                if (bucket) bucket.classList.add('is-over');
            });
            board.addEventListener('drop', function (ev) {
                var idx = dropIndexFrom(ev.target);
                var teamId = self._reserveDragId;
                clearOver();
                if (idx == null || teamId == null) return;
                ev.preventDefault();
                self._setTeamReservation(teamId, idx);
                self._reserveDragId = null;
                self._reservePickId = null;
            });
            board.addEventListener('click', function (ev) {
                var xbtn = ev.target.closest && ev.target.closest('.pg-reserve-chip-x');
                if (xbtn && board.contains(xbtn)) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    self._reservePickId = null;
                    self._setTeamReservation(xbtn.getAttribute('data-team-id'), 0);
                    return;
                }
                var chip = ev.target.closest && ev.target.closest('.pg-reserve-chip');
                if (chip && board.contains(chip)) {
                    var teamId = parseInt(chip.getAttribute('data-team-id'), 10);
                    self._reservePickId = self._reservePickId === teamId ? null : teamId;
                    Array.prototype.forEach.call(board.querySelectorAll('.pg-reserve-chip'), function (n) {
                        n.classList.toggle(
                            'is-picked',
                            parseInt(n.getAttribute('data-team-id'), 10) === self._reservePickId
                        );
                    });
                    return;
                }
                var idx = dropIndexFrom(ev.target);
                if (idx == null || self._reservePickId == null) return;
                self._setTeamReservation(self._reservePickId, idx);
                self._reservePickId = null;
            });
        },

        _renderPools: function () {
            if (!this.state.structure) {
                return '<div class="pg-panel"><div class="pg-empty"><strong>No draw yet</strong>' +
                    '<div>Go back and generate pools first.</div></div>' +
                    '<div class="pg-footer-bar"><button type="button" class="pg-btn pg-btn-back">Back</button></div></div>';
            }
            var poolCount = (this.state.pools || []).length;
            var rowCount = Math.max(1, Math.ceil(poolCount / 2));
            var cols = this.state.pools.map(function (pool, i) {
                var color = POOL_COLORS[i % POOL_COLORS.length];
                var rows = (pool.teams || []).map(function (t, ti) {
                    var logo = t.logo_url
                        ? '<img class="pg-pool-team-logo" src="' + esc(t.logo_url) + '" alt=""/>'
                        : '<span class="pg-pool-team-ph">' + esc(t.initials || '?') + '</span>';
                    return '<div class="pg-pool-team" draggable="true" ' +
                        'data-pool-idx="' + i + '" data-team-id="' + t.id + '" data-team-idx="' + ti + '" ' +
                        'title="Drag to another pool">' +
                        '<span class="pg-pool-team-grip" aria-hidden="true">⠿</span>' +
                        '<span class="pg-pool-team-no">' + (ti + 1) + '</span>' +
                        logo +
                        '<span class="pg-pool-team-name">' + esc(t.name) + '</span></div>';
                }).join('');
                return '<div class="pg-pool-col" data-pool-idx="' + i + '">' +
                    '<div class="pg-pool-hd" style="--pool-c:' + color + '">' +
                    '<span class="pg-pool-hd-kicker">GROUP</span>' +
                    '<span class="pg-pool-hd-name">' + esc(pool.name) + '</span>' +
                    '<span class="pg-pool-hd-count">' + (pool.teams || []).length + ' teams</span>' +
                    '</div>' +
                    '<div class="pg-pool-list" data-pool-idx="' + i + '">' +
                    (rows || '<div class="pg-pool-list-empty">Drop teams here</div>') +
                    '</div></div>';
            }).join('');

            var nameEditors = this.state.poolNames.map(function (p) {
                return '<div class="pg-name-row">' +
                    '<span class="pg-name-idx">#' + p.index + '</span>' +
                    '<input class="pg-input pg-pool-name" data-index="' + p.index + '" value="' +
                    esc(p.custom_name || '') + '"/>' +
                    '</div>';
            }).join('');

            return [
                '<div class="pg-panel">',
                '<h2 class="pg-panel-title">Pool Draw</h2>',
                '<p class="pg-panel-hint">Drag teams between pools to fine-tune the draw. Reshuffle redraws randomly. Rename pools and apply without reshuffling.</p>',
                '<div class="pg-toolbar">',
                '<button type="button" class="pg-btn pg-btn-reshuffle">Reshuffle</button>',
                '<button type="button" class="pg-btn pg-btn-apply-names">Apply Names</button>',
                '<button type="button" class="pg-btn pg-btn-primary pg-btn-snapshot-pools">Download Snapshot</button>',
                '<button type="button" class="pg-btn pg-btn-ok pg-btn-save-tournament">Save to Tournament</button>',
                '</div>',
                '<div class="pg-stage-wrap">',
                '<div class="pg-stage pg-stage-square pg-stage-rows-' + rowCount +
                    '" id="pg-pool-snapshot-target" data-rows="' + rowCount + '">',
                this._stageBannerHtml({
                    kicker: 'Official Pool Draw',
                    title: this.state.tournamentName || 'Pool Draw',
                }),
                '<div class="pg-pool-board pg-pool-board-grid pg-pool-board-rows-' + rowCount +
                    '" id="pg-pool-board">' + cols + '</div>',
                this._stageFootHtml(),
                '</div>',
                '</div>',
                '<div style="margin-top:16px">',
                '<label class="pg-field-label">Rename Pools</label>',
                '<div class="pg-name-list" style="max-width:520px">' + nameEditors + '</div>',
                '</div>',
                '<div class="pg-footer-bar">',
                '<button type="button" class="pg-btn pg-btn-back">Back</button>',
                '<button type="button" class="pg-btn pg-btn-primary pg-btn-next">Continue to Fixtures</button>',
                '</div></div>',
            ].join('');
        },

        _renderFixture: function () {
            var self = this;
            if (!this.state.structure) {
                return '<div class="pg-panel"><div class="pg-empty"><strong>Generate pools first</strong></div>' +
                    '<div class="pg-footer-bar"><button type="button" class="pg-btn pg-btn-back">Back</button></div></div>';
            }
            var icons = {
                pool_rr: '◎',
                cross_pool_rr: '✕',
                custom_outside: 'N',
            };
            var types = (this.state.fixtureTypes || []).map(function (ft) {
                return '<div class="pg-ftype' + (self.state.fixtureType === ft.value ? ' is-selected' : '') +
                    '" data-value="' + esc(ft.value) + '">' +
                    '<div class="pg-ftype-ico">' + (icons[ft.value] || '•') + '</div>' +
                    '<div class="pg-ftype-title">' + esc(ft.label) + '</div>' +
                    '<div class="pg-ftype-hint">' + esc(ft.hint || '') + '</div></div>';
            }).join('');

            var outside = [
                '<div class="pg-outside-field">',
                '<label class="pg-field-label">Matches per team (league round)</label>',
                '<input class="pg-input pg-outside-n" type="number" min="1" inputmode="numeric" value="' + this.state.outsideN + '"/>',
                '</div>',
            ].join('');

            var guide = [
                '<div class="pg-fx-guide">',
                '<div class="pg-fx-guide-title">How Matches per Team works</div>',
                '<ul>',
                '<li><b>Default</b> = (teams in that pool) − 1 (full round robin inside the pool).</li>',
                '<li>Every team gets <b>exactly</b> this many league matches. Opponents are chosen randomly.</li>',
                '<li><b>Pool Round Robin</b> — opponents from the <em>same</em> pool.</li>',
                '<li><b>Cross Pool / Custom</b> — opponents from <em>other</em> pools (keep pool sizes equal).</li>',
                '<li><b>Odd pool sizes:</b> with 3 teams you cannot give every team exactly 1 match ',
                '(math: total match slots would be odd). The generator auto-uses the nearest valid value ',
                '(usually <b>2</b> for a 3-team pool). Prefer even N when a pool has an odd number of teams.</li>',
                '</ul>',
                '</div>',
            ].join('');

            var board = '';
            if (this.state.fixture && this.state.fixture.matches) {
                board = [
                    '<div class="pg-toolbar" style="margin-top:8px">',
                    '<span class="pg-stat-pill">' + esc(this.state.fixture.subtitle || 'Fixture') +
                    ' · <b class="pg-fx-match-count">' + this.state.fixture.matches.length + '</b> matches</span>',
                    '<button type="button" class="pg-btn pg-btn-primary pg-btn-snapshot-fixture">Download Fixture Image</button>',
                    '<button type="button" class="pg-btn pg-btn-ok pg-btn-save-tournament">Save Snapshot to Tournament</button>',
                    '</div>',
                    '<p class="pg-panel-hint" style="margin:8px 0 4px">Drag the <b>⠿</b> handle to reorder. Use <b>×</b> to remove a match. Save when the order looks right.</p>',
                    '<div class="pg-stage-wrap">',
                    '<div class="pg-stage pg-stage-portrait" id="pg-fixture-snapshot-target">',
                    this._stageBannerHtml({
                        kicker: 'Match Schedule',
                        title: this.state.fixture.tournament || this.state.tournamentName || 'Fixture',
                        subtitle: this.state.fixture.subtitle || '',
                    }),
                    '<div class="pg-fixture-board pg-fixture-board-vertical" id="pg-fixture-board"></div>',
                    this._stageFootHtml(),
                    '</div>',
                    '</div>',
                ].join('');
            }

            return [
                '<div class="pg-panel">',
                '<h2 class="pg-panel-title">Fixture Generator</h2>',
                '<p class="pg-panel-hint">Pick a fixture style, set how many matches each team plays, generate, reorder or remove matches, then save.</p>',
                guide,
                '<div class="pg-fixture-types">' + types + '</div>',
                outside,
                '<div class="pg-toolbar">',
                '<button type="button" class="pg-btn pg-btn-ok pg-btn-fixture">Generate Fixture</button>',
                '</div>',
                board,
                '<div class="pg-footer-bar">',
                '<button type="button" class="pg-btn pg-btn-back">Back</button>',
                '</div></div>',
            ].join('');
        },

        _onStepClick: function (ev) {
            var step = parseInt($(ev.currentTarget).data('step'), 10);
            if (step === 3 && !this.state.structure) return;
            if (step === 4 && !this.state.structure) return;
            if (step === 2 && this._selectedIds().length < 2) return;
            this.state.step = step;
            this._render();
        },
        _onSearch: function (ev) {
            this.state.search = ev.currentTarget.value || '';
            this._render();
            this.$('.pg-search').focus().val(this.state.search);
            var el = this.$('.pg-search')[0];
            if (el) el.setSelectionRange(this.state.search.length, this.state.search.length);
        },
        _onToggleTeam: function (ev) {
            var id = $(ev.currentTarget).data('id');
            this.state.selected[id] = !this.state.selected[id];
            if (!this.state.selected[id] && this.state.reservations) {
                delete this.state.reservations[id];
                delete this.state.reservations[String(id)];
            }
            this._render();
        },
        _onSelectAll: function () {
            var self = this;
            this.state.teams.forEach(function (t) { self.state.selected[t.id] = true; });
            this._render();
        },
        _onClearTeams: function () {
            var self = this;
            Dialog.confirm(
                this,
                'Clear team selection and remove loaded pools/fixtures from the projector?',
                {
                    title: 'Clear',
                    confirm_callback: function () {
                        self.state.selected = {};
                        self.state.reservations = {};
                        self.state.structure = null;
                        self.state.pools = [];
                        self.state.fixture = null;
                        self.state.step = 1;
                        self._pgRpc({
                            model: 'auction.team.pool.wizard',
                            method: 'client_clear_projector_boards',
                            args: [],
                        }).then(function () {
                            self._render();
                        }).guardedCatch(function (err) {
                            Dialog.alert(
                                self,
                                (err && err.data && err.data.message) ||
                                    'Failed to clear projector boards'
                            );
                            self._render();
                        });
                    },
                }
            );
        },
        _onNext: function () {
            if (this.state.step === 1 && this._selectedIds().length >= 2) {
                this.state.step = 2;
                this._syncPoolSizes();
                this._render();
            } else if (this.state.step === 3 && this.state.structure) {
                this.state.step = 4;
                this._render();
            }
        },
        _onBack: function () {
            if (this.state.step > 1) {
                this.state.step -= 1;
                this._render();
            }
        },
        _onPoolCountChange: function (ev) {
            var self = this;
            var n = parseInt(ev.currentTarget.value, 10) || 1;
            var max = Math.max(1, this._selectedIds().length);
            n = Math.max(1, Math.min(max, n));
            this.state.poolCount = n;
            this._pruneReservations();
            this._syncPoolSizes({reset: true});
            this._loadPoolNames(n).then(function () { self._render(); });
        },
        _onPoolNameInput: function (ev) {
            var idx = parseInt($(ev.currentTarget).data('index'), 10);
            var val = ev.currentTarget.value;
            this.state.poolNames.forEach(function (p) {
                if (p.index === idx) p.custom_name = val;
            });
            var row = this.state.poolNames.filter(function (p) { return p.index === idx; })[0];
            var label = (val || '').trim() || (row && row.default_label) || ('Pool ' + idx);
            this.$('.pg-reserve-bucket[data-pool-index="' + idx + '"] .pg-reserve-bucket-name').text(label);
        },
        _onPoolSizeChange: function (ev) {
            var idx = parseInt($(ev.currentTarget).data('index'), 10);
            var total = this._selectedIds().length;
            var parts = parseInt(this.state.poolCount, 10) || 0;
            if (!idx || !parts) return;
            this._syncPoolSizes();
            var max = Math.max(1, total - (parts - 1));
            var val = parseInt(ev.currentTarget.value, 10);
            if (isNaN(val)) val = this._poolSizeFor(idx) || 1;
            val = Math.max(1, Math.min(max, val));
            this.state.poolSizes[idx - 1] = val;
            if (parts === 2) {
                var other = idx === 1 ? 1 : 0;
                this.state.poolSizes[other] = total - val;
            }
            this._updatePoolSizeHint();
            this._paintReserveBoard();
        },
        _onEqualPoolSizes: function () {
            this._syncPoolSizes({reset: true});
            this._updatePoolSizeHint();
            this._paintReserveBoard();
        },
        _onReserveSearch: function (ev) {
            this.state.reserveSearch = ev.currentTarget.value || '';
            this._filterReserveChips();
        },
        _onClearReserves: function () {
            this.state.reservations = {};
            this._reservePickId = null;
            this._paintReserveBoard();
        },
        _onGeneratePools: function () {
            var self = this;
            var ids = this._selectedIds();
            if (ids.length < 2) {
                this._toast('Select at least 2 teams');
                return;
            }
            if (this.state.revealing) return;
            this._syncPoolSizes();
            if (!this._poolSizesValid()) {
                this._toast('Pool sizes must add up to ' + ids.length + ' teams');
                return;
            }
            var reservations = this._reservationPayload();
            var reservedCount = this._reservedCount();
            var poolSizes = this._poolSizeList();
            this._showRevealLoading('pools');
            var rpc = this._pgRpc({
                model: 'auction.team.pool.wizard',
                method: 'client_generate_pools',
                args: [ids, this.state.poolCount, this._nameList(), reservations, poolSizes],
            });
            Promise.all([rpc, this._waitReveal(5000)]).then(function (pair) {
                var res = pair[0];
                self._hideRevealLoading();
                self.state.structure = res.structure;
                self.state.pools = res.pools;
                self.state.tournamentName = res.tournament_name;
                self.state.fixture = null;
                self.state.outsideN = self._defaultMatchesPerTeam();
                self.state.step = 3;
                self._render();
                var toast = 'Pools generated';
                if (reservedCount === ids.length) {
                    toast = 'Manual pool assignment applied';
                } else if (reservedCount) {
                    toast = reservedCount + ' team(s) reserved · rest auto-assigned';
                }
                self._toast(toast);
            }).catch(function (err) {
                self._hideRevealLoading();
                Dialog.alert(self, (err && err.data && err.data.message) || 'Failed to generate pools');
            });
        },
        _onApplyNames: function () {
            var self = this;
            if (!this.state.structure) return;
            this._pgRpc({
                model: 'auction.team.pool.wizard',
                method: 'client_apply_names',
                args: [this.state.structure, this._nameList()],
            }).then(function (res) {
                self.state.pools = res.pools;
                self.state.tournamentName = res.tournament_name;
                self._render();
                self._toast('Names applied');
            });
        },

        /** Rebuild pools[] team lists from structure[] using cached team payloads. */
        _rebuildPoolsFromStructure: function () {
            var self = this;
            var teamMap = {};
            (this.state.pools || []).forEach(function (p) {
                (p.teams || []).forEach(function (t) {
                    if (t && t.id) teamMap[t.id] = t;
                });
            });
            this.state.pools = (this.state.structure || []).map(function (ids, i) {
                var prev = (self.state.pools && self.state.pools[i]) || {};
                return {
                    index: i + 1,
                    name: prev.name || ('Pool ' + (i + 1)),
                    teams: (ids || []).map(function (id) {
                        return teamMap[id];
                    }).filter(Boolean),
                };
            });
        },

        /**
         * Move a team from one pool to another (or reorder inside the same pool).
         * @param {number} fromPoolIdx
         * @param {number} teamId
         * @param {number} toPoolIdx
         * @param {number|null} toTeamIdx insert before this index in destination (null = append)
         */
        _moveTeamToPool: function (fromPoolIdx, teamId, toPoolIdx, toTeamIdx) {
            if (!this.state.structure) return false;
            teamId = parseInt(teamId, 10);
            fromPoolIdx = parseInt(fromPoolIdx, 10);
            toPoolIdx = parseInt(toPoolIdx, 10);
            var structure = this.state.structure.map(function (p) {
                return (p || []).slice();
            });
            if (fromPoolIdx < 0 || toPoolIdx < 0 ||
                fromPoolIdx >= structure.length || toPoolIdx >= structure.length) {
                return false;
            }
            var from = structure[fromPoolIdx];
            var ti = from.indexOf(teamId);
            if (ti < 0) {
                // ids may be strings from JSON
                ti = from.map(Number).indexOf(teamId);
            }
            if (ti < 0) return false;

            from.splice(ti, 1);
            var to = structure[toPoolIdx];
            var insertAt = (toTeamIdx == null || toTeamIdx < 0) ? to.length : toTeamIdx;
            if (fromPoolIdx === toPoolIdx && ti < insertAt) {
                insertAt -= 1;
            }
            insertAt = Math.max(0, Math.min(to.length, insertAt));
            // Avoid no-op same position
            if (fromPoolIdx === toPoolIdx && insertAt === ti) {
                return false;
            }
            to.splice(insertAt, 0, teamId);
            this.state.structure = structure;
            this.state.fixture = null;
            this._rebuildPoolsFromStructure();
            return true;
        },

        _syncPoolsAfterMove: function () {
            var self = this;
            this._render();
            this._toast('Team moved — projector updating…');
            this._pgRpc({
                model: 'auction.team.pool.wizard',
                method: 'client_apply_names',
                args: [this.state.structure, this._nameList()],
            }).then(function (res) {
                self.state.structure = res.structure || self.state.structure;
                self.state.pools = res.pools || self.state.pools;
                self.state.tournamentName = res.tournament_name || self.state.tournamentName;
                self._toast('Pools updated');
            }).catch(function (err) {
                Dialog.alert(self, (err && err.data && err.data.message) || 'Failed to sync pool move');
            });
        },

        _bindPoolTeamDnD: function () {
            var self = this;
            var board = this.el && this.el.querySelector('#pg-pool-board');
            if (!board) return;

            this._poolDrag = null;

            function clearOver() {
                Array.prototype.forEach.call(
                    board.querySelectorAll('.pg-pool-team.is-over, .pg-pool-list.is-over, .pg-pool-col.is-over'),
                    function (n) { n.classList.remove('is-over'); }
                );
            }

            function parseDropTarget(el) {
                var team = el.closest ? el.closest('.pg-pool-team') : null;
                var list = el.closest ? el.closest('.pg-pool-list') : null;
                if (!list && el.classList && el.classList.contains('pg-pool-list')) list = el;
                if (!list) return null;
                var toPoolIdx = parseInt(list.getAttribute('data-pool-idx'), 10);
                var toTeamIdx = null;
                if (team && team.getAttribute('data-team-idx') != null) {
                    toTeamIdx = parseInt(team.getAttribute('data-team-idx'), 10);
                }
                return { toPoolIdx: toPoolIdx, toTeamIdx: toTeamIdx, teamEl: team, listEl: list };
            }

            Array.prototype.forEach.call(board.querySelectorAll('.pg-pool-team'), function (el) {
                el.setAttribute('draggable', 'true');
                el.addEventListener('dragstart', function (ev) {
                    self._poolDrag = {
                        poolIdx: parseInt(el.getAttribute('data-pool-idx'), 10),
                        teamId: parseInt(el.getAttribute('data-team-id'), 10),
                        teamIdx: parseInt(el.getAttribute('data-team-idx'), 10),
                    };
                    el.classList.add('is-dragging');
                    board.classList.add('is-dnd');
                    try {
                        ev.dataTransfer.effectAllowed = 'move';
                        ev.dataTransfer.setData('text/plain', String(self._poolDrag.teamId));
                        if (ev.dataTransfer.setDragImage) {
                            ev.dataTransfer.setDragImage(el, 20, 16);
                        }
                    } catch (e) { /* ignore */ }
                });
                el.addEventListener('dragend', function () {
                    el.classList.remove('is-dragging');
                    board.classList.remove('is-dnd');
                    clearOver();
                    self._poolDrag = null;
                });
                el.addEventListener('dragover', function (ev) {
                    if (!self._poolDrag) return;
                    ev.preventDefault();
                    ev.stopPropagation();
                    try { ev.dataTransfer.dropEffect = 'move'; } catch (e) { /* ignore */ }
                    clearOver();
                    el.classList.add('is-over');
                    var col = el.closest('.pg-pool-col');
                    if (col) col.classList.add('is-over');
                });
                el.addEventListener('drop', function (ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    var drag = self._poolDrag;
                    clearOver();
                    if (!drag) return;
                    var target = parseDropTarget(el);
                    if (!target) return;
                    if (self._moveTeamToPool(drag.poolIdx, drag.teamId, target.toPoolIdx, target.toTeamIdx)) {
                        self._syncPoolsAfterMove();
                    }
                });
            });

            Array.prototype.forEach.call(board.querySelectorAll('.pg-pool-list'), function (list) {
                list.addEventListener('dragover', function (ev) {
                    if (!self._poolDrag) return;
                    ev.preventDefault();
                    try { ev.dataTransfer.dropEffect = 'move'; } catch (e) { /* ignore */ }
                    // Only highlight list when not over a team row
                    if (!(ev.target.closest && ev.target.closest('.pg-pool-team'))) {
                        clearOver();
                        list.classList.add('is-over');
                        var col = list.closest('.pg-pool-col');
                        if (col) col.classList.add('is-over');
                    }
                });
                list.addEventListener('dragleave', function (ev) {
                    if (!list.contains(ev.relatedTarget)) {
                        list.classList.remove('is-over');
                    }
                });
                list.addEventListener('drop', function (ev) {
                    // If dropped on a team, that handler already ran
                    if (ev.target.closest && ev.target.closest('.pg-pool-team')) return;
                    ev.preventDefault();
                    ev.stopPropagation();
                    var drag = self._poolDrag;
                    clearOver();
                    if (!drag) return;
                    var toPoolIdx = parseInt(list.getAttribute('data-pool-idx'), 10);
                    if (self._moveTeamToPool(drag.poolIdx, drag.teamId, toPoolIdx, null)) {
                        self._syncPoolsAfterMove();
                    }
                });
            });
        },

        _onFixtureType: function (ev) {
            this.state.fixtureType = $(ev.currentTarget).data('value');
            this._render();
        },
        _onOutsideN: function (ev) {
            this.state.outsideN = Math.max(1, parseInt(ev.currentTarget.value, 10) || 1);
        },
        _onGenerateFixture: function () {
            var self = this;
            if (this.state.revealing) return;
            if (!this.state.structure) {
                this._toast('Generate pools first');
                return;
            }
            this._showRevealLoading('fixtures');
            var rpc = this._pgRpc({
                model: 'auction.team.pool.wizard',
                method: 'client_generate_fixture',
                args: [this.state.structure, this._nameList(), this.state.fixtureType, this.state.outsideN],
            });
            Promise.all([rpc, this._waitReveal(5000)]).then(function (pair) {
                var res = pair[0];
                self._hideRevealLoading();
                self.state.fixture = res;
                self._render();
                self._toast(res.matches.length + ' matches ready — drag to reorder');
            }).catch(function (err) {
                self._hideRevealLoading();
                Dialog.alert(self, (err && err.data && err.data.message) || 'Failed to generate fixture');
            });
        },

        _revealMessages: function (kind) {
            if (kind === 'fixtures') {
                return [
                    'Seeding the bracket…',
                    'Shuffling matchups…',
                    'Balancing home & away…',
                    'Locking in rivalries…',
                    'Almost ready to kick off…',
                ];
            }
            return [
                'Shuffling the hat…',
                'Drawing the lots…',
                'Avoiding early clashes…',
                'Balancing the groups…',
                'Sealing the pool draw…',
            ];
        },
        _showRevealLoading: function (kind) {
            var self = this;
            this.state.revealing = true;
            this._hideRevealLoading(true);
            var msgs = this._revealMessages(kind);
            var title = kind === 'fixtures' ? 'Building Fixtures' : 'Drawing Pools';
            var kicker = kind === 'fixtures' ? 'Fixture Generator' : 'Pool Draw';
            var $overlay = $(
                '<div class="pg-reveal" id="pg-reveal">' +
                '<div class="pg-reveal-card">' +
                '<div class="pg-reveal-kicker">' + esc(kicker) + '</div>' +
                '<div class="pg-reveal-title">' + esc(title) + '</div>' +
                '<div class="pg-reveal-orbit">' +
                '<span class="pg-reveal-ring"></span>' +
                '<span class="pg-reveal-ring pg-reveal-ring-2"></span>' +
                '<span class="pg-reveal-core"></span>' +
                '<span class="pg-reveal-chip pg-reveal-chip-a">A</span>' +
                '<span class="pg-reveal-chip pg-reveal-chip-b">B</span>' +
                '<span class="pg-reveal-chip pg-reveal-chip-c">C</span>' +
                '</div>' +
                '<div class="pg-reveal-msg" id="pg-reveal-msg">' + esc(msgs[0]) + '</div>' +
                '<div class="pg-reveal-bar"><i id="pg-reveal-bar-fill"></i></div>' +
                '<div class="pg-reveal-hint">Hold tight — the reveal is coming</div>' +
                '</div></div>'
            );
            this.$el.append($overlay);
            requestAnimationFrame(function () {
                $overlay.addClass('is-on');
                var fill = document.getElementById('pg-reveal-bar-fill');
                if (fill) fill.style.transitionDuration = '5s';
                requestAnimationFrame(function () {
                    if (fill) fill.style.width = '100%';
                });
            });
            var mi = 0;
            this._revealMsgTimer = setInterval(function () {
                mi = (mi + 1) % msgs.length;
                var el = document.getElementById('pg-reveal-msg');
                if (el) {
                    el.classList.add('is-swap');
                    setTimeout(function () {
                        el.textContent = msgs[mi];
                        el.classList.remove('is-swap');
                    }, 180);
                }
            }, 900);
        },
        _waitReveal: function (ms) {
            var self = this;
            return new Promise(function (resolve) {
                self._revealTimer = setTimeout(resolve, ms || 5000);
            });
        },
        _hideRevealLoading: function (silent) {
            this.state.revealing = false;
            if (this._revealTimer) {
                clearTimeout(this._revealTimer);
                this._revealTimer = null;
            }
            if (this._revealMsgTimer) {
                clearInterval(this._revealMsgTimer);
                this._revealMsgTimer = null;
            }
            var $el = this.$('#pg-reveal');
            if (!$el.length) return;
            if (silent) {
                $el.remove();
                return;
            }
            $el.removeClass('is-on').addClass('is-out');
            setTimeout(function () { $el.remove(); }, 280);
        },

        _bindFixtureDnD: function () {
            var board = this.el.querySelector('#pg-fixture-board');
            if (!board || !this.state.fixture) return;
            this._paintFixtureBoard(board, {editable: true});
        },

        _paintFixtureBoard: function (board, opts) {
            var self = this;
            var editable = !!(opts && opts.editable);
            var matches = (this.state.fixture && this.state.fixture.matches) || [];
            board.innerHTML = '';
            if (!matches.length) {
                var empty = document.createElement('div');
                empty.className = 'pg-empty';
                empty.innerHTML = '<strong>No matches left</strong><div>Generate the fixture again, or keep this empty schedule.</div>';
                board.appendChild(empty);
                this._syncFixtureMatchCount();
                return;
            }
            var lastSection = null;
            matches.forEach(function (m, idx) {
                if (m.section && m.section !== lastSection) {
                    lastSection = m.section;
                    var sec = document.createElement('div');
                    sec.className = 'pg-fx-section';
                    sec.textContent = m.section;
                    board.appendChild(sec);
                }
                board.appendChild(self._makeFxCard(m, idx, editable));
            });
            this._syncFixtureMatchCount();
        },

        _syncFixtureMatchCount: function () {
            var n = (this.state.fixture && this.state.fixture.matches)
                ? this.state.fixture.matches.length : 0;
            var el = this.el.querySelector('.pg-fx-match-count');
            if (el) el.textContent = String(n);
        },

        _onRemoveMatch: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            if (!this.state.fixture || !this.state.fixture.matches) return;
            var idx = parseInt($(ev.currentTarget).data('idx'), 10);
            if (isNaN(idx) || idx < 0 || idx >= this.state.fixture.matches.length) return;
            this.state.fixture.matches.splice(idx, 1);
            var board = this.el.querySelector('#pg-fixture-board');
            if (board) this._paintFixtureBoard(board, {editable: true});
            this._toast('Match removed');
        },

        _onMoveMatch: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            if (!this.state.fixture || !this.state.fixture.matches) return;
            var $btn = $(ev.currentTarget);
            var idx = parseInt($btn.data('idx'), 10);
            var dir = $btn.hasClass('pg-fx-move-up') ? -1 : 1;
            var arr = this.state.fixture.matches;
            var to = idx + dir;
            if (isNaN(idx) || to < 0 || to >= arr.length) return;
            var item = arr.splice(idx, 1)[0];
            arr.splice(to, 0, item);
            var board = this.el.querySelector('#pg-fixture-board');
            if (board) this._paintFixtureBoard(board, {editable: true});
        },

        _makeFxCard: function (match, idx, editable) {
            var self = this;
            var card = document.createElement('div');
            card.className = 'pg-fx-card' + (editable ? ' is-editable' : ' is-snapshot');
            card.dataset.idx = String(idx);

            function logo(team) {
                if (team.logo_url) {
                    var img = document.createElement('img');
                    img.className = 'pg-fx-logo';
                    img.src = team.logo_url;
                    return img;
                }
                var ph = document.createElement('span');
                ph.className = 'pg-fx-logo-ph';
                ph.textContent = team.initials || '?';
                return ph;
            }

            var n = document.createElement('span');
            n.className = 'pg-fx-n';
            n.textContent = 'M' + (idx + 1);

            var sideA = document.createElement('div');
            sideA.className = 'pg-fx-side';
            sideA.appendChild(logo(match.team_a));
            var nameA = document.createElement('span');
            nameA.className = 'pg-fx-name';
            nameA.textContent = match.team_a.name;
            sideA.appendChild(nameA);

            var vs = document.createElement('span');
            vs.className = 'pg-fx-vs';
            vs.innerHTML = '<span>VS</span>';

            var sideB = document.createElement('div');
            sideB.className = 'pg-fx-side right';
            var nameB = document.createElement('span');
            nameB.className = 'pg-fx-name';
            nameB.textContent = match.team_b.name;
            sideB.appendChild(nameB);
            sideB.appendChild(logo(match.team_b));

            card.appendChild(n);
            card.appendChild(sideA);
            card.appendChild(vs);
            card.appendChild(sideB);

            if (editable) {
                var actions = document.createElement('div');
                actions.className = 'pg-fx-actions';

                var moveUp = document.createElement('button');
                moveUp.type = 'button';
                moveUp.className = 'pg-fx-move pg-fx-move-up';
                moveUp.title = 'Move up';
                moveUp.setAttribute('aria-label', 'Move match up');
                moveUp.dataset.idx = String(idx);
                moveUp.textContent = '▲';
                moveUp.disabled = idx === 0;

                var moveDown = document.createElement('button');
                moveDown.type = 'button';
                moveDown.className = 'pg-fx-move pg-fx-move-down';
                moveDown.title = 'Move down';
                moveDown.setAttribute('aria-label', 'Move match down');
                moveDown.dataset.idx = String(idx);
                moveDown.textContent = '▼';
                moveDown.disabled = idx >= (self.state.fixture.matches.length - 1);

                var grip = document.createElement('span');
                grip.className = 'pg-fx-grip';
                grip.title = 'Drag to reorder';
                grip.setAttribute('aria-label', 'Drag to reorder');
                grip.setAttribute('draggable', 'true');
                grip.textContent = '⠿';

                var remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'pg-fx-remove';
                remove.title = 'Remove match';
                remove.setAttribute('aria-label', 'Remove match');
                remove.dataset.idx = String(idx);
                remove.textContent = '×';
                remove.addEventListener('mousedown', function (ev) {
                    ev.stopPropagation();
                });
                remove.addEventListener('dragstart', function (ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                });

                actions.appendChild(moveUp);
                actions.appendChild(moveDown);
                actions.appendChild(grip);
                actions.appendChild(remove);
                card.appendChild(actions);

                // Drag from grip only (avoids fighting × / scroll on touch)
                card.draggable = false;
                grip.addEventListener('dragstart', function (ev) {
                    self._dragIdx = idx;
                    card.classList.add('is-dragging');
                    try {
                        ev.dataTransfer.effectAllowed = 'move';
                        ev.dataTransfer.setData('text/plain', String(idx));
                        if (ev.dataTransfer.setDragImage) {
                            ev.dataTransfer.setDragImage(card, 24, 24);
                        }
                    } catch (e) { /* ignore */ }
                });
                grip.addEventListener('dragend', function () {
                    card.classList.remove('is-dragging');
                    self._dragIdx = null;
                    Array.prototype.forEach.call(
                        self.el.querySelectorAll('.pg-fx-card.is-over'),
                        function (c) { c.classList.remove('is-over'); }
                    );
                });
                card.addEventListener('dragover', function (ev) {
                    ev.preventDefault();
                    try { ev.dataTransfer.dropEffect = 'move'; } catch (e) { /* ignore */ }
                    card.classList.add('is-over');
                });
                card.addEventListener('dragleave', function () {
                    card.classList.remove('is-over');
                });
                card.addEventListener('drop', function (ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    card.classList.remove('is-over');
                    var from = self._dragIdx;
                    var to = idx;
                    if (from == null || from === to) return;
                    var arr = self.state.fixture.matches;
                    var item = arr.splice(from, 1)[0];
                    arr.splice(to, 0, item);
                    self._paintFixtureBoard(self.el.querySelector('#pg-fixture-board'), {editable: true});
                });
            }
            return card;
        },

        _snapshotEl: function (el, filename, bg) {
            var self = this;
            return this._elToDataUrl(el, bg).then(function (dataUrl) {
                if (!dataUrl) {
                    self._toast('Nothing to capture');
                    return;
                }
                var link = document.createElement('a');
                link.href = dataUrl;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                self._toast('Downloaded');
            }).catch(function (err) {
                console.error(err);
                self._toast('Snapshot failed');
            });
        },
        _elToDataUrl: function (el, bg) {
            if (!window.html2canvas) {
                return Promise.reject(new Error('Snapshot library not loaded'));
            }
            if (!el) {
                return Promise.resolve(false);
            }
            return window.html2canvas(el, {
                scale: 2,
                backgroundColor: bg || '#0a1628',
                useCORS: true,
                allowTaint: true,
                logging: false,
            }).then(function (canvas) {
                return canvas.toDataURL('image/png');
            });
        },
        _buildOffscreenPoolStage: function () {
            if (!this.state.pools || !this.state.pools.length) return null;
            var poolCount = this.state.pools.length;
            var rowCount = Math.max(1, Math.ceil(poolCount / 2));
            var cols = this.state.pools.map(function (pool, i) {
                var color = POOL_COLORS[i % POOL_COLORS.length];
                var rows = (pool.teams || []).map(function (t, ti) {
                    var logo = t.logo_url
                        ? '<img class="pg-pool-team-logo" src="' + esc(t.logo_url) + '" alt=""/>'
                        : '<span class="pg-pool-team-ph">' + esc(t.initials || '?') + '</span>';
                    return '<div class="pg-pool-team">' +
                        '<span class="pg-pool-team-no">' + (ti + 1) + '</span>' +
                        logo +
                        '<span class="pg-pool-team-name">' + esc(t.name) + '</span></div>';
                }).join('');
                return '<div class="pg-pool-col">' +
                    '<div class="pg-pool-hd" style="--pool-c:' + color + '">' +
                    '<span class="pg-pool-hd-kicker">GROUP</span>' +
                    '<span class="pg-pool-hd-name">' + esc(pool.name) + '</span>' +
                    '<span class="pg-pool-hd-count">' + (pool.teams || []).length + ' teams</span>' +
                    '</div>' +
                    '<div class="pg-pool-list">' + rows + '</div></div>';
            }).join('');
            var wrap = document.createElement('div');
            wrap.className = 'pg-offscreen-capture';
            wrap.innerHTML =
                '<div class="pg-stage pg-stage-square pg-stage-rows-' + rowCount + '">' +
                this._stageBannerHtml({
                    kicker: 'Official Pool Draw',
                    title: this.state.tournamentName || 'Pool Draw',
                }) +
                '<div class="pg-pool-board pg-pool-board-grid pg-pool-board-rows-' + rowCount + '">' +
                cols + '</div>' +
                this._stageFootHtml() +
                '</div>';
            document.body.appendChild(wrap);
            return wrap.firstElementChild;
        },
        _buildOffscreenFixtureStage: function () {
            if (!this.state.fixture || !this.state.fixture.matches) return null;
            var wrap = document.createElement('div');
            wrap.className = 'pg-offscreen-capture';
            wrap.innerHTML =
                '<div class="pg-stage pg-stage-portrait">' +
                this._stageBannerHtml({
                    kicker: 'Match Schedule',
                    title: this.state.fixture.tournament || this.state.tournamentName || 'Fixture',
                    subtitle: this.state.fixture.subtitle || '',
                }) +
                '<div class="pg-fixture-board pg-fixture-board-vertical"></div>' +
                this._stageFootHtml() +
                '</div>';
            document.body.appendChild(wrap);
            var stage = wrap.firstElementChild;
            var board = stage.querySelector('.pg-fixture-board');
            this._paintFixtureBoard(board, {editable: false});
            return stage;
        },
        _captureStageDataUrl: function (selector, builder) {
            var el = selector ? this.el.querySelector(selector) : null;
            var created = null;
            if (!el && builder) {
                el = builder.call(this);
                created = el && el.parentElement;
            }
            var self = this;
            return this._elToDataUrl(el, '#0a1628').then(function (url) {
                if (created && created.parentNode) created.parentNode.removeChild(created);
                return url;
            }).catch(function (err) {
                if (created && created.parentNode) created.parentNode.removeChild(created);
                throw err;
            });
        },
        _onSaveToTournament: function () {
            var self = this;
            if (!this.state.structure) {
                this._toast('Generate pools first');
                return;
            }
            if (this.state.saving) return;
            this.state.saving = true;
            this._toast('Capturing snapshots…');

            var poolP = this._captureStageDataUrl(
                '#pg-pool-snapshot-target', this._buildOffscreenPoolStage
            );
            var fixtureP = (this.state.fixture && this.state.fixture.matches && this.state.fixture.matches.length)
                ? this._captureStageDataUrl(null, this._buildOffscreenFixtureStage)
                : Promise.resolve(false);

            Promise.all([poolP, fixtureP]).then(function (pair) {
                return self._pgRpc({
                    model: 'auction.team.pool.wizard',
                    method: 'client_save_to_tournament',
                    args: [
                        self.state.structure,
                        self._nameList(),
                        self.state.fixture || false,
                        pair[0] || false,
                        pair[1] || false,
                        self.state.fixtureType,
                        self.state.outsideN,
                        self._reservationPayload(),
                        self._poolSizeList(),
                    ],
                });
            }).then(function (res) {
                self.state.saving = false;
                self._toast((res && res.message) || 'Saved to tournament');
            }).catch(function (err) {
                self.state.saving = false;
                console.error(err);
                Dialog.alert(self, (err && err.data && err.data.message) || 'Failed to save to tournament');
            });
        },
        _onSnapshotPools: function () {
            this._toast('Generating image…');
            this._snapshotEl(
                this.el.querySelector('#pg-pool-snapshot-target'),
                this._snapshotFilename('pool'),
                '#0a1628'
            );
        },
        _onSnapshotFixture: function () {
            var self = this;
            if (!this.state.fixture || !this.state.fixture.matches || !this.state.fixture.matches.length) {
                this._toast('No matches to capture');
                return;
            }
            this._toast('Generating image…');
            this._captureStageDataUrl(
                null, this._buildOffscreenFixtureStage
            ).then(function (dataUrl) {
                if (!dataUrl) {
                    self._toast('Nothing to capture');
                    return;
                }
                var link = document.createElement('a');
                link.href = dataUrl;
                link.download = self._snapshotFilename('fixture');
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                self._toast('Downloaded');
            }).catch(function (err) {
                console.error(err);
                self._toast('Snapshot failed');
            });
        },
    });

    core.action_registry.add('auction_module.pool_generator', PoolGenerator);
    return PoolGenerator;
});
