# -*- coding: utf-8 -*-
from odoo import models


class IrMailServer(models.Model):
    _inherit = 'ir.mail_server'

    def build_email(self, email_from, email_to, subject, body, email_cc=None,
                    email_bcc=None, reply_to=False, attachments=None,
                    message_id=None, references=None, object_id=False,
                    subtype='plain', headers=None, body_alternative=None,
                    subtype_alternative='plain'):
        """Send welcome-mail images inline.

        Attachments named ``cid:<id>.png`` are embedded with that Content-ID
        instead of being offered as separate downloads. The invoice PDF is
        left as a normal attachment.
        """
        inline = []
        regular = []
        for item in attachments or []:
            name = (item[0] or '') if item else ''
            if name.startswith('cid:') and len(item) >= 3 and item[1]:
                cid = name[4:]
                if '.' in cid:
                    cid = cid.rsplit('.', 1)[0]
                inline.append((cid, item[1], item[2], name[4:]))
            else:
                regular.append(item)
        msg = super().build_email(
            email_from, email_to, subject, body,
            email_cc=email_cc, email_bcc=email_bcc, reply_to=reply_to,
            attachments=regular or None, message_id=message_id,
            references=references, object_id=object_id, subtype=subtype,
            headers=headers, body_alternative=body_alternative,
            subtype_alternative=subtype_alternative,
        )
        for cid, content, mime, filename in inline:
            if mime and '/' in mime:
                main, sub = mime.split('/', 1)
            else:
                main, sub = 'image', 'png'
            msg.add_attachment(
                content, main, sub, cid=cid, filename=filename, disposition='inline',
            )
            part = msg.get_payload()[-1]
            wanted = '<%s>' % cid
            if part.get('Content-ID') != wanted:
                if 'Content-ID' in part:
                    part.replace_header('Content-ID', wanted)
                else:
                    part['Content-ID'] = wanted
        return msg
