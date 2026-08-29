odoo.define('auction_module.PlayerCategorization', function (require) {
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

    var PlayerCategorization = AbstractAction.extend({
        className: 'o_player_categorization',
        hasControlPanel: false,
        events: {
            'click .pcat-btn-refresh': '_onRefresh',
            'click .pcat-btn-new-tier': '_onOpenNewTier',
            'click .pcat-tier-cancel': '_onCloseNewTier',
            'click .pcat-tier-save': '_onSaveNewTier',
            'click .pcat-modal-backdrop, .pcat-modal-cancel': '_onCloseTeamModal',
            'click .pcat-team-card': '_onPickTeam',
            'click .pcat-modal-confirm': '_onConfirmTeam',
            'input .pcat-search': '_onSearch',
            'click .pcat-btn-clear-sel': '_onClearSelection',
            'click .pcat-btn-select-col': '_onSelectColumn',
            'click .pcat-btn-unselect-col': '_onUnselectColumn',
            'click .pcat-btn-tier-left': '_onTierMoveLeft',
            'click .pcat-btn-tier-right': '_onTierMoveRight',
            'click .pcat-btn-resequence': '_onResequenceByTier',
            'click .pcat-move-chip': '_onTapMoveTier',
            'click .pcat-check': '_onCheckClick',
            'click .pcat-row': '_onRowClick',
            'click .pcat-crumb-tournament': '_onBackToTournament',
            'keydown': '_onKeyDown',
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var ctx = (action && action.context) || {};
            var params = (action && action.params) || {};
            this.tournamentId = params.tournament_id || ctx.tournament_id || false;
            this.data = null;
            this.search = '';
            this.selectedIds = {};
            this._anchorId = null;
            this._focusId = null;
            this._dragPlayerIds = [];
            this._dragFromTierKey = null;
            this._pendingIconDrop = null;
            this._selectedTeamId = null;
            this._skipNextRowClick = false;
        },

        start: function () {
            var self = this;
            var result = this._super.apply(this, arguments);
            this.$el.html(
                '<div class="pcat-loading"><strong>Loading Player Categorization…</strong></div>'
            );
            return Promise.resolve(result).then(function () {
                return self._load();
            });
        },

        _rpcBoard: function (method, args) {
            return this._rpc({
                model: 'auction.tournament',
                method: method,
                args: args,
            });
        },

        /**
         * Odoo 15 AbstractAction may not expose do_warn / do_notify.
         * Prefer notification service, then legacy helpers, then inline banner.
         */
        _notify: function (title, message, type) {
            type = type || 'warning';
            var sticky = type === 'danger';
            try {
                if (typeof this.displayNotification === 'function') {
                    this.displayNotification({
                        title: title,
                        message: message,
                        type: type,
                        sticky: sticky,
                    });
                    return;
                }
            } catch (e0) { /* */ }
            try {
                if (this.call) {
                    this.call('notification', 'notify', {
                        title: title,
                        message: message,
                        type: type,
                        sticky: sticky,
                    });
                    return;
                }
            } catch (e1) { /* */ }
            try {
                if ((type === 'danger' || type === 'warning') &&
                    typeof this.do_warn === 'function') {
                    this.do_warn(title, message);
                    return;
                }
                if (typeof this.do_notify === 'function') {
                    this.do_notify(title, message);
                    return;
                }
            } catch (e2) { /* */ }
            var cls = type === 'danger' ? 'pcat-toast-err' :
                (type === 'success' ? 'pcat-toast-ok' : 'pcat-toast-warn');
            var $toast = this.$el.find('.pcat-toast');
            if (!$toast.length) {
                this.$el.prepend('<div class="pcat-toast" role="status"></div>');
                $toast = this.$el.find('.pcat-toast');
            }
            $toast
                .attr('class', 'pcat-toast ' + cls)
                .html('<strong>' + esc(title) + '</strong> ' + esc(message))
                .show();
            var self = this;
            clearTimeout(this._toastTimer);
            this._toastTimer = setTimeout(function () {
                self.$el.find('.pcat-toast').fadeOut(200);
            }, 4200);
        },

        _load: function () {
            var self = this;
            if (!this.tournamentId) {
                this.$el.html(
                    '<div class="pcat-loading"><strong>No tournament selected.</strong></div>'
                );
                return Promise.resolve();
            }
            return this._rpcBoard('categorization_bootstrap', [this.tournamentId])
                .then(function (data) {
                    self.data = data;
                    self._pruneSelection();
                    self._render();
                })
                .catch(function (err) {
                    console.error('[PlayerCategorization]', err);
                    var msg = (err && err.data && err.data.message) ||
                        (err && err.message) ||
                        'Could not load categorization board.';
                    self.$el.html(
                        '<div class="pcat-loading"><strong>Error</strong><div>' +
                        esc(msg) + '</div></div>'
                    );
                });
        },

        _pruneSelection: function () {
            var map = this._playerMap();
            var next = {};
            Object.keys(this.selectedIds || {}).forEach(function (k) {
                if (map[k]) {
                    next[k] = true;
                }
            });
            this.selectedIds = next;
        },

        _selectedList: function () {
            var self = this;
            return Object.keys(this.selectedIds || {}).map(function (k) {
                return parseInt(k, 10);
            }).filter(function (id) {
                return !!self._getPlayer(id);
            });
        },

        _selectionCount: function () {
            return this._selectedList().length;
        },

        _isSelected: function (id) {
            return !!this.selectedIds[String(id)];
        },

        _setSelected: function (id, on) {
            if (on) {
                this.selectedIds[String(id)] = true;
            } else {
                delete this.selectedIds[String(id)];
            }
        },

        _toggleSelected: function (id) {
            this._setSelected(id, !this._isSelected(id));
        },

        _selectOnly: function (id) {
            this.selectedIds = {};
            this._setSelected(id, true);
            this._anchorId = id;
            this._focusId = id;
        },

        _clearSelection: function () {
            this.selectedIds = {};
            this._anchorId = null;
            this._focusId = null;
        },

        _visibleIdsInColumn: function (tierKey) {
            var col = null;
            this._columns().forEach(function (c) {
                if (c.key === tierKey) {
                    col = c;
                }
            });
            if (!col) {
                return [];
            }
            return this._filteredIds(col.player_ids || []);
        },

        _columnKeyForPlayer: function (playerId) {
            var cols = this._columns();
            for (var i = 0; i < cols.length; i++) {
                if ((cols[i].player_ids || []).indexOf(playerId) !== -1) {
                    return cols[i].key;
                }
            }
            return null;
        },

        _selectRangeInColumn: function (anchorId, focusId) {
            var key = this._columnKeyForPlayer(anchorId) ||
                this._columnKeyForPlayer(focusId);
            if (!key) {
                return;
            }
            if (this._columnKeyForPlayer(focusId) &&
                this._columnKeyForPlayer(focusId) !== key) {
                return;
            }
            var ids = this._visibleIdsInColumn(key);
            var a = ids.indexOf(anchorId);
            var b = ids.indexOf(focusId);
            if (a < 0 || b < 0) {
                return;
            }
            var from = Math.min(a, b);
            var to = Math.max(a, b);
            this.selectedIds = {};
            for (var i = from; i <= to; i++) {
                this._setSelected(ids[i], true);
            }
            this._anchorId = anchorId;
            this._focusId = focusId;
        },

        _ensureFocusDefaults: function () {
            if (this._focusId && this._getPlayer(this._focusId)) {
                return;
            }
            var selected = this._selectedList();
            if (selected.length) {
                this._focusId = selected[selected.length - 1];
                this._anchorId = this._anchorId || selected[0];
                return;
            }
            var cols = this._columns();
            for (var i = 0; i < cols.length; i++) {
                var ids = this._filteredIds(cols[i].player_ids || []);
                if (ids.length) {
                    this._focusId = ids[0];
                    this._anchorId = ids[0];
                    return;
                }
            }
        },

        _moveFocus: function (delta, extend) {
            this._ensureFocusDefaults();
            if (!this._focusId) {
                return;
            }
            var key = this._columnKeyForPlayer(this._focusId);
            if (!key) {
                return;
            }
            var ids = this._visibleIdsInColumn(key);
            var idx = ids.indexOf(this._focusId);
            if (idx < 0) {
                return;
            }
            var next = idx + delta;
            if (next < 0 || next >= ids.length) {
                return;
            }
            var nextId = ids[next];
            if (extend) {
                if (!this._anchorId || this._columnKeyForPlayer(this._anchorId) !== key) {
                    this._anchorId = this._focusId;
                }
                this._selectRangeInColumn(this._anchorId, nextId);
            } else {
                this._selectOnly(nextId);
            }
            this._paintSelection();
            this._scrollFocusIntoView();
        },

        _scrollFocusIntoView: function () {
            if (!this._focusId) {
                return;
            }
            var el = this.el.querySelector(
                '.pcat-row[data-player-id="' + this._focusId + '"]'
            );
            if (el && el.scrollIntoView) {
                el.scrollIntoView({block: 'nearest', inline: 'nearest'});
            }
        },

        _onKeyDown: function (ev) {
            var tag = (ev.target && ev.target.tagName) || '';
            if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
                return;
            }
            if (ev.key !== 'ArrowDown' && ev.key !== 'ArrowUp' &&
                ev.keyCode !== 40 && ev.keyCode !== 38) {
                return;
            }
            var down = ev.key === 'ArrowDown' || ev.keyCode === 40;
            ev.preventDefault();
            ev.stopPropagation();
            this._moveFocus(down ? 1 : -1, !!ev.shiftKey);
        },

        _focusShell: function () {
            var shell = this.el && this.el.querySelector('.pcat-shell');
            if (shell && shell.focus) {
                try {
                    shell.focus({preventScroll: true});
                } catch (e) {
                    shell.focus();
                }
            }
        },

        _playerMap: function () {
            return (this.data && this.data.players) || {};
        },

        _getPlayer: function (id) {
            return this._playerMap()[String(id)] || null;
        },

        _columns: function () {
            var data = this.data || {};
            var cols = [];
            // Tiers already sorted by sequence from bootstrap
            (data.tiers || []).forEach(function (t) {
                cols.push({
                    key: 'tier-' + t.id,
                    tier_id: t.id,
                    name: t.name,
                    color: t.color || '#3498db',
                    sequence: t.sequence || 0,
                    is_icon: !!t.is_an_icon_tier,
                    mystery: !!t.mystery,
                    player_ids: t.player_ids || [],
                });
            });
            var un = data.unassigned || {};
            cols.push({
                key: 'unassigned',
                tier_id: false,
                name: 'Unassigned',
                color: '#7f8c8d',
                sequence: 999999,
                is_icon: false,
                mystery: false,
                player_ids: un.player_ids || [],
            });
            return cols;
        },

        _tierIdsOrdered: function () {
            return this._columns()
                .filter(function (c) { return !!c.tier_id; })
                .map(function (c) { return c.tier_id; });
        },

        _currentColumnOrders: function () {
            return this._columns().map(function (col) {
                return {
                    tier_id: col.tier_id || false,
                    player_ids: (col.player_ids || []).slice(),
                };
            });
        },

        _filteredIds: function (ids) {
            var self = this;
            var q = (this.search || '').trim().toLowerCase();
            if (!q) {
                return ids.slice();
            }
            return ids.filter(function (id) {
                var p = self._getPlayer(id);
                if (!p) {
                    return false;
                }
                var hay = [
                    p.name, p.role_label, p.team_name, String(p.sl_no || ''),
                ].join(' ').toLowerCase();
                return hay.indexOf(q) !== -1;
            });
        },

        _render: function () {
            if (!this.data) {
                return;
            }
            var t = this.data.tournament || {};
            var sport = t.tournament_type || 'cricket';
            var roleHdr = sport === 'football' ? 'Position' : 'Role';
            var selCount = this._selectionCount();
            var html = '';
            html += '<div class="pcat-shell" tabindex="0">';
            html += '<nav class="pcat-breadcrumb" aria-label="Breadcrumb">';
            html += '<a href="#" class="pcat-crumb-tournament" title="Back to tournament">' +
                '<i class="fa fa-arrow-left"></i> ' +
                esc(t.name || 'Tournament') + '</a>';
            html += '<span class="pcat-crumb-sep">/</span>';
            html += '<span class="pcat-crumb-current">Player Categorization</span>';
            html += '</nav>';
            html += '<header class="pcat-header">';
            html += '<div class="pcat-header-left">';
            html += '<div class="pcat-kicker">Player Categorization</div>';
            html += '<h1 class="pcat-title">' + esc(t.name || 'Tournament') + '</h1>';
            html += '</div>';
            html += '<div class="pcat-header-actions">';
            html += '<input type="search" class="pcat-search" placeholder="Search…" value="' +
                esc(this.search) + '"/>';
            if (selCount) {
                html += '<span class="pcat-sel-badge">' + selCount + ' selected</span>';
                html += '<button type="button" class="pcat-btn pcat-btn-clear-sel">' +
                    '<span class="pcat-lbl-full">Unselect All</span>' +
                    '<span class="pcat-lbl-short">Clear</span></button>';
            }
            html += '<button type="button" class="pcat-btn pcat-btn-resequence" title="Renumber auction serials by tier order (left→right, top→bottom)">' +
                '<span class="pcat-lbl-full">Resequence by Tier</span>' +
                '<span class="pcat-lbl-short">Reseq</span></button>';
            html += '<button type="button" class="pcat-btn pcat-btn-refresh">' +
                '<span class="pcat-lbl-full">Refresh</span>' +
                '<span class="pcat-lbl-short">↻</span></button>';
            html += '<button type="button" class="pcat-btn pcat-btn-primary pcat-btn-new-tier">' +
                '<span class="pcat-lbl-full">+ New Tier</span>' +
                '<span class="pcat-lbl-short">+ Tier</span></button>';
            html += '</div></header>';
            html += '<div class="pcat-hint">' +
                '<span class="pcat-hint-desk">Reorder tiers with ◀ ▶ · Drag players within/between tiers · </span>' +
                '<span class="pcat-hint-mob">Select players, tap a tier below to move · Use ▲ ▼ to order tiers · </span>' +
                '<strong>Resequence by Tier</strong> sets auction serials (' +
                esc(roleHdr) + ')</div>';
            html += this._renderMoveBar();
            html += '<div class="pcat-board">';
            var cols = this._columns();
            var self = this;
            cols.forEach(function (col) {
                html += self._renderColumn(col, roleHdr);
            });
            html += '</div>';
            html += this._renderNewTierDialog(t);
            html += this._renderTeamModal();
            html += '</div>';
            this.$el.html(html);
            this._bindDnD();
            this._paintSelection();
            this._focusShell();
        },

        _renderMoveBar: function () {
            var selCount = this._selectionCount();
            var html = '<div class="pcat-move-bar' + (selCount ? '' : ' pcat-move-bar-empty') +
                '" aria-label="Move selected players">';
            if (!selCount) {
                html += '<div class="pcat-move-bar-idle">Select players, then tap a destination tier</div>';
                html += '</div>';
                return html;
            }
            html += '<div class="pcat-move-bar-label">' + selCount + ' →</div>';
            html += '<div class="pcat-move-bar-chips">';
            this._columns().forEach(function (col) {
                html += '<button type="button" class="pcat-move-chip' +
                    (col.is_icon ? ' pcat-move-chip-icon' : '') +
                    '" data-tier-id="' + esc(col.tier_id === false ? '' : col.tier_id) +
                    '" data-is-icon="' + (col.is_icon ? '1' : '0') +
                    '" style="--pcat-tier:' + esc(col.color) + '" title="Move to ' +
                    esc(col.name) + '">';
                if (col.is_icon) {
                    html += '<i class="fa fa-star"></i> ';
                }
                html += esc(col.name) + '</button>';
            });
            html += '</div></div>';
            return html;
        },

        _renderColumn: function (col, roleHdr) {
            var ids = this._filteredIds(col.player_ids || []);
            var tierIds = this._tierIdsOrdered();
            var tierPos = col.tier_id ? tierIds.indexOf(col.tier_id) : -1;
            var html = '';
            html += '<section class="pcat-col' + (col.is_icon ? ' pcat-col-icon' : '') +
                (col.mystery ? ' pcat-col-mystery' : '') +
                '" data-tier-key="' + esc(col.key) + '" data-tier-id="' +
                esc(col.tier_id === false ? '' : col.tier_id) +
                '" data-is-icon="' + (col.is_icon ? '1' : '0') + '">';
            html += '<div class="pcat-col-head" style="--pcat-tier:' + esc(col.color) + '">';
            html += '<div class="pcat-col-head-left">';
            if (col.tier_id) {
                html += '<div class="pcat-tier-order">';
                html += '<button type="button" class="pcat-btn-tier-left" data-tier-id="' +
                    col.tier_id + '" title="Move tier earlier"' +
                    (tierPos <= 0 ? ' disabled="disabled"' : '') + '>' +
                    '<span class="pcat-tier-dir-h">◀</span>' +
                    '<span class="pcat-tier-dir-v">▲</span></button>';
                html += '<span class="pcat-tier-seq" title="Auction tier order">#' +
                    (tierPos + 1) + '</span>';
                html += '<button type="button" class="pcat-btn-tier-right" data-tier-id="' +
                    col.tier_id + '" title="Move tier later"' +
                    (tierPos < 0 || tierPos >= tierIds.length - 1 ? ' disabled="disabled"' : '') +
                    '><span class="pcat-tier-dir-h">▶</span>' +
                    '<span class="pcat-tier-dir-v">▼</span></button>';
                html += '</div>';
            }
            html += '<span class="pcat-col-name">' +
                (col.is_icon ? '<i class="fa fa-star"></i> ' : '') +
                (col.mystery ? '<i class="fa fa-eye-slash" title="Mystery"></i> ' : '') +
                esc(col.name) + '</span>';
            html += '</div>';
            html += '<div class="pcat-col-head-right">';
            if (ids.length) {
                html += '<button type="button" class="pcat-btn-select-col" data-tier-key="' +
                    esc(col.key) + '" title="Select all in this tier">' +
                    '<span class="pcat-lbl-full">Select All</span>' +
                    '<span class="pcat-lbl-short">All</span></button>';
                html += '<button type="button" class="pcat-btn-unselect-col" data-tier-key="' +
                    esc(col.key) + '" title="Unselect all in this tier">' +
                    '<span class="pcat-lbl-full">Unselect All</span>' +
                    '<span class="pcat-lbl-short">None</span></button>';
            }
            html += '<span class="pcat-col-count">' + ids.length + '</span>';
            html += '</div></div>';
            html += '<div class="pcat-col-body" data-drop-zone="1">';
            var self = this;
            if (!ids.length) {
                html += '<div class="pcat-empty-drop">' +
                    '<span class="pcat-hint-desk">Drop players here</span>' +
                    '<span class="pcat-hint-mob">Tap Move bar to add players</span>' +
                    '</div>';
            }
            ids.forEach(function (pid) {
                html += self._renderPlayerRow(pid, roleHdr);
            });
            html += '</div></section>';
            return html;
        },

        _renderPlayerRow: function (pid, roleHdr) {
            var p = this._getPlayer(pid);
            if (!p) {
                return '';
            }
            var selected = this._isSelected(pid);
            var focused = this._focusId === pid;
            var canDrag = !(window.matchMedia &&
                window.matchMedia('(pointer: coarse)').matches);
            var html = '<article class="pcat-row' +
                (selected ? ' pcat-selected' : '') +
                (focused ? ' pcat-focus' : '') +
                '" draggable="' + (canDrag ? 'true' : 'false') +
                '" data-player-id="' + p.id +
                '" title="' + (canDrag
                    ? 'Click / Ctrl+click · Drag · '
                    : 'Tap to select · Use Move bar · ') +
                esc(roleHdr) + ': ' + esc(p.role_label || '—') + '">';
            html += '<label class="pcat-check-wrap" title="Select">' +
                '<input type="checkbox" class="pcat-check" ' +
                (selected ? 'checked="checked" ' : '') +
                'data-player-id="' + p.id + '"/>' +
                '</label>';
            html += '<span class="pcat-sl">#' + esc(p.sl_no || '—') + '</span>';
            html += '<img class="pcat-photo" src="' + esc(p.photo_url) +
                '" alt="" onerror="this.style.visibility=\'hidden\'"/>';
            html += '<div class="pcat-meta">';
            html += '<div class="pcat-name">' + esc(p.name) + '</div>';
            html += '<div class="pcat-sub">';
            html += '<span class="pcat-role">' + esc(p.role_label || '—') + '</span>';
            if (p.icon_player && p.team_name) {
                html += '<span class="pcat-team-chip">' + esc(p.team_name) + '</span>';
            }
            html += '</div></div>';
            html += '<span class="pcat-grip" aria-hidden="true">⋮⋮</span>';
            html += '</article>';
            return html;
        },

        _renderNewTierDialog: function (t) {
            var colors = this.data.tier_colors || [];
            var html = '<div class="pcat-tier-dialog" hidden>';
            html += '<div class="pcat-tier-dialog-card">';
            html += '<h2>Create New Tier</h2>';
            html += '<label>Name<input type="text" class="pcat-tier-name" maxlength="64" placeholder="e.g. A Grade"/></label>';
            html += '<label>Color<select class="pcat-tier-color">';
            colors.forEach(function (c) {
                html += '<option value="' + esc(c) + '" style="background:' + esc(c) + '">' +
                    esc(c) + '</option>';
            });
            html += '</select></label>';
            html += '<div class="pcat-tier-flags">';
            if (!(t && t.has_icon_tier)) {
                html += '<label class="pcat-tier-icon-lbl">' +
                    '<input type="checkbox" class="pcat-tier-icon"/> Icon Tier</label>';
            }
            html += '<label class="pcat-tier-icon-lbl">' +
                '<input type="checkbox" class="pcat-tier-mystery"/> Mystery</label>';
            html += '</div>';
            html += '<p class="pcat-tier-hint">Mystery hides player identity on the live stage until sold.</p>';
            html += '<div class="pcat-tier-actions">';
            html += '<button type="button" class="pcat-btn pcat-tier-cancel">Cancel</button>';
            html += '<button type="button" class="pcat-btn pcat-btn-primary pcat-tier-save">Create</button>';
            html += '</div></div></div>';
            return html;
        },

        _renderTeamModal: function () {
            var teams = (this.data && this.data.teams) || [];
            var pending = this._pendingIconDrop;
            var n = pending && pending.player_ids ? pending.player_ids.length : 1;
            var html = '<div class="pcat-modal" hidden>';
            html += '<div class="pcat-modal-backdrop"></div>';
            html += '<div class="pcat-modal-card">';
            html += '<h2>Assign to Team</h2>';
            html += '<p class="pcat-modal-desc">Icon players must be assigned to a team' +
                (n > 1 ? ' — <strong>' + n + ' players</strong> will join the same team.' : '.') +
                '</p>';
            html += '<div class="pcat-team-grid">';
            if (!teams.length) {
                html += '<div class="pcat-empty-drop">No teams in this tournament. Create teams first.</div>';
            }
            teams.forEach(function (team) {
                html += '<button type="button" class="pcat-team-card" data-team-id="' +
                    team.id + '">';
                html += '<img src="' + esc(team.logo_url) + '" alt="" onerror="this.style.display=\'none\'"/>';
                html += '<span>' + esc(team.name) + '</span>';
                html += '</button>';
            });
            html += '</div>';
            html += '<div class="pcat-tier-actions">';
            html += '<button type="button" class="pcat-btn pcat-modal-cancel">Cancel</button>';
            html += '<button type="button" class="pcat-btn pcat-btn-primary pcat-modal-confirm" disabled>Confirm</button>';
            html += '</div></div></div>';
            return html;
        },

        _dragIdsForStart: function (anchorId) {
            var selected = this._selectedList();
            if (selected.length && this._isSelected(anchorId)) {
                return selected.slice();
            }
            return [anchorId];
        },

        _bindDnD: function () {
            var self = this;
            this.$el.find('.pcat-row').each(function () {
                var el = this;
                el.addEventListener('dragstart', function (ev) {
                    var pid = parseInt(el.getAttribute('data-player-id'), 10);
                    var ids = self._dragIdsForStart(pid);
                    // If dragging an unselected row, select only it
                    if (!self._isSelected(pid)) {
                        self._selectOnly(pid);
                        ids = [pid];
                        self._paintSelection();
                    }
                    self._dragPlayerIds = ids;
                    var col = el.closest('.pcat-col');
                    self._dragFromTierKey = col ? col.getAttribute('data-tier-key') : null;
                    el.classList.add('pcat-dragging');
                    ids.forEach(function (id) {
                        self.$el.find('.pcat-row[data-player-id="' + id + '"]')
                            .addClass('pcat-dragging-group');
                    });
                    try {
                        ev.dataTransfer.setData('text/plain', ids.join(','));
                        ev.dataTransfer.effectAllowed = 'move';
                    } catch (e) { /* IE */ }
                    if (ids.length > 1) {
                        try {
                            var ghost = document.createElement('div');
                            ghost.className = 'pcat-drag-ghost';
                            ghost.textContent = ids.length + ' players';
                            ghost.style.position = 'absolute';
                            ghost.style.top = '-1000px';
                            document.body.appendChild(ghost);
                            ev.dataTransfer.setDragImage(ghost, 40, 20);
                            setTimeout(function () {
                                if (ghost.parentNode) {
                                    ghost.parentNode.removeChild(ghost);
                                }
                            }, 0);
                        } catch (e2) { /* */ }
                    }
                });
                el.addEventListener('dragend', function () {
                    self.$el.find('.pcat-row').removeClass('pcat-dragging pcat-dragging-group');
                    self.$el.find('.pcat-col-body').removeClass('pcat-drag-over');
                    self._dragPlayerIds = [];
                    self._dragFromTierKey = null;
                });
            });
            this.$el.find('.pcat-col-body').each(function () {
                var zone = this;
                zone.addEventListener('dragover', function (ev) {
                    ev.preventDefault();
                    zone.classList.add('pcat-drag-over');
                    try { ev.dataTransfer.dropEffect = 'move'; } catch (e) { /* */ }
                });
                zone.addEventListener('dragleave', function () {
                    zone.classList.remove('pcat-drag-over');
                });
                zone.addEventListener('drop', function (ev) {
                    ev.preventDefault();
                    zone.classList.remove('pcat-drag-over');
                    var ids = self._dragPlayerIds.slice();
                    if (!ids.length) {
                        try {
                            var raw = ev.dataTransfer.getData('text/plain') || '';
                            ids = raw.split(',').map(function (s) {
                                return parseInt(s, 10);
                            }).filter(function (n) { return !!n; });
                        } catch (e) { ids = []; }
                    }
                    if (!ids.length) {
                        return;
                    }
                    var col = zone.closest('.pcat-col');
                    var tierIdAttr = col.getAttribute('data-tier-id');
                    var targetTierId = tierIdAttr === '' || tierIdAttr === null
                        ? false
                        : parseInt(tierIdAttr, 10);
                    var isIcon = col.getAttribute('data-is-icon') === '1';
                    var index = self._dropIndex(zone, ev.clientY, ids);
                    self._requestMoveToTier(ids, targetTierId, index, isIcon);
                });
            });
        },

        _requestMoveToTier: function (ids, targetTierId, index, isIcon) {
            var self = this;
            ids = (ids || []).slice();
            if (!ids.length) {
                return;
            }
            if (typeof index !== 'number' || index < 0) {
                index = 99999;
            }
            if (isIcon) {
                var allIconSame = ids.every(function (id) {
                    var p = self._getPlayer(id);
                    return p && p.icon_player && p.team_id && p.tier_id === targetTierId;
                });
                if (allIconSame) {
                    self._commitMove(ids, targetTierId, index, null);
                    return;
                }
                self._pendingIconDrop = {
                    player_ids: ids,
                    target_tier_id: targetTierId,
                    index: index,
                };
                var first = self._getPlayer(ids[0]);
                self._selectedTeamId = (first && first.team_id) || null;
                self.$el.find('.pcat-modal').remove();
                self.$el.find('.pcat-shell').append(self._renderTeamModal());
                self.$el.find('.pcat-modal').prop('hidden', false);
                self.$el.find('.pcat-team-card').removeClass('pcat-team-selected');
                if (self._selectedTeamId) {
                    self.$el.find('.pcat-team-card[data-team-id="' +
                        self._selectedTeamId + '"]').addClass('pcat-team-selected');
                    self.$el.find('.pcat-modal-confirm').prop('disabled', false);
                } else {
                    self.$el.find('.pcat-modal-confirm').prop('disabled', true);
                }
                return;
            }
            self._commitMove(ids, targetTierId, index, null);
        },

        _onTapMoveTier: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var ids = this._selectedList();
            if (!ids.length) {
                this._notify('Move', 'Select one or more players first.', 'warning');
                return;
            }
            var btn = ev.currentTarget;
            var tierIdAttr = btn.getAttribute('data-tier-id');
            var targetTierId = tierIdAttr === '' || tierIdAttr === null
                ? false
                : parseInt(tierIdAttr, 10);
            var isIcon = btn.getAttribute('data-is-icon') === '1';
            this._requestMoveToTier(ids, targetTierId, 99999, isIcon);
        },

        _refreshMoveBar: function () {
            var $bar = this.$el.find('.pcat-move-bar');
            if (!$bar.length) {
                return;
            }
            $bar.replaceWith(this._renderMoveBar());
        },

        _paintSelection: function () {
            var self = this;
            this.$el.find('.pcat-row').each(function () {
                var id = parseInt(this.getAttribute('data-player-id'), 10);
                var on = self._isSelected(id);
                this.classList.toggle('pcat-selected', on);
                this.classList.toggle('pcat-focus', self._focusId === id);
                var cb = this.querySelector('.pcat-check');
                if (cb) {
                    cb.checked = on;
                }
            });
            var n = this._selectionCount();
            var $badge = this.$el.find('.pcat-sel-badge');
            var $clear = this.$el.find('.pcat-btn-clear-sel');
            if (n) {
                if ($badge.length) {
                    $badge.text(n + ' selected');
                } else {
                    this.$el.find('.pcat-search').after(
                        '<span class="pcat-sel-badge">' + n + ' selected</span>' +
                        '<button type="button" class="pcat-btn pcat-btn-clear-sel">' +
                        '<span class="pcat-lbl-full">Unselect All</span>' +
                        '<span class="pcat-lbl-short">Clear</span></button>'
                    );
                }
            } else {
                $badge.remove();
                $clear.remove();
            }
            this._refreshMoveBar();
        },

        _dropIndex: function (zone, clientY, dragIds) {
            var skip = {};
            (dragIds || []).forEach(function (id) { skip[id] = true; });
            var rows = Array.prototype.slice.call(
                zone.querySelectorAll('.pcat-row')
            ).filter(function (row) {
                var id = parseInt(row.getAttribute('data-player-id'), 10);
                return !skip[id];
            });
            var idx = rows.length;
            for (var i = 0; i < rows.length; i++) {
                var rect = rows[i].getBoundingClientRect();
                var mid = rect.top + rect.height / 2;
                if (clientY < mid) {
                    idx = i;
                    break;
                }
            }
            return idx;
        },

        _buildColumnOrders: function (playerIds, targetTierId, index) {
            var moveSet = {};
            (playerIds || []).forEach(function (id) { moveSet[id] = true; });
            var cols = this._columns();
            var orders = [];
            var placed = false;
            cols.forEach(function (col) {
                var ids = (col.player_ids || []).filter(function (id) {
                    return !moveSet[id];
                });
                var isTarget = (col.tier_id || false) === (targetTierId || false);
                if (isTarget) {
                    var pos = Math.max(0, Math.min(index, ids.length));
                    ids = ids.slice(0, pos).concat(playerIds).concat(ids.slice(pos));
                    placed = true;
                }
                orders.push({
                    tier_id: col.tier_id || false,
                    player_ids: ids,
                });
            });
            if (!placed) {
                orders.push({
                    tier_id: targetTierId || false,
                    player_ids: playerIds.slice(),
                });
            }
            return orders;
        },

        _commitMove: function (playerIds, targetTierId, index, teamId) {
            var self = this;
            if (!Array.isArray(playerIds)) {
                playerIds = playerIds ? [playerIds] : [];
            }
            if (!playerIds.length) {
                return Promise.resolve();
            }
            var columnOrders = this._buildColumnOrders(playerIds, targetTierId, index);
            this.$el.addClass('pcat-busy');
            return this._rpcBoard('categorization_move_players', [
                this.tournamentId,
                playerIds,
                targetTierId || false,
                index,
                teamId || false,
                columnOrders,
            ]).then(function (data) {
                self.data = data;
                self._pendingIconDrop = null;
                self._selectedTeamId = null;
                self._clearSelection();
                self._render();
            }).catch(function (err) {
                console.error('[PlayerCategorization] move', err);
                var msg = (err && err.data && err.data.message) ||
                    (err && err.message) ||
                    'Move failed.';
                self._notify('Player Categorization', msg, 'danger');
                return self._load();
            }).then(function () {
                self.$el.removeClass('pcat-busy');
            });
        },

        _onCheckClick: function (ev) {
            ev.stopPropagation();
            var pid = parseInt(ev.currentTarget.getAttribute('data-player-id'), 10);
            this._toggleSelected(pid);
            this._focusId = pid;
            if (this._isSelected(pid) && !this._anchorId) {
                this._anchorId = pid;
            }
            if (!this._isSelected(pid) && this._anchorId === pid) {
                var remaining = this._selectedList();
                this._anchorId = remaining.length ? remaining[0] : null;
            }
            this._paintSelection();
            this._skipNextRowClick = true;
            this._focusShell();
        },

        _onRowClick: function (ev) {
            if (this._skipNextRowClick) {
                this._skipNextRowClick = false;
                return;
            }
            if (ev.target.closest && ev.target.closest('.pcat-check-wrap')) {
                return;
            }
            var row = ev.currentTarget;
            var pid = parseInt(row.getAttribute('data-player-id'), 10);
            if (ev.ctrlKey || ev.metaKey) {
                this._toggleSelected(pid);
                this._focusId = pid;
                if (this._isSelected(pid)) {
                    this._anchorId = this._anchorId || pid;
                }
            } else if (ev.shiftKey && this._anchorId) {
                this._selectRangeInColumn(this._anchorId, pid);
            } else {
                if (!(this._isSelected(pid) && this._selectionCount() > 1)) {
                    this._selectOnly(pid);
                } else {
                    this._focusId = pid;
                    this._anchorId = pid;
                }
            }
            this._paintSelection();
            this._focusShell();
        },

        _onClearSelection: function () {
            this._clearSelection();
            this._paintSelection();
        },

        _onSelectColumn: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var key = ev.currentTarget.getAttribute('data-tier-key');
            var col = null;
            this._columns().forEach(function (c) {
                if (c.key === key) {
                    col = c;
                }
            });
            if (!col) {
                return;
            }
            var self = this;
            var ids = this._filteredIds(col.player_ids || []);
            ids.forEach(function (id) {
                self._setSelected(id, true);
            });
            if (ids.length) {
                this._anchorId = ids[0];
                this._focusId = ids[ids.length - 1];
            }
            this._paintSelection();
            this._focusShell();
        },

        _onUnselectColumn: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var key = ev.currentTarget.getAttribute('data-tier-key');
            var col = null;
            this._columns().forEach(function (c) {
                if (c.key === key) {
                    col = c;
                }
            });
            if (!col) {
                return;
            }
            var self = this;
            this._filteredIds(col.player_ids || []).forEach(function (id) {
                self._setSelected(id, false);
            });
            if (this._focusId && !this._isSelected(this._focusId)) {
                var remaining = this._selectedList();
                this._focusId = remaining.length ? remaining[remaining.length - 1] : null;
                this._anchorId = remaining.length ? remaining[0] : null;
            }
            this._paintSelection();
            this._focusShell();
        },

        _onBackToTournament: function (ev) {
            ev.preventDefault();
            if (!this.tournamentId) {
                return;
            }
            this.do_action({
                type: 'ir.actions.act_window',
                name: 'Tournament',
                res_model: 'auction.tournament',
                res_id: this.tournamentId,
                views: [[false, 'form']],
                view_mode: 'form',
                target: 'current',
                context: {
                    active_id: this.tournamentId,
                },
            });
        },

        _swapTier: function (tierId, direction) {
            var ids = this._tierIdsOrdered();
            var idx = ids.indexOf(tierId);
            var swapWith = idx + direction;
            if (idx < 0 || swapWith < 0 || swapWith >= ids.length) {
                return Promise.resolve();
            }
            var tmp = ids[idx];
            ids[idx] = ids[swapWith];
            ids[swapWith] = tmp;
            var self = this;
            this.$el.addClass('pcat-busy');
            return this._rpcBoard('categorization_reorder_tiers', [
                this.tournamentId, ids,
            ]).then(function (data) {
                self.data = data;
                self._pruneSelection();
                self._render();
            }).catch(function (err) {
                var msg = (err && err.data && err.data.message) ||
                    (err && err.message) ||
                    'Could not reorder tiers.';
                self._notify('Tier Order', msg, 'danger');
                return self._load();
            }).then(function () {
                self.$el.removeClass('pcat-busy');
            });
        },

        _onTierMoveLeft: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var tid = parseInt(ev.currentTarget.getAttribute('data-tier-id'), 10);
            if (tid) {
                this._swapTier(tid, -1);
            }
        },

        _onTierMoveRight: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var tid = parseInt(ev.currentTarget.getAttribute('data-tier-id'), 10);
            if (tid) {
                this._swapTier(tid, 1);
            }
        },

        _onResequenceByTier: function (ev) {
            ev.preventDefault();
            var self = this;
            var columnOrders = this._currentColumnOrders();
            this.$el.addClass('pcat-busy');
            return this._rpcBoard('categorization_resequence_by_tiers', [
                this.tournamentId, columnOrders,
            ]).then(function (data) {
                var count = (data && data.resequence_count) || 0;
                self.data = data;
                self._pruneSelection();
                self._render();
                self._notify(
                    'Resequence Complete',
                    count
                        ? (count + ' player serial(s) set from tier order (left → right).')
                        : 'No players to resequence.',
                    'success'
                );
            }).catch(function (err) {
                var msg = (err && err.data && err.data.message) ||
                    (err && err.message) ||
                    'Resequence failed.';
                self._notify('Resequence', msg, 'danger');
                return self._load();
            }).then(function () {
                self.$el.removeClass('pcat-busy');
            });
        },

        _onRefresh: function () {
            this._load();
        },

        _onSearch: function (ev) {
            this.search = (ev.target && ev.target.value) || '';
            this._render();
            this.$el.find('.pcat-search').val(this.search).focus();
            var input = this.$el.find('.pcat-search')[0];
            if (input) {
                var len = this.search.length;
                try { input.setSelectionRange(len, len); } catch (e) { /* */ }
            }
        },

        _onOpenNewTier: function () {
            this.$el.find('.pcat-tier-dialog').prop('hidden', false);
            this.$el.find('.pcat-tier-name').val('').focus();
        },

        _onCloseNewTier: function () {
            this.$el.find('.pcat-tier-dialog').prop('hidden', true);
        },

        _onSaveNewTier: function () {
            var self = this;
            var name = (this.$el.find('.pcat-tier-name').val() || '').trim();
            var color = this.$el.find('.pcat-tier-color').val() || '#3498db';
            var isIcon = this.$el.find('.pcat-tier-icon').is(':checked');
            var isMystery = this.$el.find('.pcat-tier-mystery').is(':checked');
            if (!name) {
                this._notify('New Tier', 'Please enter a tier name.', 'warning');
                return;
            }
            this.$el.addClass('pcat-busy');
            this._rpcBoard('categorization_create_tier', [
                this.tournamentId, name, color, isIcon, isMystery,
            ]).then(function (data) {
                self.data = data;
                self._render();
                self._notify(
                    'Tier Created',
                    '"' + name + '" is ready for assignments.',
                    'success'
                );
            }).catch(function (err) {
                var msg = (err && err.data && err.data.message) ||
                    (err && err.message) ||
                    'Could not create tier.';
                self._notify('New Tier', msg, 'danger');
            }).then(function () {
                self.$el.removeClass('pcat-busy');
            });
        },

        _onCloseTeamModal: function () {
            this._pendingIconDrop = null;
            this._selectedTeamId = null;
            this.$el.find('.pcat-modal').prop('hidden', true);
        },

        _onPickTeam: function (ev) {
            var btn = ev.currentTarget;
            var tid = parseInt(btn.getAttribute('data-team-id'), 10);
            this._selectedTeamId = tid;
            this.$el.find('.pcat-team-card').removeClass('pcat-team-selected');
            btn.classList.add('pcat-team-selected');
            this.$el.find('.pcat-modal-confirm').prop('disabled', false);
        },

        _onConfirmTeam: function () {
            var pending = this._pendingIconDrop;
            var teamId = this._selectedTeamId;
            if (!pending || !teamId) {
                return;
            }
            this.$el.find('.pcat-modal').prop('hidden', true);
            this._commitMove(
                pending.player_ids || (pending.player_id ? [pending.player_id] : []),
                pending.target_tier_id,
                pending.index,
                teamId
            );
        },
    });

    core.action_registry.add('auction_module.player_categorization', PlayerCategorization);
    return PlayerCategorization;
});
