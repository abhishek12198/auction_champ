# -*- coding: utf-8 -*-
"""Detach leftover display_auction inherits before the shared HUD loads.

Flavor templates are now thin t-call wrappers. Old xpaths such as
auction-single-buttons / lm-actions would fail validation on upgrade.
"""

_FLAVOR_TEMPLATES = (
    'player_template_new',
    'player_template_butterscotch',
    'player_template_strawberry',
    'player_template_cherry',
    'player_template_pistah',
    'player_template_lemon',
    'player_template_blackberry',
    'player_template_blueberry',
)


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_ui_view child
           SET active = false,
               inherit_id = NULL
          FROM ir_ui_view parent
          JOIN ir_model_data d
            ON d.res_id = parent.id
           AND d.model = 'ir.ui.view'
         WHERE child.inherit_id = parent.id
           AND d.module = 'auction_module'
           AND d.name IN %s
        """,
        (_FLAVOR_TEMPLATES,),
    )
