"""Seed the two caisse categories a Liste de paie décaissement is booked
under (see finance.models.PayrollList.disburse and
PAYROLL_OUVRIER_CATEGORY_NAME / PAYROLL_INGENIEUR_CATEGORY_NAME).

Without this, a fresh install's décaissement would create uncategorized
transactions until the category happened to be created some other way —
seeding them up front also means they show up immediately in the
"Catégorie" filter dropdown.
"""
from django.db import migrations

CATEGORY_NAMES = [
    "Main d'œuvre Ouvriers",
    'Salaire Ingénieurs',
]


def seed_categories(apps, schema_editor):
    CaisseTransactionCategory = apps.get_model('finance', 'CaisseTransactionCategory')
    for name in CATEGORY_NAMES:
        CaisseTransactionCategory.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0014_payrolllistitem_assignment"),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]
