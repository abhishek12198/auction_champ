# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — Submit upgrade request wizard
#
##############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AcSaasUpgradeRequestWizard(models.TransientModel):
    _name = 'ac.saas.upgrade.request.wizard'
    _description = 'Request Plan Upgrade'

    account_id = fields.Many2one(
        'ac.saas.account',
        string='Account',
        required=True,
        readonly=True,
    )
    current_plan_id = fields.Many2one(
        'ac.saas.plan',
        string='Current Plan',
        required=True,
        readonly=True,
    )
    requested_plan_id = fields.Many2one(
        'ac.saas.plan',
        string='Upgrade to',
        required=True,
        domain="[('active', '=', True), ('sequence', '>', current_plan_sequence)]",
    )
    current_plan_sequence = fields.Integer(
        related='current_plan_id.sequence',
        readonly=True,
    )
    trigger_feature = fields.Selection(
        [
            ('theme', 'Player card theme'),
            ('random', 'Random mode'),
            ('teams', 'More teams'),
            ('players', 'More players'),
            ('tournaments', 'More tournaments'),
            ('parallel', 'Parallel tournaments (multi-device)'),
            ('other', 'Other'),
        ],
        string='Looking for',
        required=True,
        default='other',
    )
    tournament_id = fields.Many2one(
        'auction.tournament',
        string='Tournament',
        readonly=True,
    )
    note = fields.Text(
        string='Message (optional)',
        placeholder='Tell us what you need (e.g. Vanilla theme for our finals)…',
    )
    plan_preview = fields.Text(
        string='What you unlock',
        compute='_compute_plan_preview',
        readonly=True,
    )
    plan_preview_html = fields.Html(
        string='What you unlock',
        compute='_compute_plan_preview',
        readonly=True,
        sanitize=False,
    )

    @api.model
    def _theme_meta(self):
        """Display label + chip colors for each player-card theme."""
        return {
            'lemon': {
                'label': _('Lemon'),
                'bg': '#F6E27A',
                'fg': '#5C4A00',
                'border': '#E0C94A',
            },
            'vanilla': {
                'label': _('Vanilla'),
                'bg': '#F4E8C8',
                'fg': '#5C4A2A',
                'border': '#E2D2A8',
            },
            'butterscotch': {
                'label': _('Butterscotch'),
                'bg': '#E8B86D',
                'fg': '#4A2E00',
                'border': '#D49A45',
            },
            'strawberry': {
                'label': _('Strawberry'),
                'bg': '#F07178',
                'fg': '#4A0A12',
                'border': '#D94C56',
            },
            'cherry': {
                'label': _('Cherry'),
                'bg': '#C6283A',
                'fg': '#FFFFFF',
                'border': '#9E1E2E',
            },
            'pistah': {
                'label': _('Pistah'),
                'bg': '#8BC34A',
                'fg': '#1B3A0A',
                'border': '#6FA032',
            },
            'blackberry': {
                'label': _('Blackberry'),
                'bg': '#1E3A8A',
                'fg': '#FFFFFF',
                'border': '#3B82F6',
            },
        }

    @api.depends('requested_plan_id')
    def _compute_plan_preview(self):
        theme_meta = self._theme_meta()
        for wiz in self:
            plan = wiz.requested_plan_id
            if not plan:
                wiz.plan_preview = False
                wiz.plan_preview_html = False
                continue

            themes = plan.get_allowed_templates() or []
            random_yes = bool(plan.allow_random_mode)
            parallel_yes = bool(plan.allow_parallel_sessions)
            price_info = plan.get_website_price_display()
            bits = [b for b in (
                price_info.get('amount'),
                ('(%s)' % price_info['per_tournament']) if price_info.get('per_tournament') else False,
                price_info.get('validity'),
            ) if b]
            price_text = ' '.join(bits) if bits else _('Not listed')
            lines = [
                _('Package: %s') % price_text,
                _('Tournaments: up to %s') % plan.max_tournaments,
                _('Teams / tournament: up to %s') % plan.max_teams_per_tournament,
                _('Players / tournament: up to %s') % plan.max_players_per_tournament,
                _('Random mode: %s') % (_('Yes') if random_yes else _('No')),
                _('Parallel tournaments (multi-device): %s') % (
                    _('Yes') if parallel_yes else _('No')
                ),
                _('Themes: %s') % (
                    ', '.join(
                        theme_meta.get(t, {}).get('label', t.title()) for t in themes
                    ) if themes else '—'
                ),
            ]
            wiz.plan_preview = '\n'.join(lines)

            feature_cards = [
                {
                    'icon': 'fa-tag',
                    'label': _('Package'),
                    'value': price_text,
                    'tone': 'navy',
                },
                {
                    'icon': 'fa-trophy',
                    'label': _('Tournaments'),
                    'value': _('up to %s') % plan.max_tournaments,
                    'tone': 'navy',
                },
                {
                    'icon': 'fa-users',
                    'label': _('Teams / tournament'),
                    'value': _('up to %s') % plan.max_teams_per_tournament,
                    'tone': 'blue',
                },
                {
                    'icon': 'fa-user',
                    'label': _('Players / tournament'),
                    'value': _('up to %s') % plan.max_players_per_tournament,
                    'tone': 'teal',
                },
                {
                    'icon': 'fa-random',
                    'label': _('Random mode'),
                    'value': _('Yes') if random_yes else _('No'),
                    'tone': 'green' if random_yes else 'muted',
                },
                {
                    'icon': 'fa-laptop',
                    'label': _('Parallel tournaments'),
                    'value': _('Yes') if parallel_yes else _('No'),
                    'tone': 'green' if parallel_yes else 'muted',
                },
            ]

            cards_html = []
            for card in feature_cards:
                cards_html.append(
                    '<div class="o_saas_unlock_card o_saas_unlock_%(tone)s">'
                    '<div class="o_saas_unlock_card_icon"><i class="fa %(icon)s"/></div>'
                    '<div class="o_saas_unlock_card_body">'
                    '<div class="o_saas_unlock_card_label">%(label)s</div>'
                    '<div class="o_saas_unlock_card_value">%(value)s</div>'
                    '</div></div>' % card
                )

            theme_chips = []
            for key in themes:
                meta = theme_meta.get(key) or {
                    'label': key.title(),
                    'bg': '#CED4DA',
                    'fg': '#212529',
                    'border': '#ADB5BD',
                }
                theme_chips.append(
                    '<span class="o_saas_theme_chip" style="'
                    'background:%(bg)s;color:%(fg)s;border-color:%(border)s;">'
                    '%(label)s</span>' % meta
                )
            if not theme_chips:
                theme_chips.append(
                    '<span class="o_saas_theme_chip o_saas_theme_chip_empty">—</span>'
                )

            wiz.plan_preview_html = (
                '<div class="o_saas_unlock_panel">'
                '<div class="o_saas_unlock_title">%(title)s</div>'
                '<div class="o_saas_unlock_grid">%(cards)s</div>'
                '<div class="o_saas_unlock_themes">'
                '<div class="o_saas_unlock_themes_label">%(themes_label)s</div>'
                '<div class="o_saas_unlock_themes_row">%(chips)s</div>'
                '</div></div>'
            ) % {
                'title': _('What you unlock'),
                'cards': ''.join(cards_html),
                'themes_label': _('Player card themes'),
                'chips': ''.join(theme_chips),
            }

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        Account = self.env['ac.saas.account']
        ctx = self.env.context
        account = Account.browse()
        if ctx.get('default_tournament_id'):
            tournament = self.env['auction.tournament'].browse(ctx['default_tournament_id'])
            account = tournament.saas_account_id
        if not account:
            account = Account._get_account_for_user()
        if not account:
            raise UserError(_(
                'No SaaS account is linked to your login. Please contact support.'
            ))
        # Customers may only request for their own account
        if (
            account.user_id != self.env.user
            and not self.env.user._is_superuser()
            and not self.env.user.has_group('ac_saas_manager.group_saas_manager')
            and not self.env.user.has_group('auction_module.group_auction_group_admin')
        ):
            raise UserError(_('You can only request an upgrade for your own account.'))

        plan = account.plan_id
        res['account_id'] = account.id
        res['current_plan_id'] = plan.id
        higher = self.env['ac.saas.plan'].search([
            ('active', '=', True),
            ('sequence', '>', plan.sequence),
        ], order='sequence, id', limit=1)
        if ctx.get('default_requested_plan_id'):
            res['requested_plan_id'] = ctx['default_requested_plan_id']
        elif higher:
            res['requested_plan_id'] = higher.id
        if ctx.get('default_trigger_feature'):
            res['trigger_feature'] = ctx['default_trigger_feature']
        if ctx.get('default_tournament_id'):
            res['tournament_id'] = ctx['default_tournament_id']
        return res

    def action_submit(self):
        self.ensure_one()
        account = self.account_id
        is_manager = (
            self.env.user._is_superuser()
            or self.env.user.has_group('ac_saas_manager.group_saas_manager')
            or self.env.user.has_group('auction_module.group_auction_group_admin')
        )
        if account.user_id != self.env.user and not is_manager:
            raise UserError(_('You can only request an upgrade for your own account.'))

        Request = self.env['ac.saas.upgrade.request']
        pending = Request.sudo().search([
            ('account_id', '=', account.id),
            ('state', '=', 'pending'),
            ('requested_plan_id', '=', self.requested_plan_id.id),
        ], limit=1)
        if pending:
            raise UserError(_(
                'You already have a pending request (%(ref)s) for %(plan)s. '
                'We will confirm it shortly.'
            ) % {'ref': pending.name, 'plan': self.requested_plan_id.name})

        request = Request.sudo().create({
            'account_id': account.id,
            'current_plan_id': self.current_plan_id.id,
            'requested_plan_id': self.requested_plan_id.id,
            'trigger_feature': self.trigger_feature,
            'tournament_id': self.tournament_id.id if self.tournament_id else False,
            'note': self.note,
            'state': 'pending',
        })
        request._notify_managers_new_request()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Upgrade request sent'),
                'message': _(
                    'Request %(ref)s for %(plan)s was submitted. '
                    'We typically confirm within 24 hours.'
                ) % {'ref': request.name, 'plan': self.requested_plan_id.name},
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
