import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Force the player-card landscape paperformat DPI to 85 on existing DBs.

    The player card is laid out in px on a custom mm page, so wkhtmltopdf's
    ``--dpi`` value controls the px -> mm scale. dpi=85 makes the card fill the
    page; the previously shipped dpi=90 renders the same px card ~6% smaller,
    leaving empty space at the bottom/right of the sheet.

    The paperformat record lives in a ``noupdate="1"`` data block, so a plain
    module upgrade never rewrites it (Odoo skips records whose stored
    ``ir_model_data.noupdate`` flag is True). This migration applies the fix
    directly, and only when the value still matches the old default (90) so any
    intentional manual tuning is preserved.
    """
    cr.execute(
        """
        UPDATE report_paperformat p
        SET dpi = 85
        FROM ir_model_data d
        WHERE d.model = 'report.paperformat'
          AND d.module = 'auction_module'
          AND d.name = 'paperformat_card_landscape'
          AND d.res_id = p.id
          AND p.dpi = 90
        """
    )
    if cr.rowcount:
        _logger.info(
            "auction_module: player-card landscape paperformat DPI set to 85 "
            "(%s record updated).",
            cr.rowcount,
        )
