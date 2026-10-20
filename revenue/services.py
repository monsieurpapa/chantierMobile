"""Devis helpers that span apps (pricing → revenue)."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from chantiermobile.constants import DevisStatus


def next_devis_number(today=None):
    """Next free devis number of the form DEV-<year>-<4 digits>.
    Devis.devis_number is unique across all cabinets, so the sequence is
    global; soft-deleted devis still hold their number."""
    from .models import Devis

    year = (today or timezone.localdate()).year
    prefix = f'DEV-{year}-'
    taken = set(Devis.all_objects.filter(devis_number__startswith=prefix).values_list('devis_number', flat=True))
    n = len(taken) + 1
    while f'{prefix}{n:04d}' in taken:
        n += 1
    return f'{prefix}{n:04d}'


def _with_margin(price, margin_pct):
    price = Decimal(price or 0)
    factor = Decimal('1') + (Decimal(margin_pct or 0) / Decimal('100'))
    return (price * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


@transaction.atomic
def create_devis_from_dqe(dqe, *, client_name, margin_pct=Decimal('0'), issue_date=None, validity_days=30, notes=''):
    """Creates a draft Devis for the DQE's chantier, linked to the DQE
    (source_dqe), with one devis line per DQE line: same étape,
    designation, unit and quantity, and the DQE unit price raised by
    `margin_pct` (%). The devis is an ordinary draft afterwards — edit,
    send and accept it as usual. Raises ValueError if the DQE has no
    chantier (a devis always belongs to one)."""
    from .models import Devis, DevisLine

    if dqe.site_id is None:
        raise ValueError("Ce DQE n'est rattaché à aucun chantier.")
    issue_date = issue_date or timezone.localdate()
    devis = Devis.objects.create(
        site=dqe.site,
        source_dqe=dqe,
        devis_number=next_devis_number(issue_date),
        client_name=client_name,
        issue_date=issue_date,
        validity_date=issue_date + timedelta(days=validity_days) if validity_days else None,
        status=DevisStatus.BROUILLON,
        notes=notes,
    )
    lines = dqe.lines.select_related('price_item', 'phase').order_by('order', 'id')
    DevisLine.objects.bulk_create([
        DevisLine(
            devis=devis,
            phase=line.phase,
            order=i,
            designation=(line.display_designation or '')[:255],
            unit=(line.unit or '')[:20],
            quantity=line.quantity,
            unit_price_ht=_with_margin(line.unit_price, margin_pct),
        )
        for i, line in enumerate(lines)
    ])
    return devis
