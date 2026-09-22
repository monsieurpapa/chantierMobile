"""
Tests for the "Caisse fixes" package built from finance-team demo feedback:

1. Bétonnière-style caisses (manual_site_entry) accept a free-text
   chantier/client instead of forcing a link to an internal Site.
2. A caisse operation can be deleted (soft-delete; balance updates live).
3. A prêt entre caisses cannot exceed the lender caisse's available balance.
4. Caisse operations are filterable by type (Entrée/Sortie).
5. Caisse operations have a Bénéficiaire field.
6. Caisse operations have a filterable Catégorie field.
"""
import pytest
from decimal import Decimal
from datetime import date
from django.urls import reverse
from django.core.exceptions import ValidationError

from finance.models import Caisse, CaisseTransaction, CaisseTransactionCategory, CaisseLoan
from chantiermobile.constants import CaisseTransactionType, CaisseType


@pytest.fixture
def caisse_factory(db, cabinet):
    def create_caisse(**kwargs):
        defaults = {'cabinet': cabinet, 'name': 'Caisse Test', 'caisse_type': CaisseType.PRINCIPALE}
        defaults.update(kwargs)
        return Caisse.objects.create(**defaults)
    return create_caisse


@pytest.fixture
def category_factory(db):
    def create_category(**kwargs):
        defaults = {'name': 'Catégorie Test'}
        defaults.update(kwargs)
        return CaisseTransactionCategory.objects.get_or_create(**defaults)[0]
    return create_category


@pytest.mark.django_db
class TestBetonniereManualSiteEntry:
    def test_manual_site_entry_flag_off_by_default(self, caisse_factory):
        c = caisse_factory()
        assert c.manual_site_entry is False

    def test_transaction_form_shows_free_text_field_for_manual_caisses(self, director_client, caisse_factory):
        betonniere = caisse_factory(name='Bétonnière', manual_site_entry=True)
        response = director_client.get(reverse('finance:caisse_transaction_create', kwargs={'pk': betonniere.pk}))
        assert 'site' not in response.context['form'].fields
        assert 'external_site_label' in response.context['form'].fields

    def test_transaction_form_shows_site_dropdown_for_regular_caisses(self, director_client, caisse_factory):
        c = caisse_factory(name='Caisse principale')
        response = director_client.get(reverse('finance:caisse_transaction_create', kwargs={'pk': c.pk}))
        assert 'site' in response.context['form'].fields
        assert 'external_site_label' not in response.context['form'].fields

    def test_free_text_chantier_saves_without_an_internal_site(self, director_client, caisse_factory):
        betonniere = caisse_factory(name='Bétonnière', manual_site_entry=True)
        response = director_client.post(reverse('finance:caisse_transaction_create', kwargs={'pk': betonniere.pk}), {
            'transaction_type': CaisseTransactionType.ENTREE, 'amount': '150.00', 'date': date.today().isoformat(),
            'description': 'Location bétonnière', 'external_site_label': 'Client Kamundala (externe)',
            'recipient': '', 'category': '',
        })
        assert response.status_code == 302
        tx = betonniere.transactions.get()
        assert tx.site is None
        assert tx.external_site_label == 'Client Kamundala (externe)'

    def test_caisse_update_view_toggles_manual_site_entry(self, director_client, caisse_factory):
        c = caisse_factory(name='Bétonnière')
        response = director_client.post(reverse('finance:caisse_update', kwargs={'pk': c.pk}), {
            'name': 'Bétonnière', 'caisse_type': CaisseType.SECONDAIRE, 'site': '',
            'is_administrative': False, 'manual_site_entry': 'on',
        })
        assert response.status_code == 302
        c.refresh_from_db()
        assert c.manual_site_entry is True


@pytest.mark.django_db
class TestCaisseTransactionDelete:
    def test_delete_soft_deletes_and_updates_balance(self, director_client, caisse_factory, user):
        c = caisse_factory()
        c.record(CaisseTransactionType.ENTREE, Decimal('500.00'), user)
        tx = c.record(CaisseTransactionType.SORTIE, Decimal('200.00'), user)
        assert c.balance == Decimal('300.00')

        response = director_client.post(reverse('finance:caisse_transaction_delete', kwargs={'pk': tx.pk}))
        assert response.status_code == 302
        tx.refresh_from_db()
        assert tx.is_deleted is True
        assert c.balance == Decimal('500.00')
        assert not c.transactions.filter(pk=tx.pk).exists()

    def test_delete_requires_caisse_manage_role(self, engineer_client, caisse_factory, user):
        c = caisse_factory()
        tx = c.record(CaisseTransactionType.ENTREE, Decimal('100.00'), user)
        response = engineer_client.post(reverse('finance:caisse_transaction_delete', kwargs={'pk': tx.pk}))
        tx.refresh_from_db()
        assert tx.is_deleted is False
        assert c.balance == Decimal('100.00')
        assert response.status_code in (302, 403)


@pytest.mark.django_db
class TestCaisseLoanBalanceCheck:
    def test_loan_exceeding_lender_balance_is_rejected(self, caisse_factory, user):
        equip = caisse_factory(name='Location engins')
        site_caisse = caisse_factory(name='Chantier A')
        equip.record(CaisseTransactionType.ENTREE, Decimal('100.00'), user)

        loan = CaisseLoan(lender_caisse=equip, borrower_caisse=site_caisse, amount=Decimal('300.00'), date=date.today())
        with pytest.raises(ValidationError):
            loan.full_clean()
        assert equip.balance == Decimal('100.00')
        assert site_caisse.balance == Decimal('0.00')

    def test_loan_within_lender_balance_is_allowed(self, caisse_factory, user):
        equip = caisse_factory(name='Location engins')
        site_caisse = caisse_factory(name='Chantier A')
        equip.record(CaisseTransactionType.ENTREE, Decimal('1000.00'), user)

        loan = CaisseLoan(lender_caisse=equip, borrower_caisse=site_caisse, amount=Decimal('300.00'), date=date.today())
        loan.full_clean()  # should not raise

    def test_loan_create_view_rejects_insufficient_balance(self, director_client, caisse_factory, user):
        equip = caisse_factory(name='Location engins')
        site_caisse = caisse_factory(name='Chantier A')
        equip.record(CaisseTransactionType.ENTREE, Decimal('50.00'), user)

        response = director_client.post(reverse('finance:caisse_loan_create'), {
            'lender_caisse': equip.pk, 'borrower_caisse': site_caisse.pk,
            'amount': '300.00', 'date': date.today().isoformat(), 'notes': '',
        })
        assert response.status_code == 200  # form re-rendered, not redirected
        assert not CaisseLoan.objects.filter(lender_caisse=equip, borrower_caisse=site_caisse).exists()
        assert equip.balance == Decimal('50.00')


@pytest.mark.django_db
class TestCaisseOperationTypeAndCategoryFilters:
    def test_type_filter_narrows_ledger_rows(self, director_client, caisse_factory, user):
        c = caisse_factory()
        c.record(CaisseTransactionType.ENTREE, Decimal('500.00'), user)
        c.record(CaisseTransactionType.SORTIE, Decimal('200.00'), user)

        response = director_client.get(reverse('finance:caisse_detail', kwargs={'pk': c.pk}), {'type': 'SORTIE'})
        rows = response.context['ledger_rows']
        assert len(rows) == 1
        assert rows[0]['tx'].transaction_type == CaisseTransactionType.SORTIE
        # The running balance next to the filtered row still reflects the
        # true caisse balance (300), not a balance computed from sorties alone.
        assert rows[0]['running_balance'] == Decimal('300.00')

    def test_category_filter_narrows_ledger_rows(self, director_client, caisse_factory, category_factory, user):
        c = caisse_factory()
        salaire = category_factory(name='Salaire Ingénieurs')
        c.record(CaisseTransactionType.SORTIE, Decimal('100.00'), user, category=salaire)
        c.record(CaisseTransactionType.SORTIE, Decimal('50.00'), user)

        response = director_client.get(reverse('finance:caisse_detail', kwargs={'pk': c.pk}), {'category': salaire.pk})
        rows = response.context['ledger_rows']
        assert len(rows) == 1
        assert rows[0]['tx'].category_id == salaire.pk

    def test_no_filter_shows_all_rows(self, director_client, caisse_factory, user):
        c = caisse_factory()
        c.record(CaisseTransactionType.ENTREE, Decimal('500.00'), user)
        c.record(CaisseTransactionType.SORTIE, Decimal('200.00'), user)
        response = director_client.get(reverse('finance:caisse_detail', kwargs={'pk': c.pk}))
        assert len(response.context['ledger_rows']) == 2


@pytest.mark.django_db
class TestCaisseOperationRecipientAndCategory:
    def test_form_accepts_recipient_and_category(self, director_client, caisse_factory, category_factory):
        c = caisse_factory()
        cat = category_factory(name='Frais divers')
        response = director_client.post(reverse('finance:caisse_transaction_create', kwargs={'pk': c.pk}), {
            'transaction_type': CaisseTransactionType.SORTIE, 'amount': '75.00', 'date': date.today().isoformat(),
            'description': 'Achat fournitures', 'site': '', 'phase': '',
            'recipient': 'Quincaillerie Modeste', 'category': cat.pk,
        })
        assert response.status_code == 302
        tx = c.transactions.get()
        assert tx.recipient == 'Quincaillerie Modeste'
        assert tx.category_id == cat.pk

    def test_recipient_and_category_are_optional(self, director_client, caisse_factory):
        c = caisse_factory()
        response = director_client.post(reverse('finance:caisse_transaction_create', kwargs={'pk': c.pk}), {
            'transaction_type': CaisseTransactionType.ENTREE, 'amount': '20.00', 'date': date.today().isoformat(),
            'description': 'Recette', 'site': '', 'phase': '', 'recipient': '', 'category': '',
        })
        assert response.status_code == 302
        tx = c.transactions.get()
        assert tx.recipient == ''
        assert tx.category is None
