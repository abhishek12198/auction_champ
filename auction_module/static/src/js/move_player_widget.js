odoo.define('auction_module.MovePlayerBoardWidget', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');

    /**
     * Team picker for auction.move.player — select destination team only.
     */
    var MovePlayerBoardWidget = AbstractField.extend({
        className: 'o_field_move_player_board',
        supportedFieldTypes: ['text', 'char'],
        events: {
            'click .ac-move-team-chip': '_onTeamClick',
            'keydown .ac-move-team-chip': '_onTeamKeydown',
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
            return parseInt(this.recordData && this.recordData.source_points, 10) || 0;
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

        _renderBoard: function () {
            var data = this._getPayload();
            var teams = data.teams || [];
            var sport = this._escape(data.sport || 'cricket');
            var selectedTeamId = data.selected_team_id || false;
            var html = [];

            html.push('<div class="ac-move-board" data-sport="' + sport + '">');
            html.push('<div class="ac-swap-section-title">Choose destination team</div>');
            html.push('<div class="ac-swap-teams">');

            if (!teams.length) {
                html.push('<div class="ac-swap-empty">No other teams in this tournament.</div>');
            } else {
                teams.forEach(function (team) {
                    var selected = team.selected || (selectedTeamId && Number(team.team_id) === Number(selectedTeamId));
                    var slots = team.max_players
                        ? (team.player_count || 0) + ' / ' + team.max_players + ' players'
                        : (team.player_count || 0) + ' players';
                    html.push(
                        '<div role="button" class="ac-move-team-chip ac-swap-team-chip' +
                        (selected ? ' is-selected' : '') + '"' +
                        ' data-team-id="' + team.team_id + '"' +
                        ' data-team-name="' + this._escape(team.name) + '"' +
                        ' tabindex="0">' +
                        (team.logo_url
                            ? '<img class="ac-swap-team-logo" src="' + this._escape(team.logo_url) + '" alt=""/>'
                            : '<span class="ac-swap-team-logo ac-swap-team-logo-ph">🏅</span>') +
                        '<span class="ac-swap-team-meta">' +
                        '<span class="ac-swap-team-name">' + this._escape(team.name) + '</span>' +
                        '<span class="ac-swap-team-sub">' + slots +
                        ' · ' + this._escape(team.remaining_points_label || '0') + ' left</span>' +
                        '</span></div>'
                    );
                }.bind(this));
            }

            html.push('</div></div>');
            this.$el.html(html.join(''));
        },

        _applyChanges: function (changes) {
            this.trigger_up('field_changed', {
                dataPointID: this.dataPointID,
                changes: changes,
                viewType: this.viewType,
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

            var self = this;
            var sourceAuctionId = this._getSourceAuctionId();
            var sourcePoints = this._getSourcePoints();
            this.$el.addClass('o_field_swap_player_board_loading');

            this._rpc({
                model: 'auction.move.player',
                method: 'action_get_move_board',
                args: [sourceAuctionId, teamId],
            }).then(function (boardJson) {
                self._applyChanges({
                    board_json: boardJson,
                    target_team_id: {id: teamId, display_name: teamName},
                    selected_team_id: teamId,
                    has_target_team: true,
                    move_points: sourcePoints,
                });
            }).guardedCatch(function () {
                // keep previous board
            }).then(function () {
                self.$el.removeClass('o_field_swap_player_board_loading');
            });
        },

        _onTeamKeydown: function (ev) {
            if (ev.key === 'Enter' || ev.key === ' ') {
                this._onTeamClick(ev);
            }
        },
    });

    fieldRegistry.add('move_player_board', MovePlayerBoardWidget);

    return MovePlayerBoardWidget;
});
