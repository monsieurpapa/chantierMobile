"""Seed a default set of expense categories.

Without this, a fresh cabinet has zero ExpenseCategory rows and the
"Catégorie" dropdown on the expense form renders with no options at all
(ExpenseForm.category has no custom __init__ queryset — it's a plain
ModelChoiceField over ExpenseCategory.objects.all(), so an empty table
means an empty <select>). Categories aren't cabinet-scoped (see
ExpenseCategory model — no cabinet FK), so this is a one-time, global seed
rather than something each cabinet needs to set up itself.

Mirrors the category list in accounts.management.commands.seed_sample_data
(create_expense_categories), which exists only for demo-data seeding and
isn't something a production deployment would run.
"""
from django.db import migrations

CATEGORY_NAMES = [
    'Matériaux de Construction',
    "Main d'œuvre",
    'Transport et Logistique',
    'Équipements et Outils',
    'Permis et Autorisations',
    'Assurance',
    'Frais Administratifs',
]


def seed_categories(apps, schema_editor):
    ExpenseCategory = apps.get_model('finance', 'ExpenseCategory')
    for name in CATEGORY_NAMES:
        ExpenseCategory.objects.get_or_create(name=name)


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0009_expense_recipient"),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]
