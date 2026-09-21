# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
#  CONFIDENTIAL & PROPRIETARY
#
#  This source code, including but not limited to its algorithms, business
#  logic, database structures, models, controllers, views, reports, templates,
#  APIs, documentation, and related materials, constitutes proprietary and
#  confidential information owned exclusively by AuctionChamp.
#
#  This software is protected by applicable copyright laws and international
#  intellectual property treaties. Unauthorized copying, reproduction,
#  modification, distribution, publication, sublicensing, reverse engineering,
#  decompilation, disassembly, disclosure, or use of this software, in whole
#  or in part, is strictly prohibited without the prior written permission of
#  AuctionChamp.
#
#  This software is licensed, not sold. Possession of the source code does not
#  grant any right to copy, modify, redistribute, or create derivative works
#  except as expressly permitted under a valid written license agreement with
#  AuctionChamp.
#
#  Any unauthorized use may result in civil and criminal penalties under
#  applicable intellectual property and copyright laws.
#
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

import logging
import re
import unicodedata

from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Reserved path segments under /player/register/<slug>
_REGISTRATION_SLUG_RESERVED = frozenset({
    'admin', 'players', 'events', 'check_mobile',
})


def _tier_slugify(text):
    """URL-friendly slug from a tier name (same rules as tournament slugs)."""
    value = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode('ascii')
    value = value.lower()
    value = re.sub(r'[^\w\s-]', '', value)
    value = re.sub(r'[\s_]+', '-', value)
    return value.strip('-')


class AuctionPlayerTier(models.Model):
    _name = 'auction.player.tier'
    _inherit = ['auction.tournament.security.mixin']
    _description = 'Auction Player Tier'
    _order = 'sequence, id'

    name = fields.Char(string='Tier Name', required=True)
    description = fields.Char(string='Description')
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Auction / categorization order for this tier (lower = earlier).',
    )
    color = fields.Selection([
        ('#e74c3c', 'Red'),
        ('#e67e22', 'Orange'),
        ('#f39c12', 'Yellow'),
        ('#2ecc71', 'Green'),
        ('#1abc9c', 'Teal'),
        ('#3498db', 'Blue'),
        ('#2980b9', 'Dark Blue'),
        ('#9b59b6', 'Purple'),
        ('#e91e63', 'Pink'),
        ('#34495e', 'Dark'),
        ('#7f8c8d', 'Gray'),
        ('#ffffff', 'White'),
    ], string='Color', default='#3498db')
    is_an_icon_tier = fields.Boolean(string='Icon Tier', default=False)
    mystery = fields.Boolean(
        string='Mystery',
        default=False,
        help='When enabled, players in this tier are shown as Mystery Players on '
             'the live auction stage (photo, name, role/position and attributes '
             'hidden until revealed after the sale).',
    )
    tournament_id = fields.Many2one(
        'auction.tournament',
        string='Tournament',
        ondelete='restrict',
    )
    registration_slug = fields.Char(
        string='Registration URL Slug',
        compute='_compute_registration_slug',
        store=True,
        index=True,
        help='Auto-generated from the tier name for /player/register/<slug> links.',
    )
    max_registrations = fields.Integer(
        string='Max Registrations',
        default=0,
        help='Maximum draft players that can self-register into this tier via its '
             'dedicated registration URL. Set to 0 for unlimited (until the '
             'tournament Max Registrations cap is hit). '
             'When tournament Max Registrations is set and any regular tier has a '
             'limit, the sum of regular-tier limits must equal the tournament max. '
             'Not used for Icon or Mystery tiers.',
    )
    registration_url = fields.Char(
        string='Registration URL',
        compute='_compute_registration_url',
        help='Public self-registration link locked to this tier '
             '(regular tiers only; blank for Icon / Mystery).',
    )
    registered_count = fields.Integer(
        string='Registered (Draft)',
        compute='_compute_registered_count',
        help='Draft players currently registered under this tier.',
    )
    allow_tier_registration = fields.Boolean(
        string='Allows Tier Registration Link',
        compute='_compute_allow_tier_registration',
        help='True when this tier can have a dedicated /player/register/<slug> URL.',
    )

    _sql_constraints = [
        (
            'registration_slug_tournament_uniq',
            'unique(tournament_id, registration_slug)',
            'Each tier registration URL slug must be unique within a tournament.',
        ),
    ]

    def init(self):
        """Create tier registration columns on registry load without requiring -u."""
        self._ensure_tier_registration_columns()

    def _register_hook(self):
        super()._register_hook()
        try:
            with self.env.cr.savepoint():
                self._ensure_tier_registration_columns()
        except Exception:
            _logger.warning(
                'auction.player.tier schema self-heal skipped '
                '(transaction already aborted?)',
                exc_info=True,
            )

    @api.model
    def _ensure_tier_registration_columns(self):
        """Hot-deploy: add registration_slug / max_registrations if missing."""
        cr = self.env.cr
        cr.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'auction_player_tier'
            )
        """)
        if not cr.fetchone()[0]:
            return

        cr.execute("""
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'auction_player_tier'
               AND column_name = 'registration_slug'
        """)
        if not cr.fetchone():
            cr.execute("""
                ALTER TABLE auction_player_tier
                    ADD COLUMN registration_slug varchar
            """)
            _logger.info('auction_module: added auction_player_tier.registration_slug')

        cr.execute("""
            SELECT 1
              FROM information_schema.columns
             WHERE table_name = 'auction_player_tier'
               AND column_name = 'max_registrations'
        """)
        if not cr.fetchone():
            cr.execute("""
                ALTER TABLE auction_player_tier
                    ADD COLUMN max_registrations integer DEFAULT 0
            """)
            cr.execute("""
                UPDATE auction_player_tier
                   SET max_registrations = 0
                 WHERE max_registrations IS NULL
            """)
            _logger.info('auction_module: added auction_player_tier.max_registrations')

        self._backfill_registration_slugs()
        self._ensure_registration_slug_unique_index()

    @api.model
    def _backfill_registration_slugs(self):
        """Fill empty registration_slug values from tier names (idempotent)."""
        cr = self.env.cr
        cr.execute("""
            SELECT id, name, tournament_id, registration_slug
              FROM auction_player_tier
             WHERE registration_slug IS NULL OR registration_slug = ''
        """)
        rows = cr.fetchall()
        if not rows:
            return

        # Existing slugs per tournament for collision avoidance
        cr.execute("""
            SELECT tournament_id, registration_slug
              FROM auction_player_tier
             WHERE registration_slug IS NOT NULL AND registration_slug <> ''
        """)
        used = {}
        for tournament_id, slug in cr.fetchall():
            used.setdefault(tournament_id or 0, set()).add(slug)

        for tier_id, name, tournament_id, _old in rows:
            base = _tier_slugify(name or '') or 'tier'
            if base in _REGISTRATION_SLUG_RESERVED:
                base = '%s-tier' % base
            key = tournament_id or 0
            bucket = used.setdefault(key, set())
            slug = base
            n = 2
            while slug in bucket:
                slug = '%s-%s' % (base, n)
                n += 1
            bucket.add(slug)
            cr.execute(
                "UPDATE auction_player_tier SET registration_slug = %s WHERE id = %s",
                (slug, tier_id),
            )
        _logger.info(
            'auction_module: backfilled registration_slug on %s tier(s)',
            len(rows),
        )

    @api.model
    def _ensure_registration_slug_unique_index(self):
        cr = self.env.cr
        cr.execute("""
            SELECT 1 FROM pg_indexes
             WHERE tablename = 'auction_player_tier'
               AND indexname = 'auction_player_tier_registration_slug_tournament_uniq'
        """)
        if cr.fetchone():
            return
        try:
            cr.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS
                    auction_player_tier_registration_slug_tournament_uniq
                    ON auction_player_tier (tournament_id, registration_slug)
            """)
        except Exception:
            _logger.warning(
                'auction_module: could not create registration_slug unique index '
                '(duplicate slugs may still exist)',
                exc_info=True,
            )

    @api.depends('name')
    def _compute_registration_slug(self):
        for rec in self:
            slug = _tier_slugify(rec.name or '')
            rec.registration_slug = slug or 'tier'

    @api.depends('is_an_icon_tier', 'mystery')
    def _compute_allow_tier_registration(self):
        for rec in self:
            rec.allow_tier_registration = (
                not bool(rec.is_an_icon_tier) and not bool(rec.mystery)
            )

    @api.depends(
        'registration_slug', 'tournament_id', 'tournament_id.slug',
        'is_an_icon_tier', 'mystery',
    )
    def _compute_registration_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        db_name = self.env.cr.dbname
        for rec in self:
            if (
                rec.is_an_icon_tier
                or rec.mystery
                or not rec.registration_slug
                or not rec.tournament_id
                or not rec.tournament_id.slug
            ):
                rec.registration_url = False
                continue
            rec.registration_url = '{}/{}/{}/player/register/{}'.format(
                base_url, db_name, rec.tournament_id.slug, rec.registration_slug,
            )

    def _compute_registered_count(self):
        Player = self.env['auction.team.player'].sudo().with_context(
            auction_skip_tournament_security=True,
        )
        for rec in self:
            if not rec.id:
                rec.registered_count = 0
                continue
            rec.registered_count = Player.search_count([
                ('tier_id', '=', rec.id),
                ('state', '=', 'draft'),
            ])

    def is_registration_eligible(self):
        """Whether this tier may be used on a dedicated registration URL."""
        self.ensure_one()
        return bool(self.allow_tier_registration)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        if not defaults.get('tournament_id'):
            user_tournament = self.env.user.tournament_id
            if user_tournament:
                defaults['tournament_id'] = user_tournament.id
        tournament_id = defaults.get('tournament_id')
        if tournament_id and 'sequence' in fields_list and 'sequence' not in defaults:
            last = self.search(
                [('tournament_id', '=', tournament_id)],
                order='sequence desc, id desc',
                limit=1,
            )
            defaults['sequence'] = (last.sequence or 0) + 10 if last else 10
        return defaults

    def action_migrate_tier(self):
        self.ensure_one()
        return self.env['auction.migrate.tier'].with_context(active_id=self.id).action_open_wizard()

    @api.constrains('is_an_icon_tier', 'tournament_id')
    def _check_single_icon_tier(self):
        for record in self:
            if record.is_an_icon_tier:
                domain = [
                    ('is_an_icon_tier', '=', True),
                    ('id', '!=', record.id),
                ]
                if record.tournament_id:
                    domain.append(('tournament_id', '=', record.tournament_id.id))
                existing = self.search(domain, limit=1)
                if existing:
                    raise ValidationError(
                        'Only one tier can be marked as the Icon Tier per tournament. '
                        '"%s" is already set as the Icon Tier. '
                        'Please unmark it first before setting a new one.' % existing.name
                    )

    @api.constrains('registration_slug', 'tournament_id')
    def _check_registration_slug(self):
        for record in self:
            slug = (record.registration_slug or '').strip().lower()
            if not slug:
                raise ValidationError('Tier registration URL slug cannot be empty.')
            if slug in _REGISTRATION_SLUG_RESERVED:
                raise ValidationError(
                    'Tier name "%s" produces a reserved registration URL slug ("%s"). '
                    'Please rename the tier.' % (record.name or '', slug)
                )

    @api.constrains(
        'max_registrations', 'tournament_id', 'is_an_icon_tier', 'mystery',
    )
    def _check_tier_registration_limits_sum(self):
        if self.env.context.get('skip_tier_registration_limit_check'):
            return
        tournaments = self.mapped('tournament_id')
        for tournament in tournaments:
            tournament._check_tier_registration_limits_sum()
