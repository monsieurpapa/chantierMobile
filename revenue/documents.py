"""PDF of a devis in the cabinet's letterhead layout (see core/pdf_utils)."""
from django.utils.text import slugify

from chantiermobile.constants import DevisStatus
from core.pdf_utils import Signatory, bordereau_sections, render_bordereau_pdf, status_stamp


def devis_pdf_response(devis, *, generated_by=''):
    lines = devis.lines.select_related('phase__parent_phase').order_by('order', 'id')
    sections = bordereau_sections(
        lines,
        phase_of=lambda l: l.phase,
        designation_of=lambda l: l.designation,
        unit_of=lambda l: l.unit,
        quantity_of=lambda l: l.quantity,
        unit_price_of=lambda l: l.unit_price_ht,
        total_of=lambda l: l.total_ht,
    )
    site = devis.site
    cabinet = site.cabinet
    info_rows = [
        ('Devis n°', devis.devis_number),
        ("Date d'émission", devis.issue_date.strftime('%d/%m/%Y')),
        ("Valable jusqu'au", devis.validity_date.strftime('%d/%m/%Y') if devis.validity_date else '—'),
        ('Chantier', site.name),
        ('Adresse', site.location),
        ("Maître d'ouvrage", devis.client_name),
    ]
    short = getattr(cabinet, 'short_name', '') or cabinet.name
    pour = f"Pour l'{short}" if short[:1].upper() in 'AEIOUYH' else f'Pour {short}'
    signatories = [
        Signatory(pour, 'La Direction Technique'),
        Signatory('Vu pour approbation', "Le Maître d'ouvrage", devis.client_name,
                  stamp=status_stamp(devis, DevisStatus.ACCEPTE, 'Accepté') if devis.status == DevisStatus.ACCEPTE else ''),
    ]
    note = devis.notes or None
    if not sections and devis.photo:
        note = ((note + '\n') if note else '') + 'Devis établi sur document papier (photo jointe dans ChantierMobile).'
    return render_bordereau_pdf(
        filename=f'devis-{slugify(devis.devis_number) or devis.pk}.pdf',
        cabinet=cabinet,
        title=f'DEVIS — {site.name}',
        info_rows=info_rows,
        sections=sections,
        total_label='TOTAL GÉNÉRAL HT',
        signatories=signatories,
        date=devis.issue_date,
        generated_by=generated_by,
        note=note,
    )
