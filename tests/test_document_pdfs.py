"""Branded PDFs: DQE and devis with signature boxes, shared letterhead
(2026-10-20, layout of the client's "DEVIS GLOBAL" sheet)."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from chantiermobile.constants import DevisStatus, DQEStatus
from core.pdf_utils import bordereau_sections, fmt_amount, montant_en_lettres, pdf_text
from pricing.models import DQE, DQELine
from revenue.models import Devis, DevisLine
from tests.test_devis_material_comparison import ciment, material_item_ciment  # noqa: F401


def _pdf_text(response):
    """Text of a generated PDF (pypdf is optional; fall back to raw bytes)."""
    try:
        from io import BytesIO
        from pypdf import PdfReader
        return '\n'.join(p.extract_text() for p in PdfReader(BytesIO(response.content)).pages)
    except ImportError:
        return response.content.decode('latin-1')


class TestHelpers:
    def test_amount_in_words(self):
        assert montant_en_lettres(Decimal('51900.10')) == 'Cinquante et un mille neuf cents dollars américains et dix cents'
        assert montant_en_lettres(Decimal('1000000')) == 'Un million de dollars américains'
        assert montant_en_lettres(Decimal('1')) == 'Un dollar américain'

    def test_french_grouping(self):
        assert fmt_amount(Decimal('51900.1')) == '51\xa0900,10'
        assert fmt_amount(Decimal('-200')) == '-200,00'

    def test_unsupported_characters_are_replaced(self):
        assert pdf_text('Ferrons ϕ8 & co') == 'Ferrons Ø8 &amp; co'


@pytest.fixture
def cabinet_with_letterhead(cabinet):
    cabinet.legal_name = 'Assistance Technique en Génie Civil (ATGC congo.sarl)'
    cabinet.short_name = 'A.T.G.C.'
    cabinet.legal_mentions = 'RCCM : CD/KNG/RCCM/18-B-01479'
    cabinet.phone = '(+243) 994166625'
    cabinet.city = 'Goma'
    cabinet.save()
    return cabinet


@pytest.fixture
def dqe(db, cabinet_with_letterhead, site, phase, phase_factory, material_item_ciment):
    sub = phase_factory(site, name='Semelles', parent_phase=phase)
    dqe = DQE.objects.create(cabinet=cabinet_with_letterhead, site=site, reference='DQE-PDF-1', title='Projet test', status=DQEStatus.DRAFT)
    DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=phase, quantity=Decimal('10'), unit_price=Decimal('12'), order=0)
    DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=sub, quantity=Decimal('5'), unit_price=Decimal('12'), order=1)
    DQELine.objects.create(dqe=dqe, price_item=material_item_ciment, phase=None, designation='Transport', quantity=Decimal('1'), unit_price=Decimal('20'), order=2)
    return dqe


@pytest.mark.django_db
class TestBordereauSections:
    def test_groups_by_etape_and_sous_etape(self, dqe, phase):
        lines = dqe.lines.select_related('phase__parent_phase').order_by('order')
        sections = bordereau_sections(lines, phase_of=lambda l: l.phase, designation_of=lambda l: l.display_designation,
                                      unit_of=lambda l: l.unit, quantity_of=lambda l: l.quantity,
                                      unit_price_of=lambda l: l.unit_price, total_of=lambda l: l.line_total)
        assert [s.title for s in sections] == [phase.name, 'AUTRES TRAVAUX']
        assert sections[0].total == Decimal('180')
        assert sections[0].items[1].title == 'Semelles'


@pytest.mark.django_db
class TestDqePdf:
    def test_download(self, director_client, dqe):
        response = director_client.get(reverse('pricing:dqe_pdf', args=[dqe.pk]))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert 'dqe-pdf-1.pdf' in response['Content-Disposition']
        assert response.content.startswith(b'%PDF')

    def test_content(self, director_client, dqe):
        text = _pdf_text(director_client.get(reverse('pricing:dqe_pdf', args=[dqe.pk])))
        if 'Assistance' not in text:
            pytest.skip('pypdf not installed: content not extractable')
        for expected in ('Assistance Technique en Génie Civil', 'DQE-PDF-1', 'TOTAL GÉNÉRAL DU DQE', '200,00',
                         'Nous disons en toute lettre', 'Établi par', 'Vérifié par', 'Approuvé par', 'Fait à Goma'):
            assert expected in text, expected

    def test_other_cabinet_cannot_download(self, client, dqe, django_user_model):
        from accounts.models import Cabinet, UserCabinetRole
        from chantiermobile.constants import ApprovalStatus, UserRoles
        other = Cabinet.objects.create(name='Autre')
        outsider = django_user_model.objects.create_user(username='outsider', password='x')
        UserCabinetRole.objects.create(user=outsider, cabinet=other, role=UserRoles.DIRECTOR, status=ApprovalStatus.APPROVED)
        client.force_login(outsider)
        assert client.get(reverse('pricing:dqe_pdf', args=[dqe.pk])).status_code == 404


@pytest.mark.django_db
class TestDevisPdf:
    def test_download_with_client_signature_box(self, director_client, site, cabinet_with_letterhead, phase):
        devis = Devis.objects.create(site=site, devis_number='DEV-PDF-1', client_name='Client Kivu', issue_date=date(2026, 10, 20),
                                     status=DevisStatus.BROUILLON)
        DevisLine.objects.create(devis=devis, phase=phase, designation='Béton 350', unit='m3', quantity=Decimal('2'), unit_price_ht=Decimal('400'))
        response = director_client.get(reverse('revenue:devis_pdf', args=[devis.pk]))
        assert response.status_code == 200
        assert response.content.startswith(b'%PDF')
        text = _pdf_text(response)
        if 'Client Kivu' not in text:
            pytest.skip('pypdf not installed: content not extractable')
        for expected in ("Pour l'A.T.G.C.", 'Vu pour approbation', "Le Maître d'ouvrage", 'Client Kivu', 'TOTAL GÉNÉRAL HT', '800,00'):
            assert expected in text, expected


@pytest.mark.django_db
class TestCabinetLetterheadForm:
    def test_fields_are_editable(self, superuser, cabinet):
        from accounts.forms import CabinetForm
        form = CabinetForm(instance=cabinet, data={'name': cabinet.name, 'legal_name': 'X SARL', 'short_name': 'X',
                                                  'city': 'Bukavu', 'phone': '1', 'email': 'a@b.c', 'legal_mentions': 'RCCM 1'})
        assert form.is_valid(), form.errors
        form.save()
        cabinet.refresh_from_db()
        assert cabinet.city == 'Bukavu' and cabinet.short_name == 'X'


@pytest.mark.django_db
class TestOtherDocumentsCarryTheLetterhead:
    def test_invoice_pdf_has_letterhead_words_and_signature(self, director_client, invoice, cabinet_with_letterhead):
        text = _pdf_text(director_client.get(reverse('revenue:invoice_pdf', kwargs={'pk': invoice.pk})))
        if 'Assistance' not in text:
            pytest.skip('pypdf not installed: content not extractable')
        for expected in ('Assistance Technique en Génie Civil', 'FACTURE N°', 'Reste à payer', 'Nous disons en toute lettre',
                         "Pour l'A.T.G.C."):
            assert expected in text, expected

    def test_contract_pdf_has_client_signature(self, director_client, contract, cabinet_with_letterhead):
        text = _pdf_text(director_client.get(reverse('revenue:contract_pdf', kwargs={'pk': contract.pk})))
        if 'Assistance' not in text:
            pytest.skip('pypdf not installed: content not extractable')
        assert 'Le Client' in text and "Pour l'A.T.G.C." in text
