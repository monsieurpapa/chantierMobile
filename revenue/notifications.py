"""Email notifications for revenue events.

There is no in-app notification system in this codebase (no Notification
model, no bell icon) — director alerts for payments are sent by email
only, using the project's existing EMAIL_BACKEND (console in DEBUG, SMTP
in production; see chantiermobile/settings.py).
"""
import logging

from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def notify_directors_of_payment(payment, recorded_by=None):
    """Email every DIRECTOR of the payment's cabinet that a client payment
    was recorded. Best-effort: a mail failure is logged, not raised, so it
    never blocks the payment itself from being saved."""
    from accounts.models import UserCabinetRole
    from chantiermobile.constants import UserRoles, ApprovalStatus

    invoice = payment.invoice
    cabinet = invoice.contract.site.cabinet
    director_emails = list(
        UserCabinetRole.objects.filter(
            cabinet=cabinet, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED,
        ).exclude(user__email='').values_list('user__email', flat=True)
    )
    if not director_emails:
        return

    contract = invoice.contract
    subject = _('Paiement reçu — %(site)s') % {'site': contract.site.name}
    recorder_name = (recorded_by.get_full_name() or recorded_by.username) if recorded_by else _('un utilisateur')
    message = _(
        "Un paiement de %(amount)s $ a été enregistré par %(recorder)s.\n\n"
        "Client : %(client)s\n"
        "Chantier : %(site)s\n"
        "Facture : %(invoice)s\n"
        "Méthode : %(method)s\n"
        "Solde restant dû par le client : %(balance)s $\n"
    ) % {
        'amount': f"{payment.amount:.2f}",
        'recorder': recorder_name,
        'client': contract.client_name,
        'site': contract.site.name,
        'invoice': invoice.invoice_number,
        'method': payment.get_method_display(),
        'balance': f"{contract.client_balance:.2f}",
    }

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            recipient_list=director_emails,
            fail_silently=False,
        )
    except Exception:
        # A broken SMTP config must never prevent the payment from being
        # recorded — log and move on.
        logger.exception("Failed to send payment notification email to directors for payment %s", payment.pk)
