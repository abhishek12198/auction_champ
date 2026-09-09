# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp SaaS Manager — Plan catalog
#
##############################################################################
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class AcSaasPlan(models.Model):
    _name = 'ac.saas.plan'
    _description = 'AuctionChamp SaaS Plan'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    code = fields.Selection(
        [
            ('standard', 'Starter'),
            ('classic', 'Classic'),
            ('pro', 'Pro'),
            ('pro_plus', 'Champion'),
        ],
        required=True,
        index=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    recommended = fields.Boolean(string='Recommended')
    description = fields.Text()

    # ── Package tariff (one-time purchase; shown on marketing website) ──
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    list_price = fields.Monetary(
        string='Package price',
        currency_field='currency_id',
        help='One-time purchase amount for this package (covers the tournament quota below).',
    )
    price_per_tournament = fields.Monetary(
        string='Per tournament',
        currency_field='currency_id',
        compute='_compute_price_per_tournament',
        help='Package price ÷ max tournaments (shown on the website in braces).',
    )
    validity_days = fields.Integer(
        string='Package validity (days)',
        default=365,
        help='How long the package remains valid after purchase / activation. '
             'Shown on the website and used when setting account end date.',
    )
    price_label = fields.Char(
        string='Price label override',
        help='Optional. When set, this text is shown instead of the package price '
             '(e.g. “Contact us”, “Custom quote”).',
    )
    show_price_on_website = fields.Boolean(
        string='Show price on website',
        default=True,
        help='Uncheck to hide the price block on the public pricing section.',
    )

    # ── Quotas ────────────────────────────────────────────────────────────
    max_tournaments = fields.Integer(
        required=True,
        help='Maximum tournaments this account may create.',
    )
    max_teams_per_tournament = fields.Integer(
        required=True,
        help='Maximum teams allowed on each tournament.',
    )
    max_players_per_tournament = fields.Integer(
        required=True,
        help='Maximum player registrations allowed per tournament.',
    )

    # ── Features ──────────────────────────────────────────────────────────
    # Toggles below are the single source of truth for organisers. SaaS accounts
    # auto-sync the matching security groups — do not assign those groups by hand.
    allow_random_mode = fields.Boolean(
        string='Random + Manual Mode',
        help='If disabled, only Manual (linear) player appearance is allowed.',
    )
    allow_auctioneer_console = fields.Boolean(
        string='Auctioneer Console',
        help='When enabled, organisers on this plan automatically get the '
             'Auctioneer Console app in their menu. Access is synced from this '
             'plan only — no separate group configuration is required.',
    )
    allow_owner_bidding = fields.Boolean(
        string='Owners Remote Bidding',
        help='Allows team Owner console / remote bidding features for this plan. '
             'Owner logins are still assigned per team; this flag is the plan entitlement.',
    )
    allow_pool_creator = fields.Boolean(
        string='Pool Creator',
        help='When enabled, organisers on this plan automatically get the Pool '
             'Creator app. Synced from this plan — no separate group setup needed.',
    )
    allow_roster_print_settings = fields.Boolean(
        string='Roster Print (Settings)',
        default=True,
    )
    allow_roster_print_auction_screen = fields.Boolean(
        string='Roster Print (Auction Screen)',
    )
    allow_parallel_sessions = fields.Boolean(
        string='Parallel tournaments (multi-device)',
        default=False,
        help='When enabled, each browser session can select its own working tournament '
             'at the same time (e.g. laptop A on Tournament A, laptop B on Tournament B). '
             'When disabled, switching the navbar updates one shared working tournament '
             'for the login on all devices.',
    )
    allow_mystery_players = fields.Boolean(
        string='Mystery Players',
        default=False,
        help='When enabled, organisers can mark player tiers as Mystery '
             '(hidden identity on the live auction stage until revealed).',
    )

    allowed_player_templates = fields.Char(
        string='Allowed Player Cards',
        help='Comma-separated template keys, e.g. lemon or strawberry,cherry,pistah',
        required=True,
        default='vanilla',
    )

    contact_support = fields.Boolean(
        string='Contact Support for Higher',
        help='Show upgrade-to-support messaging beyond this plan.',
    )

    account_count = fields.Integer(compute='_compute_account_count')

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'Plan code must be unique.'),
        ('max_tournaments_positive', 'CHECK(max_tournaments > 0)',
         'Max tournaments must be positive.'),
        ('max_teams_positive', 'CHECK(max_teams_per_tournament > 0)',
         'Max teams must be positive.'),
        ('max_players_positive', 'CHECK(max_players_per_tournament > 0)',
         'Max players must be positive.'),
        ('validity_days_positive', 'CHECK(validity_days > 0)',
         'Package validity (days) must be positive.'),
    ]

    @api.depends('code')
    def _compute_account_count(self):
        Account = self.env['ac.saas.account']
        for plan in self:
            plan.account_count = Account.search_count([('plan_id', '=', plan.id)])

    @api.depends('list_price', 'max_tournaments', 'currency_id')
    def _compute_price_per_tournament(self):
        for plan in self:
            tournaments = int(plan.max_tournaments or 0)
            amount = float(plan.list_price or 0.0)
            plan.price_per_tournament = (amount / tournaments) if tournaments > 0 else 0.0

    def _format_money(self, amount):
        self.ensure_one()
        currency = self.currency_id or self.env.company.currency_id
        try:
            from odoo.tools.misc import formatLang
            return formatLang(self.env, amount, currency_obj=currency)
        except Exception:
            symbol = (currency.symbol or currency.name or '') if currency else ''
            return ('%s %s' % (symbol, '%.0f' % amount)).strip()

    def get_allowed_templates(self):
        self.ensure_one()
        raw = (self.allowed_player_templates or '').strip()
        if not raw:
            return []
        return [t.strip() for t in raw.split(',') if t.strip()]

    def get_website_price_display(self):
        """Return package price display bits for public pricing cards.

        Returns dict keys: amount, per_tournament, validity (any may be False).
        Example: ₹500  (₹167 per tournament)  Valid for 365 days
        """
        self.ensure_one()
        if not self.show_price_on_website:
            return {
                'amount': False,
                'per_tournament': False,
                'validity': False,
            }
        if (self.price_label or '').strip():
            return {
                'amount': self.price_label.strip(),
                'per_tournament': False,
                'validity': (
                    _('Valid for %s days') % self.validity_days
                    if self.validity_days else False
                ),
            }
        amount = float(self.list_price or 0.0)
        tournaments = int(self.max_tournaments or 0)
        per_tournament = False
        if amount > 0 and tournaments > 0:
            per_unit = amount / float(tournaments)
            per_tournament = _('%s per tournament') % self._format_money(per_unit)
        return {
            'amount': self._format_money(amount) if amount > 0 else False,
            'per_tournament': per_tournament,
            'validity': (
                _('Valid for %s days') % self.validity_days
                if self.validity_days else False
            ),
        }

    def assert_template_allowed(self, template_key):
        self.ensure_one()
        allowed = self.get_allowed_templates()
        if template_key and allowed and template_key not in allowed:
            upgrade = self.get_min_plan_for_template(template_key)
            raise ValidationError(_(
                'Theme "%(tpl)s" is not included in the %(plan)s plan. '
                'Allowed: %(allowed)s.%(upgrade)s'
            ) % {
                'tpl': template_key,
                'plan': self.name,
                'allowed': ', '.join(allowed),
                'upgrade': (
                    _(' Upgrade to %(p)s to enable this theme.') % {'p': upgrade.name}
                    if upgrade else _(' Upgrade your plan or contact support.')
                ),
            })

    def assert_random_mode_allowed(self, algorithm):
        self.ensure_one()
        if algorithm == 'random' and not self.allow_random_mode:
            upgrade = self.get_min_plan_for_random()
            raise ValidationError(_(
                'Lucky Dip is not included in the %(plan)s plan. '
                'Only Roll Call is available (list order or dice by squad number). '
                'Upgrade to %(upgrade)s (or higher) to enable Lucky Dip.'
            ) % {
                'plan': self.name,
                'upgrade': upgrade.name if upgrade else 'Classic',
            })

    @api.model
    def get_min_plan_for_parallel_sessions(self):
        """Cheapest active plan that allows per-browser working tournaments."""
        return self.search([
            ('allow_parallel_sessions', '=', True),
            ('active', '=', True),
        ], order='sequence, id', limit=1)

    @api.model
    def get_min_plan_for_random(self):
        """Cheapest active plan that includes Random + Manual mode."""
        return self.search([
            ('allow_random_mode', '=', True),
            ('active', '=', True),
        ], order='sequence, id', limit=1)

    @api.model
    def get_min_plan_for_mystery(self):
        """Cheapest active plan that includes Mystery player tiers."""
        return self.search([
            ('allow_mystery_players', '=', True),
            ('active', '=', True),
        ], order='sequence, id', limit=1)

    def assert_mystery_allowed(self):
        self.ensure_one()
        if self.allow_mystery_players:
            return
        upgrade = self.get_min_plan_for_mystery()
        raise ValidationError(_(
            'Mystery players are not included in the %(plan)s plan. '
            'Upgrade to %(upgrade)s (or higher) to enable Mystery tiers.'
        ) % {
            'plan': self.name,
            'upgrade': upgrade.name if upgrade else 'Pro',
        })

    @api.model
    def get_min_plan_for_template(self, template_key):
        """Cheapest active plan that includes the given player-card theme."""
        if not template_key:
            return self.browse()
        for plan in self.search([('active', '=', True)], order='sequence, id'):
            if template_key in plan.get_allowed_templates():
                return plan
        return self.browse()

    def get_random_selection_label(self):
        """Label for Lucky Dip (with upgrade hint when locked)."""
        self.ensure_one()
        if self.allow_random_mode:
            return _('Lucky Dip')
        upgrade = self.get_min_plan_for_random()
        return _('Lucky Dip (%(plan)s+)') % {
            'plan': upgrade.name if upgrade else 'Classic',
        }

    def get_template_selection_label(self, template_key, base_label):
        """Label for a theme radio option (short plan suffix when locked)."""
        self.ensure_one()
        allowed = self.get_allowed_templates()
        if not allowed or template_key in allowed:
            return base_label
        upgrade = self.get_min_plan_for_template(template_key)
        if upgrade:
            return _('%(theme)s (%(plan)s+)') % {
                'theme': base_label,
                'plan': upgrade.name,
            }
        return _('%(theme)s (locked)') % {'theme': base_label}

    def get_theme_upgrade_hint(self):
        """One-line caption under the theme radios."""
        self.ensure_one()
        allowed = self.get_allowed_templates()
        if not allowed:
            return False
        labels = {
            'lemon': _('Lemon'),
            'vanilla': _('Vanilla'),
            'butterscotch': _('Butterscotch'),
            'strawberry': _('Strawberry'),
            'cherry': _('Cherry'),
            'pistah': _('Pistah'),
            'blackberry': _('Blackberry'),
        }
        included = ', '.join(labels.get(k, k.title()) for k in allowed)
        return _('%(plan)s plan · included: %(themes)s') % {
            'plan': self.name,
            'themes': included,
        }

    def write(self, vals):
        res = super().write(vals)
        # Re-sync organiser groups when feature / card entitlements change
        feature_keys = {
            'allowed_player_templates',
            'allow_pool_creator',
            'allow_random_mode',
            'allow_auctioneer_console',
            'allow_owner_bidding',
            'allow_parallel_sessions',
            'allow_mystery_players',
            'active',
        }
        if feature_keys & set(vals):
            accounts = self.env['ac.saas.account'].sudo().search([
                ('plan_id', 'in', self.ids),
            ])
            if accounts:
                accounts._sync_user_groups()
        return res
