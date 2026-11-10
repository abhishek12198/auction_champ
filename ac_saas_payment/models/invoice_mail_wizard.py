# -*- coding: utf-8 -*-
import base64
import io
import re
import zipfile
from datetime import timedelta
from html import escape

from odoo import api, fields, models, _
from odoo.exceptions import UserError

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class AcSaasInvoiceMailWizard(models.TransientModel):
    _name = 'ac.saas.invoice.mail.wizard'
    _description = 'Email signup invoices for GST filing'

    date_from = fields.Date(string='From date', required=True)
    date_to = fields.Date(string='To date', required=True)
    prepared = fields.Boolean(default=False)
    invoice_count = fields.Integer(string='Invoices', readonly=True)
    zip_file = fields.Binary(string='Invoice ZIP', attachment=True, readonly=True)
    zip_filename = fields.Char()
    email_to = fields.Char(string='To')
    email_cc = fields.Char(string='Cc')
    subject = fields.Char()
    body = fields.Text(string='Email')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        first_this_month = today.replace(day=1)
        last_prev = first_this_month - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        res.setdefault('date_from', first_prev)
        res.setdefault('date_to', last_prev)
        return res

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Email Composer'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _payments_in_range(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_('Choose a from date and a to date.'))
        if self.date_from > self.date_to:
            raise UserError(_('The from date must be on or before the to date.'))
        Payment = self.env['ac.saas.signup.payment'].sudo()
        payments = Payment.search([
            ('state', 'in', ('paid', 'provisioned')),
            '|',
            '&', ('invoice_date', '>=', self.date_from), ('invoice_date', '<=', self.date_to),
            '&', ('invoice_date', '=', False),
                 '&', ('purchase_date', '>=', self.date_from), ('purchase_date', '<=', self.date_to),
        ], order='invoice_date, id')
        missing_date = payments.filtered(lambda pay: not pay.invoice_date)
        if missing_date:
            missing_date._assign_invoice()
        return payments.filtered(
            lambda pay: pay.invoice_date and self.date_from <= pay.invoice_date <= self.date_to
        )

    def _zip_invoices(self, payments):
        buffer = io.BytesIO()
        used = set()
        failed = []
        count = 0
        with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for payment in payments:
                label = payment.invoice_number or payment.name or str(payment.id)
                try:
                    attachment = payment._invoice_attachment()
                    raw = base64.b64decode(attachment.datas or b'')
                except Exception:
                    raw = b''
                if not raw:
                    failed.append(label)
                    continue
                filename = payment._invoice_filename()
                base, ext = filename.rsplit('.', 1) if '.' in filename else (filename, 'pdf')
                candidate = filename
                suffix = 2
                while candidate in used:
                    candidate = '%s-%s.%s' % (base, suffix, ext)
                    suffix += 1
                used.add(candidate)
                archive.writestr(candidate, raw)
                count += 1
        if failed:
            raise UserError(_(
                'Could not build a PDF for: %s'
            ) % ', '.join(failed))
        if not count:
            raise UserError(_('No invoice PDFs were found for this date range.'))
        return buffer.getvalue(), count

    def action_prepare(self):
        self.ensure_one()
        payments = self._payments_in_range()
        if not payments:
            raise UserError(_(
                'No paid signup invoices have an invoice date in this range.'
            ))
        payload, count = self._zip_invoices(payments)
        account = self.env['ac.saas.account']
        start = account._saas_format_date(self.date_from)
        end = account._saas_format_date(self.date_to)
        filename = 'AuctionChamp-GST-Invoices-%s-to-%s.zip' % (
            self.date_from.strftime('%Y%m%d'),
            self.date_to.strftime('%Y%m%d'),
        )
        self.write({
            'prepared': True,
            'invoice_count': count,
            'zip_file': base64.b64encode(payload),
            'zip_filename': filename,
            'subject': _('Auction Champ invoices for GST filing — %s to %s') % (start, end),
            'body': _(
                'Hello,\n\n'
                'Please find attached the Auction Champ subscription invoices for GST filing.\n\n'
                'Invoice dates: %s to %s\n'
                'Number of invoices: %s\n\n'
                'Thank you,\n'
                'Auction Champ'
            ) % (start, end, count),
        })
        return self._reopen()

    def action_back(self):
        self.ensure_one()
        self.write({
            'prepared': False,
            'invoice_count': 0,
            'zip_file': False,
            'zip_filename': False,
        })
        return self._reopen()

    def _addresses(self, raw, label, required):
        parts = [part.strip() for part in re.split(r'[,;]', raw or '') if part.strip()]
        if required and not parts:
            raise UserError(_('Enter a %s email address.') % label)
        invalid = [part for part in parts if not EMAIL_RE.match(part)]
        if invalid:
            raise UserError(_(
                'Check the %s address: %s'
            ) % (label, ', '.join(invalid)))
        return ', '.join(parts)

    def action_send(self):
        self.ensure_one()
        if not self.prepared or not self.zip_file:
            raise UserError(_('Prepare the invoice ZIP before sending.'))
        email_to = self._addresses(self.email_to, _('To'), required=True)
        email_cc = self._addresses(self.email_cc, _('Cc'), required=False)
        if not (self.subject or '').strip():
            raise UserError(_('Enter an email subject.'))
        if not (self.body or '').strip():
            raise UserError(_('Enter the email text.'))

        account = self.env['ac.saas.account']
        account._saas_ensure_mail_default_from()
        sender = account._saas_email_from()
        server = account._saas_mail_server()
        payload = self.with_context(bin_size=False).zip_file
        attachment = self.env['ir.attachment'].sudo().create({
            'name': self.zip_filename or 'AuctionChamp-GST-Invoices.zip',
            'type': 'binary',
            'datas': payload,
            'mimetype': 'application/zip',
        })
        body_html = '<div style="font-family:sans-serif;font-size:14px;line-height:1.5;">%s</div>' % (
            escape(self.body).replace('\n', '<br/>')
        )
        mail = self.env['mail.mail'].sudo().create({
            'subject': self.subject.strip(),
            'body_html': body_html,
            'email_from': sender,
            'email_to': email_to,
            'email_cc': email_cc or False,
            'reply_to': account._saas_sender_address(),
            'message_id': account._saas_message_id(),
            'mail_server_id': server.id if server else False,
            'auto_delete': False,
            'attachment_ids': [(4, attachment.id)],
        })
        attachment.sudo().write({'res_model': 'mail.mail', 'res_id': mail.id})
        mail.send()
        mail.flush()
        if mail.exists() and mail.state == 'exception':
            raise UserError(_(
                'The email could not be sent. %s'
            ) % (mail.failure_reason or ''))
        notify = getattr(self.env.user, 'notify_success', None)
        if notify:
            notify(_('Invoice ZIP sent to %s.') % email_to)
        return {'type': 'ir.actions.act_window_close'}
