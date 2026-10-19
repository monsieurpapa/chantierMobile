"""One-off demo/exploration command: creates the "Appartements CCLK"
chantier from the client's own devis quantitatif et estimatif (shared
2026-10-19), wiring it through several existing features end to end with
real project data instead of synthetic test fixtures:

  1. Makes sure there is a Cabinet + a Director account to own the data
     (reusing `bootstrap_admin_and_roles`'s cabinet/demo-role-account
     convention) and a real account for the person running this.
  2. Creates the Site itself ("Appartements CCLK").
  3. Instantiates every PhaseTemplate (the "liste des étapes possibles
     irrespective of a project/chantier" catalog — see
     projects.models.PhaseTemplate and its 0012 seed migration) onto
     that Site, so it starts with the full Gros-Œuvre/Second-Œuvre étape
     structure the devis itself uses.
  4. Seeds this cabinet's Bibliothèque de Prix (pricing.PriceLibraryItem)
     from the devis: one MATERIAL-type row per cabinet-wide Material
     (see materials' 0013 seed migration), plus the Gros-Œuvre devis's
     own composite ouvrage lines (béton/maçonnerie "dosage" items) as
     WORK_ITEM rows, and its lump-sum lines (implantation, ajustage,
     charpente) as SERVICE rows.
  5. Builds one DQE ("Gros œuvre — Appartements CCLK") from those
     Bibliothèque de Prix rows, with each line's quantity and phase
     taken directly from the devis — exercising DQE/DQELine.phase and
     DQELine.exploded_requirements() against real figures.

Every step is get_or_create'd by its natural key, so re-running this
command is safe and never duplicates data.

Usage:
    python manage.py seed_cclk_site
"""
import secrets
import string
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Cabinet, UserCabinetRole
from chantiermobile.constants import (
    ApprovalStatus, UserRoles, ContractMode, StructureType, PriceItemType, WorkCategory, DQEStatus,
)
from materials.models import Material
from pricing.models import PriceLibraryItem, DQE, DQELine
from projects.models import Site, PhaseTemplate

CABINET_NAME = 'Cabinet Principal'
SUPERUSER_EMAIL = 'dieudonneishara@gmail.com'
SITE_NAME = 'Appartements CCLK'

# (phase, sub_phase, designation, unit, quantity, unit_price, work_category)
# — the devis's own composite ouvrage ("dosage") lines, Gros-Œuvre only.
WORK_ITEMS = [
    ('Travaux de fondation', 'Béton de propreté', 'Béton de propreté (dosage 200/m3)', 'm3', '3.75', '87.00', WorkCategory.BETON),
    ('Travaux de fondation', 'Semelle en BA', 'Semelle en BA (dosage 350/m3)', 'm3', '2.254', '268.65', WorkCategory.BETON),
    ('Travaux de fondation', 'Socle en BA', 'Socle en BA (dosage 350/m3)', 'm3', '1.840', '193.50', WorkCategory.BETON),
    ('Travaux de fondation', 'Maçonnerie de fondation en moellons', 'Maçonnerie de fondation en moellons', 'm3', '43.75', '47.60', WorkCategory.MACONNERIE),
    ('Travaux de fondation', 'Longrine en BA', 'Longrine en BA (dosage 350/m3)', 'm3', '3.75', '342.33', WorkCategory.BETON),
    ('Travaux de fondation', 'Béton de sous-pavement', 'Béton de sous-pavement (dosage 250/m3)', 'm3', '7.60', '123.61', WorkCategory.BETON),
    ('Rez-de-chaussée', 'Elévation', "Murs d'élévation en blocs de 15", 'm3', '44.10', '69.49', WorkCategory.MACONNERIE),
    ('Rez-de-chaussée', 'Colonnes en BA', 'Colonnes en BA (dosage 350/m3)', 'm3', '3.381', '564.90', WorkCategory.BETON),
    ('Rez-de-chaussée', 'Bande sismique', 'Bande sismique (dosage 350/m3)', 'm3', '1.575', '334.39', WorkCategory.BETON),
    ('Rez-de-chaussée', 'Poutres en BA', 'Poutres en BA (dosage 350/m3)', 'm3', '3.99', '708.67', WorkCategory.BETON),
    ('Rez-de-chaussée', 'Dalle et escalier', 'Dalle et escalier (dosage 350/m3)', 'm3', '26.85', '302.87', WorkCategory.BETON),
    ('Etage 1', 'Elévation', "Murs d'élévation en blocs de 15", 'm3', '46.20', '65.33', WorkCategory.MACONNERIE),
    ('Etage 1', 'Colonnes en BA', 'Colonnes en BA (dosage 350/m3)', 'm3', '3.381', '409.91', WorkCategory.BETON),
    ('Etage 1', 'Bande sismique', 'Bande sismique (dosage 350/m3)', 'm3', '1.65', '226.45', WorkCategory.BETON),
    ('Etage 1', 'Poutres en BA', 'Poutres en BA (dosage 350/m3)', 'm3', '4.14', '466.40', WorkCategory.BETON),
    ('Etage 1', 'Dalle et escalier', 'Dalle et escalier (dosage 350/m3)', 'm3', '26.85', '240.76', WorkCategory.BETON),
    ('Etage 2', 'Elévation', "Murs d'élévation en blocs de 15", 'm3', '42.00', '65.49', WorkCategory.MACONNERIE),
    ('Etage 2', 'Colonnes en BA', 'Colonnes en BA (dosage 350/m3)', 'm3', '2.898', '375.05', WorkCategory.BETON),
    ('Etage 2', 'Bande sismique', 'Bande sismique (dosage 350/m3)', 'm3', '1.50', '226.45', WorkCategory.BETON),
    ('Etage 2', 'Poutres en BA', 'Poutres en BA (dosage 350/m3)', 'm3', '4.35', '334.60', WorkCategory.BETON),
    ('Etage 2', 'Dalle et pergola', 'Dalle et pergola (dosage 350/m3)', 'm3', '6.62', '277.68', WorkCategory.BETON),
    ('Couverture', 'Elévation', "Murs d'élévation en blocs de 15", 'm3', '12.60', '72.55', WorkCategory.MACONNERIE),
    ('Couverture', 'Colonnes en BA', 'Colonnes en BA (dosage 350/m3)', 'm3', '0.918', '224.96', WorkCategory.BETON),
    ('Couverture', 'Chaînage supérieur en BA', 'Chaînage supérieur en BA (dosage 350/m3)', 'm3', '2.24', '232.79', WorkCategory.BETON),
]

# (phase, sub_phase, designation, total_price) — lump-sum ("forfait")
# lines from the same Gros-Œuvre devis.
SERVICE_ITEMS = [
    ('Travaux de fondation', 'Fondation', 'Implantation et travaux préliminaires', '1260.00'),
    ('Rez-de-chaussée', 'Ajustage portes et fenêtres métalliques', 'Ajustage portes et fenêtres métalliques — RDC', '1166.50'),
    ('Etage 1', 'Ajustage portes et fenêtres métalliques', 'Ajustage portes et fenêtres métalliques — Étage 1', '1166.50'),
    ('Etage 2', 'Ajustage portes et fenêtres métalliques', 'Ajustage portes et fenêtres métalliques — Étage 2', '1174.00'),
    ('Couverture', 'Charpente et tôlage', 'Charpente métallique et tôlage', '2935.00'),
]


class Command(BaseCommand):
    help = (
        'Creates the "Appartements CCLK" chantier from the client\'s own devis, seeding its '
        'étapes (from the PhaseTemplate catalog), Bibliothèque de Prix, and a Gros-Œuvre DQE.'
    )

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. Cabinet + accounts. Reuses the existing bootstrap command so
        # this doesn't duplicate its demo-account logic; it also promotes
        # SUPERUSER_EMAIL to superuser if that account already exists.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.filter(email__iexact=SUPERUSER_EMAIL).first()
        if user is None:
            alphabet = string.ascii_letters + string.digits
            temp_password = 'Cm-' + ''.join(secrets.choice(alphabet) for _ in range(10)) + '!'
            user = User.objects.create_user(
                username='dieudonneishara', email=SUPERUSER_EMAIL,
                password=temp_password,
                first_name='Dieudonné', is_superuser=True, is_staff=True,
            )
            user.must_change_password = True
            user.save(update_fields=['must_change_password'])
            self.stdout.write(self.style.SUCCESS(f'Created account for {SUPERUSER_EMAIL}.'))

        call_command('bootstrap_admin_and_roles', superuser_email=SUPERUSER_EMAIL, cabinet=CABINET_NAME)
        cabinet = Cabinet.objects.get(name=CABINET_NAME)
        UserCabinetRole.objects.update_or_create(
            user=user, cabinet=cabinet,
            defaults={'role': UserRoles.DIRECTOR, 'status': ApprovalStatus.APPROVED},
        )

        chief_engineer = User.objects.filter(username='chief_engineer_demo').first()

        # 2. The Site.
        site, site_created = Site.objects.get_or_create(
            cabinet=cabinet, name=SITE_NAME,
            defaults={
                'location': 'CCLK, Q. Kyeshero, Commune de Goma, Goma-NK',
                'contract_mode': ContractMode.CLE_EN_MAIN,
                'structure_type': StructureType.POTEAUX_POUTRES,
                'floor_count': 2,
                'basement_count': 0,
                'footprint_area_m2': Decimal('152.00'),
                'lead_engineer': chief_engineer,
            },
        )
        if site_created:
            site.sync_levels()
            self.stdout.write(self.style.SUCCESS(f'Created site "{SITE_NAME}".'))
        else:
            self.stdout.write(f'Site "{SITE_NAME}" already exists — reusing it.')

        # 3. Instantiate the full étape catalog onto this site.
        phase_by_key = {}
        for template in PhaseTemplate.objects.filter(parent_template__isnull=True).order_by('category', 'order'):
            top_phase = template.instantiate_for_site(site)
            phase_by_key[(template.name, None)] = top_phase
            for sub in template.sub_templates.all():
                phase_by_key[(template.name, sub.name)] = site.phases.get(name=sub.name, parent_phase=top_phase)
        self.stdout.write(self.style.SUCCESS(f'Instantiated {len(phase_by_key)} étapes/sous-étapes for "{SITE_NAME}".'))

        # 4a. Bibliothèque de Prix — one MATERIAL row per cabinet-wide Material.
        code_n = 0
        material_items = {}
        for material in Material.objects.order_by('id'):
            code_n += 1
            item, _created = PriceLibraryItem.objects.get_or_create(
                cabinet=cabinet, code=f'CCLK-MAT-{code_n:03d}',
                defaults={
                    'designation': material.name,
                    'item_type': PriceItemType.MATERIAL,
                    'material': material,
                    'unit': material.unit,
                    'unit_price': material.estimated_cost_per_unit or Decimal('0'),
                },
            )
            material_items[material.name] = item

        # 4b. Bibliothèque de Prix — Gros-Œuvre composite ouvrage lines.
        work_item_rows = []  # (phase_key, sub_key, item, quantity)
        code_n = 0
        for phase_name, sub_name, designation, unit, qty, price, category in WORK_ITEMS:
            code_n += 1
            item, _created = PriceLibraryItem.objects.get_or_create(
                cabinet=cabinet, code=f'CCLK-WRK-{code_n:03d}',
                defaults={
                    'designation': designation, 'item_type': PriceItemType.WORK_ITEM,
                    'work_category': category, 'unit': unit, 'unit_price': Decimal(price),
                },
            )
            work_item_rows.append((phase_name, sub_name, item, Decimal(qty)))

        # 4c. Bibliothèque de Prix — lump-sum ("forfait") service lines.
        code_n = 0
        service_rows = []  # (phase_key, sub_key, item)
        for phase_name, sub_name, designation, price in SERVICE_ITEMS:
            code_n += 1
            item, _created = PriceLibraryItem.objects.get_or_create(
                cabinet=cabinet, code=f'CCLK-SRV-{code_n:03d}',
                defaults={
                    'designation': designation, 'item_type': PriceItemType.SERVICE,
                    'unit': 'forfait', 'unit_price': Decimal(price),
                },
            )
            service_rows.append((phase_name, sub_name, item))
        self.stdout.write(self.style.SUCCESS(
            f'Seeded {len(material_items)} material + {len(work_item_rows)} ouvrage + '
            f'{len(service_rows)} forfait items in the Bibliothèque de Prix.'
        ))

        # 5. One DQE from those lines, each tied to its real site phase.
        dqe, dqe_created = DQE.objects.get_or_create(
            cabinet=cabinet, reference='DQE-CCLK-GO-001',
            defaults={
                'site': site, 'title': 'Gros œuvre — Appartements CCLK',
                'status': DQEStatus.DRAFT,
                'notes': "Importé du devis quantitatif et estimatif du client (Gros-Œuvre).",
            },
        )
        if dqe_created:
            order = 0
            for phase_name, sub_name, item, qty in work_item_rows:
                phase = phase_by_key.get((phase_name, sub_name))
                DQELine.objects.create(dqe=dqe, price_item=item, phase=phase, quantity=qty, unit_price=item.unit_price, order=order)
                order += 1
            for phase_name, sub_name, item in service_rows:
                phase = phase_by_key.get((phase_name, sub_name))
                DQELine.objects.create(dqe=dqe, price_item=item, phase=phase, quantity=Decimal('1'), unit_price=item.unit_price, order=order)
                order += 1
            self.stdout.write(self.style.SUCCESS(f'Created DQE "{dqe.reference}" with {dqe.total_lines} lines (total {dqe.total_amount} $).'))
        else:
            self.stdout.write(f'DQE "{dqe.reference}" already exists ({dqe.total_lines} lines, total {dqe.total_amount} $).')

        self.stdout.write(self.style.SUCCESS('Done.'))
