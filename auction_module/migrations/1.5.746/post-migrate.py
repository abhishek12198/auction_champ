# -*- coding: utf-8 -*-
def migrate(cr, version):
    cr.execute(
        """
        UPDATE auction_tournament
           SET player_display_template = 'blueberry'
         WHERE player_display_template = 'blackberry'
        """
    )
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'ac_saas_plan'
           AND column_name = 'allowed_player_templates'
        """
    )
    if cr.fetchone():
        cr.execute(
            """
            UPDATE ac_saas_plan
               SET allowed_player_templates = replace(
                    allowed_player_templates, 'blackberry', 'blueberry')
             WHERE allowed_player_templates LIKE '%blackberry%'
            """
        )
