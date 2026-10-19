"""Seed global-default MaterialConsumptionRatio rows for the two
second-œuvre WorkCategory values that DO have a well-established,
generic BTP rule of thumb: PEINTURE and REVETEMENTS (see
0005_second_oeuvre_work_categories and WorkCategory's own docstring for
why PLOMBERIE/ELECTRICITE/MENUISERIE are deliberately left unseeded).

Ratios reflect standard practice for finishing work:

- Peinture (2 couches, murs/plafonds intérieurs) : ~0.2 L de peinture
  par m² — a commonly-cited rule of thumb for two coats of standard
  acrylic paint on a primed interior wall.
- Revêtements (carrelage posé à la colle) : ~3 kg de colle par m² (a
  standard notched-trowel bed thickness), ~0.3 kg de joint par m², et
  ~1.1 m² de carreaux par m² de surface (10% de chute/découpe — le
  même ordre de grandeur que la marge de perte habituellement retenue
  pour la pose de carrelage).

Same disclaimer as 0004_seed_material_consumption_ratios: deliberately
conservative, commonly-cited defaults meant as a starting point — a
cabinet can override any of them with its own cabinet-specific row.
"""
from django.db import migrations


MATERIALS = {
    'peinture': ('Peinture', 'L'),
    'colle_carrelage': ('Colle à carrelage', 'kg'),
    'joint_carrelage': ('Joint de carrelage', 'kg'),
    'carreaux': ('Carreaux', 'm2'),
}

# (work_category, material_key, ratio, ratio_unit)
RATIOS = [
    ('PEINTURE', 'peinture', '0.2000', 'L/m2'),
    ('REVETEMENTS', 'colle_carrelage', '3.0000', 'kg/m2'),
    ('REVETEMENTS', 'joint_carrelage', '0.3000', 'kg/m2'),
    ('REVETEMENTS', 'carreaux', '1.1000', 'm2/m2'),
]


def seed_ratios(apps, schema_editor):
    Material = apps.get_model('materials', 'Material')
    MaterialConsumptionRatio = apps.get_model('pricing', 'MaterialConsumptionRatio')

    material_ids = {}
    for key, (name, unit) in MATERIALS.items():
        obj, _created = Material.objects.get_or_create(name=name, defaults={'unit': unit})
        material_ids[key] = obj.id

    for work_category, material_key, ratio, ratio_unit in RATIOS:
        MaterialConsumptionRatio.objects.get_or_create(
            cabinet=None,
            work_category=work_category,
            material_id=material_ids[material_key],
            defaults={'ratio': ratio, 'ratio_unit': ratio_unit},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("pricing", "0005_second_oeuvre_work_categories"),
    ]

    operations = [
        migrations.RunPython(seed_ratios, migrations.RunPython.noop),
    ]
