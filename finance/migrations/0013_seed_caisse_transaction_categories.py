"""Seed a starter set of caisse transaction categories.

Without this, the new "Catégorie" dropdown on the caisse operation form
(CaisseTransactionForm.category) renders empty on a fresh install. Unlike
ExpenseCategory (Dépenses-only, matériel/main d'œuvre spend types), these
categories cover both entrées and sorties across all caisses, so the
starter list is generic. Managed from Django admin afterwards — finance
can add more (e.g. per-cabinet specifics) without a code change.
"""
from django.db import migrations

CATEGORY_NAMES = [
    'Recette client',
    'Location matériel',
    'Remboursement de prêt',
    'Retrait / Virement interne',
    'Achat matériaux',
    "Main d'œuvre",
    'Frais divers',
]


def seed_categories(apps, schema_editor):
    CaisseTransactionCategory = apps.get_model('finance', 'CaisseTransactionCategory')
    for name in CATEGORY_NAMES:
        CaisseTransactionCategory.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0012_caisse_manual_site_entry_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]
