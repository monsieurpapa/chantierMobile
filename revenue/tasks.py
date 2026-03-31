from celery import shared_task
from django.utils import timezone


@shared_task
def mark_overdue_invoices():
    """
    Auto-transition SENT invoices past their due date to OVERDUE.

    Run daily via Celery beat (01:00 Africa/Kigali).
    Queryset already guarantees status=SENT so no per-row validation needed;
    uses bulk_update for a single DB round-trip.

    State machine: SENT → OVERDUE (always valid per Invoice.clean())
    """
    from .models import Invoice
    from chantiermobile.constants import InvoiceStatus

    today = timezone.now().date()
    candidates = list(Invoice.objects.filter(
        status=InvoiceStatus.SENT,
        due_date__lt=today,
    ))

    for invoice in candidates:
        invoice.status = InvoiceStatus.OVERDUE

    if candidates:
        Invoice.objects.bulk_update(candidates, ['status'])

    return {'updated': len(candidates)}
