"""Seed Material catalog rows from a real devis quantitatif et estimatif
("Appartements CCLK") shared by the client while exploring the app with
real-shaped reference data.

Material has no cabinet FK (see Material's docstring: "a catalog entry
... shared across every cabinet") so, like
materials.migrations.0001_initial's own handful of starter rows, this is
exactly the kind of "other data not specific to a chantier" the catalog
is meant to hold — every cabinet sees these, independent of which (if
any) actually worked the CCLK devis.

Rows are get_or_create'd by name, so this is safe to re-run and never
touches any Material a cabinet has already created or edited by hand
(including the unrelated starter rows from 0001_initial, which use
different display names/units and are deliberately left untouched)."""
from django.db import migrations


# (name, unit, estimated_cost_per_unit ($)) — construction materials,
# from the devis's own line items (DEVIS DETAILLE sheet).
CONSTRUCTION_MATERIALS = [
    ('Ciment', 'sac', 12),
    ('Sable', 'm3', 25),
    ('Gravier', 'm3', 30),
    ('Moellons', 'm3', 17),
    ('Remblais', 'm3', 5),
    ('Ferrons ϕ6', 'unité', 3.5),
    ('Ferrons ϕ8', 'unité', 4.5),
    ('Ferrons ϕ10', 'unité', 6),
    ('Ferrons ϕ12', 'unité', 8),
    ('Ferrons ϕ14', 'unité', 10),
    ('Planches de coffrage', 'unité', 5),
    ('Multiplex de coffrage', 'unité', 17),
    ('Madrier', 'unité', 7),
    ('Stick de bois', 'unité', 5),
    ('Chevron', 'unité', 2),
    ('Clous ordinaire', 'kg', 2),
    ('Fil de recuit', 'kg', 2),
    ('Bloc creux (15cm)', 'unité', 0.6),
    ('Tube 16x16', 'unité', 3),
    ('Tube 20x40', 'unité', 6),
    ('Tube 40x40', 'unité', 10),
    ('Tube 60x40', 'unité', 13.5),
    ('Fer plat de 20', 'unité', 3),
    ('Cornières de 25', 'unité', 13),
    ('Roulettes de porte', 'paire', 15),
    ('Roulettes de fenêtre', 'paire', 2),
    ('Pomelles de 8', 'paire', 2),
    ('Pomelles de 12', 'paire', 3),
    ('Baguettes', 'boîte', 5),
    ('Disques à poncer', 'unité', 5),
    ('Disques à couper', 'unité', 3),
    ('Mastic', 'boîte', 26),
    ('Antirouille', 'boîte', 10),
    ('Tôles ondulées galvanisées BG28', 'unité', 16),
    ('Gouttières galvanisées + machinage', 'unité', 25),
    ('Vis de tôles', 'boîte', 9),
    ('Naissances de gouttières', 'unité', 4),
    ('Tamis', 'm', 3),
    ('Ficelle', 'unité', 2.5),
    ('Bâche', 'unité', 6),
    ('SIKAPLAN (fourniture et pose)', 'm2', 40),
]

# (name, unit, estimated_cost_per_unit ($)) — reusable site tooling and
# equipment (devis's "Installation chantier" line), not tied to any one
# chantier's structural work.
TOOLS_AND_EQUIPMENT = [
    ('Brouette 50L', 'unité', 45),
    ('Demi-fût (Kingumbi)', 'unité', 15),
    ('Niveau à bulle', 'unité', 5),
    ('Niveau à eau', 'unité', 25),
    ('Marteau menuiserie', 'unité', 5),
    ('Marteau maçonnerie 2kg', 'unité', 4),
    ('Bêche', 'unité', 4),
    ('Pioche', 'unité', 6),
    ('Barre de mine', 'unité', 10),
    ('Burin', 'unité', 3),
    ('Scie à bois', 'unité', 5),
    ('Equerre', 'unité', 4),
    ('Décamètre 50m', 'unité', 10),
    ('Monture pour scie à métaux', 'unité', 3),
    ('Lame de scie à métaux', 'boîte', 15),
    ('Chaux (implantation)', 'unité', 4),
]


def seed_materials(apps, schema_editor):
    Material = apps.get_model('materials', 'Material')
    for name, unit, price in CONSTRUCTION_MATERIALS + TOOLS_AND_EQUIPMENT:
        Material.objects.get_or_create(
            name=name, defaults={'unit': unit, 'estimated_cost_per_unit': price},
        )


def unseed_materials(apps, schema_editor):
    Material = apps.get_model('materials', 'Material')
    names = [name for name, _unit, _price in CONSTRUCTION_MATERIALS + TOOLS_AND_EQUIPMENT]
    Material.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0012_migrate_validated_requests_to_pending'),
    ]

    operations = [
        migrations.RunPython(seed_materials, unseed_materials),
    ]
