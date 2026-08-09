odoo.define('auction_module.SwapPlayerBoardWidget', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');

    /**
     * Custom board for auction.swap.player.
     * Team clicks reload players via RPC.
     * Player clicks select locally (no team re-write) and unlock points fields.
     */
    var SwapPlayerBoardWidget = AbstractField.extend({
        className: 'o_field_swap_player_board',
        supportedFieldTypes: ['text', 'char'],
        events: {
            'click .ac-swap-team-chip': '_onTeamClick',
            'click .ac-swap-player-card': '_onPlayerClick',
            'keydown .ac-swap-team-chip': '_onTeamKeydown',
            'keydown .ac-swap-player-card': '_onPlayerKeydown',
        },

        reset: function (record, event) {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._render();
            });
        },

        _getPayload: function () {
            var raw = this.value;
            if ((raw == null || raw === '') && this.recordData && this.recordData.board_json != null) {
                raw = this.recordData.board_json;
            }
            if (!raw) {
                return {teams: [], unit_label: 'Points', sport: 'cricket'};
            }
            try {
                return typeof raw === 'string' ? JSON.parse(raw) : raw;
            } catch (e) {
                return {teams: [], unit_label: 'Points', sport: 'cricket'};
            }
        },

        _getSourceAuctionId: function () {
            var auc = this.recordData && this.recordData.source_auction_id;
            if (!auc) {
                return 0;
            }
            if (typeof auc === 'object') {
                return auc.res_id || (auc.data && auc.data.id) || auc.id || 0;
            }
            return parseInt(auc, 10) || 0;
        },

        _getSourcePoints: function () {
            var pts = this.recordData && this.recordData.source_points;
            return parseInt(pts, 10) || 0;
        },

        _escape: function (value) {
            return _.escape(value == null ? '' : String(value));
        },

        _renderEdit: function () {
            this._renderBoard();
        },

        _renderReadonly: function () {
            this._renderBoard();
        },

        _markPlayerSelected: function (payload, lineId) {
            var selectedLineId = parseInt(lineId, 10) || 0;
            payload.selected_line_id = selectedLineId || false;
            _.each(payload.teams || [], function (team) {
                _.each(team.players || [], function (player) {
                    player.selected = Number(player.line_id) === selectedLineId;
                });
            });
            return payload;
        },

        _findPlayer: function (payload, lineId) {
            var selectedLineId = Number(lineId);
            var found = null;
            _.each(payload.teams || [], function (team) {
                _.each(team.players || [], function (player) {
                    if (Number(player.line_id) === selectedLineId) {
                        found = player;
                    }
                });
            });
            return found;
        },

        _renderBoard: function () {
            var data = this._getPayload();
            var teams = data.teams || [];
            var unit = this._escape(data.unit_label || 'Points');
            var sport = this._escape(data.sport || 'cricket');
            var selectedTeamId = data.selected_team_id || false;
            var html = [];

            html.push('<div class="ac-swap-board" data-sport="' + sport + '">');
            html.push('<div class="ac-swap-section-title">1. Choose target team</div>');
            html.push('<div class="ac-swap-teams">');

            if (!teams.length) {
                html.push('<div class="ac-swap-empty">No other teams in this tournament.</div>');
            } else {
                teams.forEach(function (team) {
                    var selected = team.selected || (selectedTeamId && Number(team.team_id) === Number(selectedTeamId));
                    html.push(
                        '<div role="button" class="ac-swap-team-chip' + (selected ? ' is-selected' : '') + '"' +
                        ' data-team-id="' + team.team_id + '"' +
                        ' data-team-name="' + this._escape(team.name) + '"' +
                        ' tabindex="0">' +
                        (team.logo_url
                            ? '<img class="ac-swap-team-logo" src="' + this._escape(team.logo_url) + '" alt=""/>'
                            : '<span class="ac-swap-team-logo ac-swap-team-logo-ph">🏅</span>') +
                        '<span class="ac-swap-team-meta">' +
                        '<span class="ac-swap-team-name">' + this._escape(team.name) + '</span>' +
                        '<span class="ac-swap-team-sub">' +
                        (team.player_count || 0) + ' players · ' +
                        this._escape(team.remaining_points_label || '0') + ' left</span>' +
                        '</span></div>'
                    );
                }.bind(this));
            }
            html.push('</div>');

            html.push('<div class="ac-swap-section-title">2. Select player to bring in</div>');

            var active = _.find(teams, function (t) {
                return t.selected || (selectedTeamId && Number(t.team_id) === Number(selectedTeamId));
            });

            if (!selectedTeamId && !active) {
                html.push('<div class="ac-swap-empty">Pick a team above to load its signed players.</div>');
            } else {
                var players = (active && active.players) || [];
                if (!players.length) {
                    html.push('<div class="ac-swap-empty">This team has no signed players to swap with.</div>');
                } else {
                    html.push('<div class="ac-swap-players">');
                    players.forEach(function (p) {
                        var attrs = (p.attrs || []).map(function (a) {
                            return '<span class="ac-swap-chip"><b>' + this._escape(a.label) +
                                '</b> ' + this._escape(a.value) + '</span>';
                        }.bind(this)).join('');
                        html.push(
                            '<div role="button" class="ac-swap-player-card' +
                            (p.selected ? ' is-selected' : '') + '"' +
                            ' data-line-id="' + p.line_id + '"' +
                            ' data-player-id="' + (p.player_id || '') + '"' +
                            ' data-player-name="' + this._escape(p.name) + '"' +
                            ' data-points="' + (p.points || 0) + '"' +
                            ' tabindex="0" style="--ac-swap-tier:' + this._escape(p.tier_color || '#3498db') + '">' +
                            '<div class="ac-swap-player-photo">' +
                            '<img src="' + this._escape(p.photo_url) + '" alt=""/>' +
                            (p.icon ? '<span class="ac-swap-icon-badge">★</span>' : '') +
                            '</div>' +
                            '<div class="ac-swap-player-body">' +
                            '<div class="ac-swap-player-name">' + this._escape(p.name) + '</div>' +
                            '<div class="ac-swap-player-role">' + this._escape(p.role || '—') + '</div>' +
                            '<div class="ac-swap-player-row">' +
                            '<span class="ac-swap-player-pts">' + this._escape(p.points_label) +
                            ' <small>' + unit + '</small></span>' +
                            (p.tier
                                ? '<span class="ac-swap-tier" style="background:' +
                                  this._escape(p.tier_color || '#3498db') + '">' +
                                  this._escape(p.tier) + '</span>'
                                : '') +
                            '</div>' +
                            '<div class="ac-swap-player-mobile">📱 ' +
                            this._escape(p.contact || '—') + '</div>' +
                            '<div class="ac-swap-attrs">' + attrs + '</div>' +
                            '</div></div>'
                        );
                    }.bind(this));
                    html.push('</div>');
                }
            }

            html.push('</div>');
            this.$el.html(html.join(''));
        },

        _applyBoardChanges: function (changes) {
            this.trigger_up('field_changed', {
                dataPointID: this.dataPointID,
                changes: changes,
                viewType: this.viewType,
            });
        },

        _reloadBoard: function (teamId, teamName) {
            var self = this;
            var sourceAuctionId = this._getSourceAuctionId();
            if (!sourceAuctionId) {
                return Promise.resolve();
            }
            this.$el.addClass('o_field_swap_player_board_loading');
            return this._rpc({
                model: 'auction.swap.player',
                method: 'action_get_swap_board',
                args: [sourceAuctionId, teamId || false, 0],
            }).then(function (boardJson) {
                self._applyBoardChanges({
                    board_json: boardJson,
                    target_team_id: teamId
                        ? {id: teamId, display_name: teamName || ''}
                        : false,
                    target_line_id: 0,
                    target_player_id: false,
                    target_points: 0,
                    target_swap_points: 0,
                    has_target_player: false,
                });
            }).guardedCatch(function () {
                // keep previous board on failure
            }).then(function () {
                self.$el.removeClass('o_field_swap_player_board_loading');
            });
        },

        _onTeamClick: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var $btn = $(ev.currentTarget);
            var teamId = parseInt($btn.attr('data-team-id'), 10);
            var teamName = $btn.attr('data-team-name') || '';
            if (!teamId) {
                return;
            }
            this._reloadBoard(teamId, teamName);
        },

        _onPlayerClick: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var $btn = $(ev.currentTarget);
            var lineId = parseInt($btn.attr('data-line-id'), 10);
            var playerId = parseInt($btn.attr('data-player-id'), 10);
            var playerName = $btn.attr('data-player-name') || '';
            var points = parseInt($btn.attr('data-points'), 10) || 0;
            if (!lineId || !playerId) {
                return;
            }

            var payload = this._getPayload();
            this._markPlayerSelected(payload, lineId);

            var sourcePoints = this._getSourcePoints();
            // Do NOT re-write target_team_id here — that onchange clears the player.
            this._applyBoardChanges({
                board_json: JSON.stringify(payload),
                target_line_id: lineId,
                target_player_id: {id: playerId, display_name: playerName},
                target_points: points,
                target_swap_points: points,
                source_swap_points: sourcePoints,
                has_target_player: true,
            });
        },

        _onTeamKeydown: function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                this._onTeamClick(ev);
            }
        },

        _onPlayerKeydown: function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                this._onPlayerClick(ev);
            }
        },
    });

    fieldRegistry.add('swap_player_board', SwapPlayerBoardWidget);

    return SwapPlayerBoardWidget;
});
