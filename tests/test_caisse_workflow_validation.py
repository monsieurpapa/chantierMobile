"""Tests for the 2026-10-19 "Workflow validation" feature (meeting-note
backlog item 11): a CaisseTransaction now has its own detail page (there
was none before — only the ledger table's paperclip icon opened the
proof file directly), where:

- a manually-entered movement can be linked to an existing état de
  besoin (materials.MaterialRequest) via the new `material_request` FK,
  and carry a `delivery_note` ("bon de réception") in addition to the
  existing `proof` ("justificatif/facture");
- a SORTIE movement can be e-signed by the DG/bureau technique
  (FINAL_AUTHORIZATION_ROLES) via CaisseTransaction.sign_by_dg(), at any
  time — including well after the movement was recorded ("signature
  rétroactive").

A transaction paid through the normal Expense circuit (Expense.pay())
already links back to its état de besoin via expense.material_request —
the new `material_request` FK only matters for a movement entered
directly on the caisse, with no Expense involved.
"""
from decimal import Decimal

import pytest
from django.urls import reverse

from finance.models import Caisse, CaisseTransaction
from chantiermobile.constants import CaisseTransactionType


@pytest.fixture
def caisse(db, cabinet, site):
    return Caisse.objects.create(cabinet=cabinet, name='Caisse Chantier', site=site)


@pytest.mark.django_db
class TestMaterialRequestAndDeliveryNoteLink:
    def test_can_link_a_manual_movement_to_an_existing_material_request(self, director_client, caisse, site, material_request_factory, user):
        mr = material_request_factory(site=site)
        response = director_client.post(reverse('finance:caisse_transaction_create', kwargs={'pk': caisse.pk}), {
            'transaction_type': CaisseTransactionType.SORTIE, 'amount': '100.00', 'date': '2026-10-19',
            'material_request': str(mr.pk),
        })
        assert response.status_code == 302
        tx = CaisseTransaction.objects.get(caisse=caisse)
        assert tx.material_request_id == mr.pk

    def test_material_request_dropdown_scoped_to_the_caisse_site(self, director_client, caisse, site, site_factory, material_request_factory):
        other_site = site_factory(name='Autre Chantier')
        mr_here = material_request_factory(site=site)
        material_request_factory(site=other_site)
        response = director_client.get(reverse('finance:caisse_transaction_create', kwargs={'pk': caisse.pk}))
        assert response.status_code == 200
        form = response.context['form']
        ids = set(form.fields['material_request'].queryset.values_list('pk', flat=True))
        assert ids == {mr_here.pk}

    def test_detail_page_shows_both_documents_and_the_linked_request(self, director_client, caisse, site, material_request_factory, user):
        mr = material_request_factory(site=site)
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('50.00'),
            date='2026-10-19', material_request=mr, recorded_by=user,
        )
        response = director_client.get(reverse('finance:caisse_transaction_detail', kwargs={'pk': tx.pk}))
        assert response.status_code == 200
        content = response.content.decode()
        assert str(mr) in content


@pytest.mark.django_db
class TestDGSignature:
    def test_director_can_sign_a_sortie_movement(self, director_client, caisse, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('75.00'),
            date='2026-10-01', recorded_by=user,
        )
        response = director_client.post(reverse('finance:caisse_transaction_dg_sign', kwargs={'pk': tx.pk}))
        assert response.status_code == 302
        tx.refresh_from_db()
        assert tx.is_dg_validated
        assert tx.dg_validated_by == user
        assert tx.dg_validated_at is not None

    def test_signing_is_not_blocked_by_the_movement_being_old(self, director_client, caisse, user):
        """"Signature rétroactive" — nothing in sign_by_dg() checks the
        transaction's own date, so a movement from months ago can still
        be signed today."""
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('75.00'),
            date='2025-01-01', recorded_by=user,
        )
        response = director_client.post(reverse('finance:caisse_transaction_dg_sign', kwargs={'pk': tx.pk}))
        assert response.status_code == 302
        tx.refresh_from_db()
        assert tx.is_dg_validated

    def test_cannot_sign_an_entree(self, director_client, caisse, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.ENTREE, amount=Decimal('75.00'),
            date='2026-10-19', recorded_by=user,
        )
        response = director_client.post(reverse('finance:caisse_transaction_dg_sign', kwargs={'pk': tx.pk}))
        assert response.status_code == 302
        tx.refresh_from_db()
        assert not tx.is_dg_validated

    def test_an_engineer_cannot_sign(self, engineer_client, caisse, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('75.00'),
            date='2026-10-19', recorded_by=user,
        )
        response = engineer_client.post(reverse('finance:caisse_transaction_dg_sign', kwargs={'pk': tx.pk}))
        assert response.status_code == 302
        tx.refresh_from_db()
        assert not tx.is_dg_validated

    def test_sign_button_shown_to_a_director(self, director_client, caisse, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('75.00'),
            date='2026-10-19', recorded_by=user,
        )
        response = director_client.get(reverse('finance:caisse_transaction_detail', kwargs={'pk': tx.pk}))
        assert response.context['can_sign_dg'] is True

    def test_sign_button_hidden_from_an_engineer(self, engineer_client, caisse, user):
        tx = CaisseTransaction.objects.create(
            caisse=caisse, transaction_type=CaisseTransactionType.SORTIE, amount=Decimal('75.00'),
            date='2026-10-19', recorded_by=user,
        )
        response = engineer_client.get(reverse('finance:caisse_transaction_detail', kwargs={'pk': tx.pk}))
        assert response.context['can_sign_dg'] is False
