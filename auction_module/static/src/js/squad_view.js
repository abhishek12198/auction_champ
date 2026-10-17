odoo.define('auction_module.SquadView', function (require) {
    'use strict';

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');
    var Dialog = require('web.Dialog');
    var session = require('web.session');
    var _t = core._t;

    function esc(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/"/g, '&quot;');
    }

    var SquadView = AbstractAction.extend({
        hasControlPanel: false,
        className: 'o_ac_squad_view',

        events: {
            'click .ac-sv-crumb-settings': '_onBack',
            'click .ac-sv-act': '_onAct',
            'dragstart .ac-sv-player': '_onDragStart',
            'dragend .ac-sv-player': '_onDragEnd',
            'dragover .ac-sv-team': '_onDragOver',
            'dragleave .ac-sv-team': '_onDragLeave',
            'drop .ac-sv-team': '_onDrop',
            'touchstart .ac-sv-player': '_onTouchStart',
            'click .ac-sv-choice-swap': '_onChoiceSwap',
            'click .ac-sv-choice-move': '_onChoiceMove',
            'click .ac-sv-choice-cancel': '_onChoiceCancel',
            'click .ac-sv-choice': '_onChoiceBackdrop',
            'click .ac-sv-print-roster': '_onPrintRoster',
            'click .ac-sv-print-poster': '_onPrintPoster',
            'click .ac-sv-poster-close': '_onPosterClose',
            'click .ac-sv-poster': '_onPosterBackdrop',
        },

        init: function (parent, action) {
            this._super.apply(this, arguments);
            var ctx = (action && action.context) || {};
            var params = (action && action.params) || {};
            this.tournamentId = ctx.tournament_id || params.tournament_id || null;
            this.fromUserSettings = !!(ctx.from_user_settings || params.from_user_settings);
            this.settingsScreen = ctx.settings_screen || params.settings_screen || 'players';
            this.data = null;
            this._drag = null;
            this._drop = null;
            this._dragY = null;
            this._dragScrollRaf = null;
            this._boundDragScrollMove = this._onDragScrollMove.bind(this);
            this._boundDragWheel = this._onDragWheel.bind(this);
            this._boundTouchMove = this._onTouchMove.bind(this);
            this._boundTouchEnd = this._onTouchEnd.bind(this);
            this._touch = null;
            this._touchTimer = null;
            this._ghost = null;
        },

        start: function () {
            var self = this;
            this.$el.addClass('o_ac_squad_view');
            return this._super.apply(this, arguments).then(function () {
                return self._load();
            });
        },

        destroy: function () {
            this._hidePoster();
            this._endTouchDrag();
            this._stopDragScroll();
            this._super.apply(this, arguments);
        },

        _load: function () {
            var self = this;
            if (!this.tournamentId) {
                this.$el.html(
                    '<div class="ac-sv-app"><div class="ac-sv-empty">' +
                    esc(_t('No tournament selected.')) + '</div></div>'
                );
                return Promise.resolve();
            }
            return this._rpc({
                model: 'auction.tournament',
                method: 'get_squad_view_payload',
                args: [[this.tournamentId]],
            }).then(function (data) {
                self.data = data || {};
                self._render();
            });
        },

        _render: function () {
            var d = this.data || {};
            var teams = d.teams || [];
            var body = teams.length
                ? teams.map(this._teamHtml.bind(this)).join('')
                : '<div class="ac-sv-empty">' + esc(_t('NO TEAMS YET. SET AUCTION RULES FIRST.')) + '</div>';
            var logo = d.logo_url
                ? '<img src="' + esc(d.logo_url) + '" alt="" draggable="false" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"/>' +
                  '<span class="ac-sv-ph" style="display:none">' + esc(d.initials || '') + '</span>'
                : '<span class="ac-sv-ph">' + esc(d.initials || '') + '</span>';
            this.$el.html(
                '<div class="ac-sv-app">' +
                    '<header class="ac-sv-head">' +
                        '<div class="ac-sv-tour-logo">' + logo + '</div>' +
                        '<div class="ac-sv-head-copy">' +
                            '<nav class="ac-sv-crumb" aria-label="' + esc(_t('Breadcrumb')) + '">' +
                                '<a href="#" class="ac-sv-crumb-settings">' +
                                    esc(_t('Tournament Settings')) + '</a>' +
                                '<span class="ac-sv-crumb-sep"> / </span>' +
                                '<span>' + esc(_t('Squad Modification')) + '</span>' +
                            '</nav>' +
                            (d.tournament_name ? '<p>' + esc(d.tournament_name) + '</p>' : '') +
                        '</div>' +
                        '<p class="ac-sv-head-meta">' +
                            esc(d.team_count || 0) + ' ' + esc(_t('Teams')) + ' · ' +
                            esc(d.sold_count || 0) + ' ' + esc(_t('Sold')) +
                        '</p>' +
                    '</header>' +
                    '<div class="ac-sv-body">' + body + '</div>' +
                    this._choiceHtml() +
                    this._posterHtml() +
                '</div>'
            );
        },

        _choiceHtml: function () {
            return '<div class="ac-sv-choice" hidden>' +
                '<div class="ac-sv-choice-card">' +
                    '<p class="ac-sv-choice-kicker">' + esc(_t('Drop action')) + '</p>' +
                    '<div class="ac-sv-choice-faces"></div>' +
                    '<p class="ac-sv-choice-msg"></p>' +
                    '<div class="ac-sv-choice-acts">' +
                        '<button type="button" class="ac-sv-choice-swap">' +
                            '<i class="fa fa-exchange"></i><span>' + esc(_t('Swap')) + '</span></button>' +
                        '<button type="button" class="ac-sv-choice-move">' +
                            '<i class="fa fa-arrow-right"></i><span>' + esc(_t('Move')) + '</span></button>' +
                        '<button type="button" class="ac-sv-choice-cancel">' +
                            esc(_t('Cancel')) + '</button>' +
                    '</div>' +
                '</div>' +
            '</div>';
        },

        _posterHtml: function () {
            return '<div class="ac-sv-poster" hidden>' +
                '<div class="ac-sv-poster-card">' +
                    '<header class="ac-sv-poster-bar">' +
                        '<span>' + esc(_t('Squad Poster (Instagram)')) + '</span>' +
                        '<button type="button" class="ac-sv-poster-close">' +
                            esc(_t('Close')) + '</button>' +
                    '</header>' +
                    '<iframe class="ac-sv-poster-frame" title="' +
                        esc(_t('Squad Poster')) + '"></iframe>' +
                '</div>' +
            '</div>';
        },

        _teamHtml: function (team) {
            var squadPct = Math.max(0, Math.min(100, team.squad_pct || 0));
            var spendPct = Math.max(0, Math.min(100, team.spend_pct || 0));
            var self = this;
            var players = (team.players || []).map(function (player) {
                return self._playerHtml(player, team);
            }).join('');
            if (!players) {
                players = '<li class="ac-sv-empty-row">' + esc(_t('NO SOLD PLAYERS')) + '</li>';
            }
            var logo = team.logo_url
                ? '<img src="' + esc(team.logo_url) + '" alt="" draggable="false" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"/>' +
                  '<span class="ac-sv-ph" style="display:none">' + esc(team.initials || '') + '</span>'
                : '<span class="ac-sv-ph">' + esc(team.initials || '') + '</span>';
            return '<section class="ac-sv-team" data-team="' + esc(team.team_id || 0) +
                '" data-name="' + esc(team.name || '') +
                '" data-logo="' + esc(team.logo_url || '') +
                '" data-initials="' + esc(team.initials || '') +
                '" data-auction="' + esc(team.auction_id || 0) + '">' +
                '<header class="ac-sv-team-head">' +
                    '<div class="ac-sv-logo">' + logo + '</div>' +
                    '<div class="ac-sv-team-id">' +
                        '<h2>' + esc(team.name || '') + '</h2>' +
                        (team.owner ? '<p>' + esc(_t('Owner')) + ' · ' + esc(team.owner) + '</p>' : '') +
                    '</div>' +
                    '<div class="ac-sv-meters">' +
                        '<div class="ac-sv-meter">' +
                            '<div class="ac-sv-meter-row"><span>' + esc(_t('Squad')) + '</span>' +
                            '<span>' + esc(team.squad_now) + ' / ' + esc(team.squad_max) + '</span></div>' +
                            '<div class="ac-sv-track" role="progressbar" aria-valuenow="' + squadPct +
                                '" aria-valuemin="0" aria-valuemax="100">' +
                                '<i style="width:' + squadPct + '%"></i></div>' +
                        '</div>' +
                        '<div class="ac-sv-meter">' +
                            '<div class="ac-sv-meter-row"><span>' + esc(_t('Spent / purse')) + '</span>' +
                            '<span>' + esc(team.spent_display) + ' / ' + esc(team.purse_display) + '</span></div>' +
                            '<div class="ac-sv-track ac-sv-track-spend" role="progressbar" aria-valuenow="' + spendPct +
                                '" aria-valuemin="0" aria-valuemax="100">' +
                                '<i style="width:' + spendPct + '%"></i></div>' +
                        '</div>' +
                    '</div>' +
                    '<div class="ac-sv-team-tools">' +
                        '<button type="button" class="ac-sv-team-btn ac-sv-print-roster" data-auction="' +
                            esc(team.auction_id || 0) + '">' +
                            '<i class="fa fa-print"></i><span>' + esc(_t('Print Squad Roster')) +
                            '</span></button>' +
                        '<button type="button" class="ac-sv-team-btn ac-sv-print-poster" data-auction="' +
                            esc(team.auction_id || 0) + '">' +
                            '<i class="fa fa-picture-o"></i><span>' + esc(_t('Squad Poster (Instagram)')) +
                            '</span></button>' +
                    '</div>' +
                '</header>' +
                '<ul class="ac-sv-players">' + players + '</ul>' +
            '</section>';
        },

        _playerHtml: function (player, team) {
            var photo = player.photo_url
                ? '<img src="' + esc(player.photo_url) + '" alt="" draggable="false" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"/>' +
                  '<span class="ac-sv-ph" style="display:none">' + esc(player.initials || '') + '</span>'
                : '<span class="ac-sv-ph">' + esc(player.initials || '') + '</span>';
            var meta = [player.points_display ? (_t('Sold') + ' ' + player.points_display) : '', player.role]
                .filter(Boolean).join(' · ');
            return '<li class="ac-sv-player" draggable="true" data-line="' +
                esc(player.line_id || 0) + '" data-team="' + esc((team && team.team_id) || 0) +
                '" data-name="' + esc(player.name || '') +
                '" data-photo="' + esc(player.photo_url || '') +
                '" data-initials="' + esc(player.initials || '') + '">' +
                '<div class="ac-sv-photo">' + photo + '</div>' +
                '<div class="ac-sv-who">' +
                    '<p class="ac-sv-name">' + esc(player.name || '') + '</p>' +
                    (meta ? '<p class="ac-sv-sold">' + esc(meta) + '</p>' : '') +
                '</div>' +
                '<div class="ac-sv-acts">' +
                    this._actBtn(player.line_id, 'edit', 'fa-pencil', 'ac-sv-btn-edit', _t('Edit sold value')) +
                    this._actBtn(player.line_id, 'swap', 'fa-exchange', 'ac-sv-btn-swap', _t("Swap with another team's player")) +
                    this._actBtn(player.line_id, 'move', 'fa-arrow-right', 'ac-sv-btn-move', _t('Move to another team')) +
                    this._actBtn(player.line_id, 'recall', 'fa-undo', 'ac-sv-btn-recall', _t('Recall to auction')) +
                '</div>' +
            '</li>';
        },

        _actBtn: function (lineId, act, icon, extraCls, title) {
            return '<button type="button" class="ac-sv-btn ' + extraCls + ' ac-sv-act" data-act="' +
                act + '" data-line="' + lineId + '" title="' + esc(title) + '" aria-label="' +
                esc(title) + '"><i class="fa ' + icon + '"></i></button>';
        },

        _onBack: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            if (this.fromUserSettings) {
                this.trigger_up('history_back');
                return;
            }
            this.do_action({
                type: 'ir.actions.client',
                tag: 'auction_module.tournament_settings_user',
                name: _t('Tournament Settings'),
                target: 'current',
                context: {
                    tournament_id: this.tournamentId,
                    settings_screen: this.settingsScreen || 'players',
                },
                params: {
                    tournament_id: this.tournamentId,
                    settings_screen: this.settingsScreen || 'players',
                },
            });
        },

        _onAct: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var btn = ev.currentTarget;
            var act = btn.getAttribute('data-act');
            var lineId = parseInt(btn.getAttribute('data-line'), 10);
            if (!act || !lineId) {
                return;
            }
            if (act === 'recall') {
                this._recall(lineId);
                return;
            }
            this._openWizard(act, lineId, {});
        },

        _onDragStart: function (ev) {
            if ($(ev.target).closest('.ac-sv-act, .ac-sv-btn').length) {
                ev.preventDefault();
                return;
            }
            var card = ev.currentTarget;
            var dt = ev.originalEvent && ev.originalEvent.dataTransfer;
            this._drag = this._dragFromCard(card);
            if (!this._drag.lineId) {
                ev.preventDefault();
                return;
            }
            if (dt) {
                dt.setData('text/plain', String(this._drag.lineId));
                dt.effectAllowed = 'move';
            }
            $(card).addClass('is-dragging');
            this.$('.ac-sv-app').addClass('is-dragging-player');
            this._startDragScroll();
        },

        _onDragEnd: function () {
            this._clearDragUi();
        },

        _dragFromCard: function (card) {
            return {
                lineId: parseInt(card.getAttribute('data-line'), 10) || 0,
                teamId: parseInt(card.getAttribute('data-team'), 10) || 0,
                name: card.getAttribute('data-name') || '',
                photo: card.getAttribute('data-photo') || '',
                initials: card.getAttribute('data-initials') || '',
            };
        },

        _onTouchStart: function (ev) {
            if ($(ev.target).closest('.ac-sv-act, .ac-sv-btn, .ac-sv-choice').length) {
                return;
            }
            var oe = ev.originalEvent || ev;
            var touch = oe.touches && oe.touches[0];
            if (!touch) {
                return;
            }
            var card = ev.currentTarget;
            var self = this;
            this._endTouchDrag();
            this._touch = {
                card: card,
                startX: touch.clientX,
                startY: touch.clientY,
                active: false,
            };
            this._touchTimer = setTimeout(function () {
                if (!self._touch || self._touch.active) {
                    return;
                }
                self._beginTouchDrag();
                if (window.navigator && window.navigator.vibrate) {
                    window.navigator.vibrate(15);
                }
            }, 180);
            document.addEventListener('touchmove', this._boundTouchMove, {capture: true, passive: false});
            document.addEventListener('touchend', this._boundTouchEnd, true);
            document.addEventListener('touchcancel', this._boundTouchEnd, true);
        },

        _onTouchMove: function (ev) {
            if (!this._touch) {
                return;
            }
            var touch = ev.touches && ev.touches[0];
            if (!touch) {
                return;
            }
            var dx = touch.clientX - this._touch.startX;
            var dy = touch.clientY - this._touch.startY;
            if (!this._touch.active) {
                if (Math.hypot(dx, dy) > 12) {
                    this._endTouchDrag();
                }
                return;
            }
            ev.preventDefault();
            this._dragY = touch.clientY;
            this._moveGhost(touch.clientX, touch.clientY);
            this._highlightAt(touch.clientX, touch.clientY);
        },

        _onTouchEnd: function (ev) {
            if (!this._touch) {
                this._unbindTouch();
                return;
            }
            if (this._touch.active) {
                ev.preventDefault();
                var touch = ev.changedTouches && ev.changedTouches[0];
                if (touch) {
                    this._finishTouchDrop(touch.clientX, touch.clientY);
                }
            }
            this._endTouchDrag();
        },

        _beginTouchDrag: function () {
            if (!this._touch || !this._touch.card) {
                return;
            }
            var drag = this._dragFromCard(this._touch.card);
            if (!drag.lineId) {
                this._endTouchDrag();
                return;
            }
            this._touch.active = true;
            this._drag = drag;
            $(this._touch.card).addClass('is-dragging');
            this.$('.ac-sv-app').addClass('is-dragging-player');
            this._makeGhost(this._touch.card);
            this._startDragScroll();
        },

        _makeGhost: function (card) {
            this._removeGhost();
            var ghost = card.cloneNode(true);
            ghost.classList.add('ac-sv-ghost');
            ghost.classList.remove('is-dragging');
            ghost.removeAttribute('draggable');
            document.body.appendChild(ghost);
            this._ghost = ghost;
            var rect = card.getBoundingClientRect();
            this._ghostW = rect.width;
            this._ghostH = rect.height;
            ghost.style.width = rect.width + 'px';
            this._moveGhost(this._touch.startX, this._touch.startY);
        },

        _moveGhost: function (x, y) {
            if (!this._ghost) {
                return;
            }
            this._ghost.style.left = (x - (this._ghostW || 74) / 2) + 'px';
            this._ghost.style.top = (y - (this._ghostH || 80) / 2) + 'px';
        },

        _removeGhost: function () {
            if (this._ghost && this._ghost.parentNode) {
                this._ghost.parentNode.removeChild(this._ghost);
            }
            this._ghost = null;
        },

        _highlightAt: function (x, y) {
            var el = document.elementFromPoint(x, y);
            this.$('.ac-sv-team').removeClass('is-drop');
            this.$('.ac-sv-player').removeClass('is-drop-target');
            var $team = $(el).closest('.ac-sv-team');
            if (!$team.length || !this._drag) {
                return;
            }
            var teamId = parseInt($team.attr('data-team'), 10) || 0;
            if (!teamId || teamId === this._drag.teamId) {
                return;
            }
            $team.addClass('is-drop');
            var $player = $(el).closest('.ac-sv-player');
            if ($player.length && $team.has($player).length) {
                var line = parseInt($player.attr('data-line'), 10) || 0;
                if (line && line !== this._drag.lineId) {
                    $player.addClass('is-drop-target');
                }
            }
        },

        _finishTouchDrop: function (x, y) {
            var el = document.elementFromPoint(x, y);
            var $team = $(el).closest('.ac-sv-team');
            if (!$team.length) {
                return;
            }
            this._applyDrop($team, $(el).closest('.ac-sv-player'));
        },

        _unbindTouch: function () {
            document.removeEventListener('touchmove', this._boundTouchMove, true);
            document.removeEventListener('touchend', this._boundTouchEnd, true);
            document.removeEventListener('touchcancel', this._boundTouchEnd, true);
            if (this._touchTimer) {
                clearTimeout(this._touchTimer);
                this._touchTimer = null;
            }
        },

        _endTouchDrag: function () {
            this._unbindTouch();
            this._removeGhost();
            this._touch = null;
            this._clearDragUi();
        },

        _clearDragUi: function () {
            this._stopDragScroll();
            this.$('.ac-sv-player').removeClass('is-dragging is-drop-target');
            this.$('.ac-sv-team').removeClass('is-drop');
            this.$('.ac-sv-app').removeClass('is-dragging-player');
            this._drag = null;
        },

        _scrollParent: function () {
            var el = this.el;
            var nodes = [el];
            if (el && el.parentElement) {
                nodes.push(el.parentElement);
            }
            if (el && el.closest) {
                var content = el.closest('.o_content');
                if (content) {
                    nodes.push(content);
                }
            }
            var i;
            for (i = 0; i < nodes.length; i++) {
                var node = nodes[i];
                if (!node) {
                    continue;
                }
                var style = window.getComputedStyle(node);
                var oy = style.overflowY;
                if ((oy === 'auto' || oy === 'scroll') && node.scrollHeight > node.clientHeight + 4) {
                    return node;
                }
            }
            return document.scrollingElement || document.documentElement;
        },

        _startDragScroll: function () {
            this._stopDragScroll();
            this._dragY = null;
            document.addEventListener('dragover', this._boundDragScrollMove, true);
            document.addEventListener('wheel', this._boundDragWheel, {capture: true, passive: false});
            this._tickDragScroll();
        },

        _stopDragScroll: function () {
            document.removeEventListener('dragover', this._boundDragScrollMove, true);
            document.removeEventListener('wheel', this._boundDragWheel, true);
            if (this._dragScrollRaf) {
                cancelAnimationFrame(this._dragScrollRaf);
                this._dragScrollRaf = null;
            }
            this._dragY = null;
        },

        _onDragScrollMove: function (ev) {
            if (!this._drag) {
                return;
            }
            ev.preventDefault();
            this._dragY = ev.clientY;
        },

        _onDragWheel: function (ev) {
            if (!this._drag) {
                return;
            }
            ev.preventDefault();
            var scroller = this._scrollParent();
            if (scroller) {
                scroller.scrollTop += ev.deltaY;
            }
        },

        _tickDragScroll: function () {
            var self = this;
            this._dragScrollRaf = requestAnimationFrame(function () {
                self._applyDragScroll();
                if (self._drag && self._drag.lineId) {
                    self._tickDragScroll();
                } else {
                    self._dragScrollRaf = null;
                }
            });
        },

        _applyDragScroll: function () {
            if (this._dragY == null) {
                return;
            }
            var scroller = this._scrollParent();
            if (!scroller) {
                return;
            }
            var rect = scroller.getBoundingClientRect();
            var edge = 90;
            var y = this._dragY;
            var speed = 0;
            if (y < rect.top + edge) {
                speed = -this._scrollSpeed(rect.top + edge - y, edge);
            } else if (y > rect.bottom - edge) {
                speed = this._scrollSpeed(y - (rect.bottom - edge), edge);
            }
            if (speed) {
                scroller.scrollTop += speed;
            }
        },

        _scrollSpeed: function (dist, edge) {
            var t = Math.min(1, Math.max(0, dist / edge));
            return Math.max(8, Math.round(32 * t * t));
        },

        _onDragOver: function (ev) {
            if (!this._drag || !this._drag.lineId) {
                return;
            }
            ev.preventDefault();
            if (ev.originalEvent && ev.originalEvent.dataTransfer) {
                ev.originalEvent.dataTransfer.dropEffect = 'move';
            }
            var teamId = parseInt(ev.currentTarget.getAttribute('data-team'), 10) || 0;
            this.$('.ac-sv-team').removeClass('is-drop');
            if (teamId && teamId !== this._drag.teamId) {
                $(ev.currentTarget).addClass('is-drop');
            }
        },

        _onDragLeave: function (ev) {
            var related = ev.relatedTarget;
            if (related && ev.currentTarget.contains(related)) {
                return;
            }
            $(ev.currentTarget).removeClass('is-drop');
        },

        _onDrop: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            this._applyDrop($(ev.currentTarget), $(ev.target).closest('.ac-sv-player'));
        },

        _applyDrop: function ($team, $player) {
            $team.removeClass('is-drop');
            this.$('.ac-sv-player').removeClass('is-drop-target');
            var drag = this._drag;
            var toTeam = parseInt($team.attr('data-team'), 10) || 0;
            if (!drag || !drag.lineId || !toTeam || toTeam === drag.teamId) {
                return;
            }
            var toLine = 0;
            if ($player && $player.length && $team.has($player).length) {
                toLine = parseInt($player.attr('data-line'), 10) || 0;
                if (toLine === drag.lineId) {
                    toLine = 0;
                }
            }
            this._drop = {
                lineId: drag.lineId,
                fromTeam: drag.teamId,
                fromName: drag.name,
                fromPhoto: drag.photo || '',
                fromInitials: drag.initials || '',
                toTeam: toTeam,
                toTeamName: $team.attr('data-name') || '',
                toTeamLogo: $team.attr('data-logo') || '',
                toTeamInitials: $team.attr('data-initials') || '',
                toLine: toLine,
                toName: toLine ? ($player.attr('data-name') || '') : '',
                toPhoto: toLine ? ($player.attr('data-photo') || '') : '',
                toInitials: toLine ? ($player.attr('data-initials') || '') : '',
            };
            this._showChoice();
        },

        _faceHtml: function (photo, initials, name) {
            var pic = photo
                ? '<img src="' + esc(photo) + '" alt="" draggable="false" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\'"/>' +
                  '<span class="ac-sv-ph" style="display:none">' + esc(initials || '') + '</span>'
                : '<span class="ac-sv-ph">' + esc(initials || '') + '</span>';
            return '<div class="ac-sv-choice-face">' +
                '<div class="ac-sv-choice-pic">' + pic + '</div>' +
                (name ? '<p class="ac-sv-choice-label">' + esc(name) + '</p>' : '') +
                '</div>';
        },

        _showChoice: function () {
            var drop = this._drop || {};
            var isSwap = !!drop.toLine;
            var fromName = drop.fromName || _t('This player');
            var toTeam = drop.toTeamName || _t('this team');
            var faces = this._faceHtml(drop.fromPhoto, drop.fromInitials, fromName);
            faces += '<span class="ac-sv-choice-arrow">' + (isSwap ? '⇄' : '→') + '</span>';
            faces += isSwap
                ? this._faceHtml(drop.toPhoto, drop.toInitials, drop.toName || _t('this player'))
                : this._faceHtml(drop.toTeamLogo, drop.toTeamInitials, toTeam);
            this.$('.ac-sv-choice-card')
                .toggleClass('is-swap-only', isSwap)
                .toggleClass('is-move-only', !isSwap);
            this.$('.ac-sv-choice-kicker').text(isSwap ? _t('Swap players') : _t('Move player'));
            this.$('.ac-sv-choice-faces').html(faces);
            this.$('.ac-sv-choice-msg').text(toTeam);
            this.$('.ac-sv-choice').prop('hidden', false);
        },

        _hideChoice: function () {
            this.$('.ac-sv-choice').prop('hidden', true);
            this._drop = null;
        },

        _onChoiceSwap: function (ev) {
            ev.preventDefault();
            var drop = this._drop;
            this._hideChoice();
            if (!drop) {
                return;
            }
            this._openWizard('swap', drop.lineId, {
                squad_target_team_id: drop.toTeam,
                squad_target_line_id: drop.toLine || 0,
            });
        },

        _onChoiceMove: function (ev) {
            ev.preventDefault();
            var drop = this._drop;
            this._hideChoice();
            if (!drop) {
                return;
            }
            this._openWizard('move', drop.lineId, {
                squad_target_team_id: drop.toTeam,
            });
        },

        _onChoiceCancel: function (ev) {
            ev.preventDefault();
            this._hideChoice();
        },

        _onChoiceBackdrop: function (ev) {
            if (ev.target === ev.currentTarget) {
                this._hideChoice();
            }
        },

        _onPrintRoster: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var auctionId = parseInt(ev.currentTarget.getAttribute('data-auction'), 10);
            if (!auctionId) {
                return;
            }
            this.do_action('auction_module.action_report_auction_players', {
                additional_context: {
                    active_id: auctionId,
                    active_ids: [auctionId],
                    active_model: 'auction.auction',
                },
            });
        },

        _onPrintPoster: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            var auctionId = parseInt(ev.currentTarget.getAttribute('data-auction'), 10);
            if (!auctionId) {
                return;
            }
            var url = session.db
                ? '/' + session.db + '/auction/squad-poster/' + auctionId
                : '/auction/squad-poster/' + auctionId;
            url += (url.indexOf('?') >= 0 ? '&' : '?') + 'embed=1';
            this.$('.ac-sv-poster-frame').attr('src', url);
            this.$('.ac-sv-poster').prop('hidden', false);
        },

        _onPosterClose: function (ev) {
            ev.preventDefault();
            this._hidePoster();
        },

        _onPosterBackdrop: function (ev) {
            if (ev.target === ev.currentTarget) {
                this._hidePoster();
            }
        },

        _hidePoster: function () {
            this.$('.ac-sv-poster').prop('hidden', true);
            this.$('.ac-sv-poster-frame').attr('src', 'about:blank');
        },

        _openWizard: function (act, lineId, extraCtx) {
            var xmlIds = {
                edit: 'auction_module.action_edit_player_point',
                swap: 'auction_module.action_swap_player',
                move: 'auction_module.action_move_player',
            };
            var xmlId = xmlIds[act];
            if (!xmlId || !lineId) {
                return;
            }
            var self = this;
            this.do_action(xmlId, {
                additional_context: Object.assign({
                    active_id: lineId,
                    active_ids: [lineId],
                    active_model: 'auction.auction.player',
                }, extraCtx || {}),
                on_close: function () {
                    self._load();
                },
            });
        },

        _recall: function (lineId) {
            var self = this;
            Dialog.confirm(this, _t('Bring this player back to auction? This will remove them from the team.'), {
                confirm_callback: function () {
                    return self._rpc({
                        model: 'auction.auction.player',
                        method: 'action_recall_to_auction',
                        args: [[lineId]],
                    }).then(function () {
                        return self._load();
                    });
                },
            });
        },
    });

    core.action_registry.add('auction_module.squad_view', SquadView);
    return SquadView;
});
