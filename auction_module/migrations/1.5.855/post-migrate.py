# -*- coding: utf-8 -*-
def migrate(cr, version):
    """New idle fields land as 0. Live board and bid summary default to 1 minute."""
    cr.execute(
        """
        UPDATE auction_tournament
           SET live_board_screen_idle_min = 1
         WHERE live_board_screen_idle_min IS NULL
            OR live_board_screen_idle_min = 0
        """
    )
    cr.execute(
        """
        UPDATE auction_tournament
           SET bid_summary_screen_idle_min = 1
         WHERE bid_summary_screen_idle_min IS NULL
            OR bid_summary_screen_idle_min = 0
        """
    )
