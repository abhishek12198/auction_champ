# -*- coding: utf-8 -*-
def migrate(cr, version):
    """Entitle Champion (and any blueberry plan) to the new Blackberry theme.

    Existing tournaments keep blueberry. The 1.5.746 rename must not be reversed.
    """
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
    cr.execute(
        "SELECT id, allowed_player_templates, code FROM ac_saas_plan"
    )
    for plan_id, raw, code in cr.fetchall():
        keys = [k.strip() for k in (raw or '').split(',') if k.strip()]
        if not keys or 'blackberry' in keys:
            continue
        if 'blueberry' in keys or code == 'pro_plus':
            keys.append('blackberry')
            cr.execute(
                "UPDATE ac_saas_plan SET allowed_player_templates = %s WHERE id = %s",
                (','.join(keys), plan_id),
            )
