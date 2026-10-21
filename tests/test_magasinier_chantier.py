"""Magasinier of one chantier (2026-10-21).

- A Magasinier role names its chantier; only that person records, edits
  and deletes entrées/sorties there — everyone else reads.
- Editing or deleting a movement keeps the stock right.
- Every entrée has a bon de réception (PDF, quantities only) sent to the
  Directeur technique, who puts a visa on it.
- A Magasinier is scoped to their chantier and never sees prices.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import UserCabinetRole
from chantiermobile.constants import ApprovalStatus, StockMovementType, UserRoles
from core.models import Notification
from core.roles import is_magasinier_only, is_site_magasinier
from materials.models import Material
from procurement.models import StockItem, StockMovement, Supplier


def _user(username, cabinet, role, site=None):
    user = get_user_model().objects.create_user(username=username, password='pw-12345', first_name=username.title())
    UserCabinetRole.objects.create(user=user, cabinet=cabinet, role=role, site=site, status=ApprovalStatus.APPROVED)
    return user


@pytest.fixture
def other_site(site_factory):
    return site_factory(name='Chantier B')


@pytest.fixture
def mag(db, cabinet, site):
    return _user('mag_a', cabinet, UserRoles.MAGASINIER, site)


@pytest.fixture
def mag_client(client, mag):
    client.force_login(mag)
    return client


@pytest.fixture
def dt(db, cabinet):
    return _user('dt_a', cabinet, UserRoles.DIRECTEUR_TECHNIQUE)


@pytest.fixture
def ciment(db):
    return Material.objects.create(name='Ciment MAG-T', unit='sac', estimated_cost_per_unit=Decimal('11.75'))


@pytest.fixture
def stock(site, ciment):
    return StockItem.objects.create(site=site, material=ciment, name=ciment.name, unit='sac', quantity_on_hand=Decimal('50'))


def entry_data(material, qty='20', **extra):
    data = {'material': material.pk, 'quantity': qty, 'movement_date': '2026-10-21', 'motif': '', 'notes': ''}
    data.update(extra)
    return data


@pytest.mark.django_db
class TestRoleBelongsToOneChantier:
    def test_magasinier_requires_a_chantier(self, cabinet, user):
        role = UserCabinetRole(user=user, cabinet=cabinet, role=UserRoles.MAGASINIER)
        with pytest.raises(ValidationError):
            role.full_clean()

    def test_chantier_must_be_in_the_cabinet(self, cabinet, user, site):
        from accounts.models import Cabinet
        other = Cabinet.objects.create(name='Autre cabinet MAG')
        role = UserCabinetRole(user=user, cabinet=other, role=UserRoles.MAGASINIER, site=site)
        with pytest.raises(ValidationError):
            role.full_clean()

    def test_other_roles_drop_the_chantier(self, cabinet, user, site):
        role = UserCabinetRole(user=user, cabinet=cabinet, role=UserRoles.ENGINEER, site=site)
        role.full_clean()
        assert role.site is None

    def test_helpers(self, mag, site, other_site, dt):
        assert is_site_magasinier(mag, site)
        assert not is_site_magasinier(mag, other_site)
        assert is_magasinier_only(mag)
        assert not is_magasinier_only(dt)

    def test_assign_form_from_cabinet_page(self, admin_client, cabinet, site):
        target = get_user_model().objects.create_user(username='future_mag', password='x')
        url = reverse('accounts:admin_assign_user_to_cabinet', kwargs={'cabinet_id': cabinet.pk})
        response = admin_client.post(url, {'user': target.pk, 'role': 'MAGASINIER', 'status': 'APPROVED'})
        assert response.status_code == 200  # chantier missing
        assert not UserCabinetRole.objects.filter(user=target).exists()
        admin_client.post(url, {'user': target.pk, 'role': 'MAGASINIER', 'site': site.pk, 'status': 'APPROVED'})
        assert UserCabinetRole.objects.get(user=target).site == site


@pytest.mark.django_db
class TestEntriesAndExits:
    def test_entry_creates_article_and_bon_de_reception(self, mag_client, mag, site, ciment, dt):
        supplier = Supplier.objects.create(cabinet=site.cabinet, name='Quincaillerie MAG')
        response = mag_client.post(reverse('procurement:stock_movement_new', kwargs={'kind': 'entree'}),
                                   entry_data(ciment, '20', supplier=supplier.pk, delivery_note_ref='BL-77'))
        movement = StockMovement.objects.get(stock_item__site=site, stock_item__material=ciment)
        assert response.status_code == 302
        assert response['Location'] == reverse('procurement:stock_movement_detail', kwargs={'pk': movement.pk})
        assert movement.movement_type == StockMovementType.IN
        assert movement.moved_by == mag
        assert movement.stock_item.material == ciment
        assert movement.stock_item.quantity_on_hand == Decimal('20')
        assert movement.reception_number == f'BR-{movement.pk:05d}'
        note = Notification.objects.get(recipient=dt)
        assert movement.reception_number in note.message

    def test_entry_reuses_existing_article(self, mag_client, site, stock, ciment):
        mag_client.post(reverse('procurement:stock_movement_new', kwargs={'kind': 'entree'}), entry_data(ciment, '5'))
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('55')
        assert StockItem.objects.filter(site=site).count() == 1

    def test_exit_cannot_exceed_stock(self, mag_client, stock):
        url = reverse('procurement:stock_movement_new', kwargs={'kind': 'sortie'})
        response = mag_client.post(url, {'stock_item': stock.pk, 'quantity': '80', 'movement_date': '2026-10-21'})
        assert response.status_code == 200
        assert 'négatif' in response.content.decode()
        mag_client.post(url, {'stock_item': stock.pk, 'quantity': '30', 'movement_date': '2026-10-21', 'motif': 'Dalle'})
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('20')

    def test_exit_offers_only_this_chantiers_articles(self, mag_client, other_site, stock):
        foreign = StockItem.objects.create(site=other_site, name='Sable', unit='m3', quantity_on_hand=10)
        response = mag_client.post(reverse('procurement:stock_movement_new', kwargs={'kind': 'sortie'}),
                                   {'stock_item': foreign.pk, 'quantity': '1', 'movement_date': '2026-10-21'})
        assert response.status_code == 200
        foreign.refresh_from_db()
        assert foreign.quantity_on_hand == 10

    def test_edit_moves_stock_by_the_difference(self, mag_client, stock, ciment, mag):
        m = StockMovement.objects.create(stock_item=stock, movement_type=StockMovementType.IN, quantity=Decimal('10'),
                                         movement_date='2026-10-20', moved_by=mag)
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('60')
        mag_client.post(reverse('procurement:stock_movement_update', kwargs={'pk': m.pk}),
                        entry_data(ciment, '4', stock_item=stock.pk))
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('54')

    def test_edit_resets_visa(self, mag_client, stock, ciment, mag, dt):
        from django.utils import timezone
        m = StockMovement.objects.create(stock_item=stock, movement_type=StockMovementType.IN, quantity=Decimal('10'),
                                         movement_date='2026-10-20', moved_by=mag,
                                         reception_visa_by=dt, reception_visa_at=timezone.now())
        mag_client.post(reverse('procurement:stock_movement_update', kwargs={'pk': m.pk}),
                        entry_data(ciment, '12', stock_item=stock.pk))
        m.refresh_from_db()
        assert m.reception_visa_at is None

    def test_delete_restores_stock_and_refuses_consumed_entry(self, mag_client, stock, mag):
        m = StockMovement.objects.create(stock_item=stock, movement_type=StockMovementType.IN, quantity=Decimal('10'),
                                         movement_date='2026-10-20', moved_by=mag)
        StockMovement.objects.create(stock_item=stock, movement_type=StockMovementType.OUT, quantity=Decimal('55'),
                                     movement_date='2026-10-21', moved_by=mag)
        mag_client.post(reverse('procurement:stock_movement_delete', kwargs={'pk': m.pk}))
        assert StockMovement.objects.filter(pk=m.pk).exists()  # only 5 left: refused
        out = StockMovement.objects.get(stock_item=stock, movement_type=StockMovementType.OUT)
        mag_client.post(reverse('procurement:stock_movement_delete', kwargs={'pk': out.pk}))
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('60')
        assert not StockMovement.objects.filter(pk=out.pk).exists()

    def test_po_receipt_cannot_be_edited(self, mag_client, stock, mag):
        from procurement.models import PurchaseOrder, PurchaseOrderLine
        from datetime import date
        supplier = Supplier.objects.create(cabinet=stock.site.cabinet, name='F')
        po = PurchaseOrder.objects.create(site=stock.site, supplier=supplier, order_number='PO-MAG-1', order_date=date.today())
        line = PurchaseOrderLine.objects.create(purchase_order=po, stock_item=stock, quantity=5, unit_price=2)
        m = StockMovement.objects.create(stock_item=stock, movement_type=StockMovementType.IN, quantity=5,
                                         movement_date=date.today(), purchase_order_line=line)
        mag_client.post(reverse('procurement:stock_movement_delete', kwargs={'pk': m.pk}))
        assert StockMovement.objects.filter(pk=m.pk).exists()


@pytest.mark.django_db
class TestOnlyTheChantiersMagasinier:
    def test_director_cannot_record_entries(self, director_client, ciment, site):
        response = director_client.post(reverse('procurement:stock_movement_new', kwargs={'kind': 'entree'}) + f'?site={site.pk}',
                                        entry_data(ciment))
        assert response.status_code == 302
        assert not StockMovement.objects.filter(stock_item__site=site).exists()

    def test_magasinier_of_another_chantier_cannot_edit(self, client, cabinet, other_site, stock, mag):
        other_mag = _user('mag_b', cabinet, UserRoles.MAGASINIER, other_site)
        m = StockMovement.objects.create(stock_item=stock, movement_type=StockMovementType.IN, quantity=Decimal('10'),
                                         movement_date='2026-10-20', moved_by=mag)
        client.force_login(other_mag)
        client.post(reverse('procurement:stock_movement_delete', kwargs={'pk': m.pk}))
        assert StockMovement.objects.filter(pk=m.pk).exists()

    def test_old_endpoint_entry_reserved_to_magasinier(self, director_client, stock):
        url = reverse('procurement:stock_item_detail', kwargs={'pk': stock.pk}).rstrip('/') + '/mouvement/'
        data = {'movement_type': 'IN', 'quantity': '3', 'movement_date': '2026-10-21'}
        director_client.post(url, data)
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('50')
        director_client.post(url, {**data, 'movement_type': 'ADJUSTMENT', 'quantity': '-2'})
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('48')

    def test_others_read_the_detail(self, director_client, stock, mag):
        m = StockMovement.objects.create(stock_item=stock, movement_type=StockMovementType.IN, quantity=Decimal('10'),
                                         movement_date='2026-10-20', moved_by=mag)
        response = director_client.get(reverse('procurement:stock_movement_detail', kwargs={'pk': m.pk}))
        assert response.status_code == 200
        assert response.context['can_edit'] is False
        assert reverse('procurement:stock_movement_update', kwargs={'pk': m.pk}).encode() not in response.content


@pytest.mark.django_db
class TestBonDeReception:
    @pytest.fixture
    def entry(self, stock, mag):
        return StockMovement.objects.create(stock_item=stock, movement_type=StockMovementType.IN, quantity=Decimal('10'),
                                            movement_date='2026-10-20', moved_by=mag, delivery_note_ref='BL-9')

    def test_pdf(self, mag_client, entry):
        response = mag_client.get(reverse('procurement:bon_de_reception_pdf', kwargs={'pk': entry.pk}))
        assert response.status_code == 200
        assert response['Content-Type'] == 'application/pdf'
        assert entry.reception_number in response['Content-Disposition']

    def test_pdf_has_quantities_not_prices(self, mag_client, entry):
        from io import BytesIO
        from pypdf import PdfReader
        response = mag_client.get(reverse('procurement:bon_de_reception_pdf', kwargs={'pk': entry.pk}))
        text = ''.join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
        assert 'BON DE RÉCEPTION' in text or 'BON DE R' in text
        assert 'BL-9' in text and 'Directeur Technique' in text
        assert '11,75' not in text and '$' not in text

    def test_detail_shows_bon(self, director_client, entry):
        response = director_client.get(reverse('procurement:stock_movement_detail', kwargs={'pk': entry.pk}))
        assert reverse('procurement:bon_de_reception_pdf', kwargs={'pk': entry.pk}).encode() in response.content

    def test_exit_has_no_bon(self, mag_client, stock, mag):
        out = StockMovement.objects.create(stock_item=stock, movement_type=StockMovementType.OUT, quantity=1,
                                           movement_date='2026-10-21', moved_by=mag)
        response = mag_client.get(reverse('procurement:bon_de_reception_pdf', kwargs={'pk': out.pk}))
        assert response.status_code == 404

    def test_dt_visa(self, client, dt, mag, entry):
        client.force_login(mag)
        client.post(reverse('procurement:stock_movement_visa', kwargs={'pk': entry.pk}))
        entry.refresh_from_db()
        assert entry.reception_visa_at is None  # magasinier cannot
        client.force_login(dt)
        client.post(reverse('procurement:stock_movement_visa', kwargs={'pk': entry.pk}))
        entry.refresh_from_db()
        assert entry.reception_visa_by == dt
        assert Notification.objects.filter(recipient=mag, message__contains=entry.reception_number).exists()


@pytest.mark.django_db
class TestMagasinierView:
    def test_report_scoped_to_their_chantier(self, mag_client, stock, other_site):
        StockItem.objects.create(site=other_site, name='Sable caché', unit='m3', quantity_on_hand=3)
        response = mag_client.get(reverse('procurement:stock_report'))
        content = response.content.decode()
        assert stock.name in content
        assert 'Sable caché' not in content
        assert reverse('procurement:stock_movement_new', kwargs={'kind': 'entree'}) in content

    def test_hide_prices_flag(self, mag_client):
        assert bool(mag_client.get(reverse('procurement:stock_report')).context['hide_prices']) is True

    def test_director_sees_prices(self, director_client):
        assert bool(director_client.get(reverse('procurement:stock_report')).context['hide_prices']) is False


@pytest.mark.django_db
class TestPriceWall:
    def test_money_sections_redirect(self, mag_client):
        for name in ('finance:expense_list', 'revenue:contract_list', 'pricing:dqe_list', 'personnel:personnel_list'):
            response = mag_client.get(reverse(name))
            assert response.status_code == 302, name
            assert response['Location'] == reverse('procurement:stock_report')

    def test_director_not_redirected(self, director_client):
        assert director_client.get(reverse('finance:expense_list')).status_code == 200

    def test_no_prices_on_purchase_order_or_catalogue(self, mag_client, stock, ciment):
        from datetime import date
        from procurement.models import PurchaseOrder, PurchaseOrderLine
        supplier = Supplier.objects.create(cabinet=stock.site.cabinet, name='F')
        po = PurchaseOrder.objects.create(site=stock.site, supplier=supplier, order_number='PO-MAG-9', order_date=date.today())
        PurchaseOrderLine.objects.create(purchase_order=po, stock_item=stock, quantity=4, unit_price=Decimal('48213.77'))
        for url in (reverse('procurement:purchase_order_detail', kwargs={'pk': po.pk}),
                    reverse('procurement:purchase_order_list'), reverse('materials:material_list')):
            content = mag_client.get(url).content.decode()
            assert not any(x in content for x in ('48213', '48 213', '48,213', '48.213', '192855', '192 855', '11,75', '11.75')), url

    def test_materials_data_api_hides_cost(self, mag_client, ciment):
        data = mag_client.get(reverse('materials:materials_data')).json()
        assert data[str(ciment.pk)]['cost_per_unit'] == 0

    def test_other_chantier_hidden(self, mag_client, other_site):
        response = mag_client.get(reverse('projects:site_detail', kwargs={'unique_id': other_site.unique_id}))
        assert response.status_code == 404

    def test_magasinier_can_receive_their_purchase_order(self, mag_client, stock, dt):
        from datetime import date
        from chantiermobile.constants import PurchaseOrderStatus
        from procurement.models import PurchaseOrder, PurchaseOrderLine
        supplier = Supplier.objects.create(cabinet=stock.site.cabinet, name='F2')
        po = PurchaseOrder.objects.create(site=stock.site, supplier=supplier, order_number='PO-MAG-10',
                                          order_date=date.today(), status=PurchaseOrderStatus.ENVOYEE)
        PurchaseOrderLine.objects.create(purchase_order=po, stock_item=stock, quantity=4, unit_price=1)
        mag_client.post(reverse('procurement:purchase_order_receive', kwargs={'pk': po.pk}))
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('54')
        movement = StockMovement.objects.get(purchase_order_line__purchase_order=po)
        assert movement.effective_supplier == supplier
        assert Notification.objects.filter(recipient=dt, message__contains=movement.reception_number).exists()


@pytest.mark.django_db
class TestSuperadminNeverLockedOut:
    """Standing rule (CLAUDE.md): every access limit lets a superadmin through."""

    def test_superadmin_records_edits_and_deletes(self, admin_client, site, ciment, stock):
        url = reverse('procurement:stock_movement_new', kwargs={'kind': 'entree'}) + f'?site={site.pk}'
        response = admin_client.post(url, entry_data(ciment, '6'))
        assert response.status_code == 302
        movement = StockMovement.objects.filter(stock_item=stock).latest('pk')
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('56')
        detail = admin_client.get(reverse('procurement:stock_movement_detail', kwargs={'pk': movement.pk}))
        assert detail.context['can_edit'] is True
        admin_client.post(reverse('procurement:stock_movement_update', kwargs={'pk': movement.pk}),
                          entry_data(ciment, '2', stock_item=stock.pk))
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('52')
        admin_client.post(reverse('procurement:stock_movement_delete', kwargs={'pk': movement.pk}))
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('50')

    def test_superadmin_sortie_and_transfer(self, admin_client, stock, other_site):
        admin_client.post(reverse('procurement:stock_movement_new', kwargs={'kind': 'sortie'}) + f'?site={stock.site.pk}',
                          {'stock_item': stock.pk, 'quantity': '5', 'movement_date': '2026-10-21'})
        admin_client.post(reverse('procurement:stock_transfer_create', kwargs={'pk': stock.pk}),
                          {'destination_site': other_site.pk, 'quantity': '5'})
        stock.refresh_from_db()
        assert stock.quantity_on_hand == Decimal('40')

    def test_superadmin_sees_entry_buttons_once_a_chantier_is_chosen(self, admin_client, site):
        content = admin_client.get(reverse('procurement:stock_report') + f'?site={site.pk}').content.decode()
        assert reverse('procurement:stock_movement_new', kwargs={'kind': 'entree'}) in content

    def test_superadmin_sees_prices_and_everything(self, admin_client):
        assert bool(admin_client.get(reverse('procurement:stock_report')).context['hide_prices']) is False
        assert admin_client.get(reverse('finance:expense_list')).status_code == 200
