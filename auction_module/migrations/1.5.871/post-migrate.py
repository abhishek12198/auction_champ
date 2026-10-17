# -*- coding: utf-8 -*-
def migrate(cr, version):
    """Entitle every plan to the new Standard theme (new tournament default)."""
    cr.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_name = 'ac_saas_plan'
           AND column_name = 'allowed_player_templates'
        """
    )
    if not cr.fetchone():
        return
    cr.execute("SELECT id, allowed_player_templates FROM ac_saas_plan")
    for plan_id, raw in cr.fetchall():
        keys = [k.strip() for k in (raw or '').split(',') if k.strip()]
        if 'standard' in keys:
            continue
        keys.insert(0, 'standard')
        cr.execute(
            "UPDATE ac_saas_plan SET allowed_player_templates = %s WHERE id = %s",
            (','.join(keys), plan_id),
        )
