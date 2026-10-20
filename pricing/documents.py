"""PDF of a DQE in the cabinet's letterhead layout (see core/pdf_utils)."""
from django.utils.text import slugify

from chantiermobile.constants import DQEStatus, DevisStatus
from core.pdf_utils import (
    Signatory, bordereau_sections, person_name, render_bordereau_pdf, status_stamp,
)


def dqe_client_name(dqe):
    """The maître d'ouvrage for a DQE: the client of the chantier's accepted
    devis (or its latest devis)."""
    if dqe.site_id is None:
        return ''
    devis = (dqe.site.devis_set.filter(status=DevisStatus.ACCEPTE).first()
             or dqe.site.devis_set.exclude(client_name='').order_by('-issue_date', '-pk').first())
    return devis.client_name if devis else ''


def dqe_pdf_response(dqe, *, generated_by=''):
    lines = dqe.lines.select_related('price_item', 'phase__parent_phase').order_by('order', 'id')
    sections = bordereau_sections(
        lines,
        phase_of=lambda l: l.phase,
        designation_of=lambda l: l.display_designation,
        unit_of=lambda l: l.unit,
        quantity_of=lambda l: l.quantity,
        unit_price_of=lambda l: l.unit_price,
        total_of=lambda l: l.line_total,
    )
    site = dqe.site
    info_rows = [
        ('Document', 'Détail quantitatif estimatif (DQE)'),
        ('Référence', dqe.reference),
        ('Chantier', site.name if site else '—'),
        ('Adresse', site.location if site else ''),
        ("Maître d'ouvrage", dqe_client_name(dqe)),
        ('Statut', dqe.get_status_display()),
    ]
    approved = dqe.status in (DQEStatus.APPROUVE, DQEStatus.VALIDATED)
    signatories = [
        Signatory('Établi par', "Bureau d'études", person_name(dqe.created_by)),
        Signatory('Vérifié par', 'La Direction Technique'),
        Signatory('Approuvé par', 'La Direction Générale',
                  stamp=status_stamp(dqe, DQEStatus.APPROUVE, 'Approuvé') if approved else ''),
    ]
    return render_bordereau_pdf(
        filename=f'{slugify(dqe.reference) or "dqe"}.pdf',
        cabinet=dqe.cabinet,
        title=dqe.title,
        info_rows=info_rows,
        sections=sections,
        total_label='TOTAL GÉNÉRAL DU DQE',
        signatories=signatories,
        generated_by=generated_by,
        note=dqe.notes or None,
    )
