# -*- coding: utf-8 -*-
"""Remove orphaned DB records for the reverted player-card wizard feature."""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    _purge_xml_ids(env)
    _purge_tournament_player_card_field(env)


def _purge_xml_ids(env):
    Data = env['ir.model.data'].sudo()
    names = Data.search([
        ('module', '=', 'auction_module'),
        '|', '|', '|',
        ('name', '=like', 'view_auction_player_card_wizard%'),
        ('name', '=like', 'action_auction_player_card_wizard%'),
        ('name', '=like', 'access_auction_player_card_wizard%'),
        ('name', '=', 'model_auction_player_card_wizard'),
    ])
    if names:
        names.unlink()
        _logger.info(
            'auction_module 1.5.661: removed %d player-card wizard xml ids.',
            len(names),
        )


def _purge_tournament_player_card_field(env):
    Field = env['ir.model.fields'].sudo()
    field = Field.search([
        ('model', '=', 'auction.tournament'),
        ('name', '=', 'player_card_count'),
    ], limit=1)
    if not field:
        return
    Data = env['ir.model.data'].sudo()
    meta = Data.search([
        ('module', '=', 'auction_module'),
        ('model', '=', 'ir.model.fields'),
        ('res_id', '=', field.id),
    ])
    if meta:
        meta.unlink()
    field.unlink()
    _logger.info(
        'auction_module 1.5.661: removed auction.tournament.player_card_count.',
    )
