"""
Management command to populate materials database with comprehensive construction materials.

Usage:
    python manage.py populate_materials
"""

from django.core.management.base import BaseCommand
from decimal import Decimal
from materials.models import Material


class Command(BaseCommand):
    help = 'Populates the database with a comprehensive list of construction materials in French'

    def handle(self, *args, **options):
        self.stdout.write('📦 Populating materials database...')
        
        materials_data = [
            # Ciments et Liants
            ('Ciment CEM II/A 42.5', 'sacs', 8500),
            ('Ciment CEM I 52.5', 'sacs', 9200),
            ('Chaux vive', 'kg', 850),
            ('Plâtre de construction', 'kg', 500),
            
            # Granulats
            ('Sable Construction 0-4mm', 'm³', 35000),
            ('Sable Fin 0-2mm', 'm³', 38000),
            ('Gravier 4-6mm', 'm³', 40000),
            ('Gravillon 6-10mm', 'm³', 38000),
            ('Tout-venant', 'm³', 25000),
            
            # Aciers et Ferraillage
            ('Acier HA500 - Ø8', 'kg', 950),
            ('Acier HA500 - Ø10', 'kg', 950),
            ('Acier HA500 - Ø12', 'kg', 950),
            ('Acier HA500 - Ø16', 'kg', 950),
            ('Fil d\'acier recuit', 'kg', 1200),
            ('Treillis soudé 6/6', 'm²', 4500),
            
            # Éléments de maçonnerie
            ('Brique de Construction 24x12x6cm', 'unité', 350),
            ('Parpaing Creux 20x20x40cm', 'unité', 2500),
            ('Parpaing Plein 20x20x40cm', 'unité', 3200),
            ('Pierre de taille', 'm²', 25000),
            ('Moellon', 'm³', 45000),
            
            # Couverture et Étanchéité
            ('Tuiles Mécaniques', 'm²', 5500),
            ('Ardoise Naturelle', 'm²', 8500),
            ('Membrane Bitumineuse', 'm²', 6500),
            ('Étanchéifiant Bitumeux', 'litre', 8000),
            ('Feuille de Zinc', 'm²', 12000),
            
            # Menuiserie et Charpente
            ('Bois de Charpente Classe II', 'm³', 450000),
            ('Contre-plaqué Extérieur', 'm²', 8500),
            ('Panneaux OSB 2.5cm', 'm²', 4500),
            ('Fenêtres Aluminium Standard', 'unité', 85000),
            ('Portes Bois Massif', 'unité', 125000),
            ('Escalier Préfabriqué', 'volée', 850000),
            
            # Revêtements
            ('Carrelage Murs 20x25cm', 'm²', 4500),
            ('Carrelage Sol 40x40cm', 'm²', 6500),
            ('Mosaïque Céramique', 'm²', 8500),
            ('Revêtement Vinyl', 'm²', 3500),
            ('Moquette', 'm²', 5500),
            
            # Peintures et Vernis
            ('Peinture Intérieure', 'litre', 12000),
            ('Peinture Extérieure', 'litre', 15000),
            ('Vernis Transparent', 'litre', 18000),
            ('Peinture Spéciale Humidité', 'litre', 16000),
            ('Apprêt Primaire', 'litre', 10000),
            
            # Plomberie
            ('Tuyau PVC 20mm', 'mètre', 1200),
            ('Tuyau PVC 32mm', 'mètre', 1800),
            ('Tuyau PVC 50mm', 'mètre', 2500),
            ('Tuyau Cuivre 12mm', 'mètre', 4500),
            ('Tuyau Cuivre 20mm', 'mètre', 6500),
            ('Raccord PVC 20mm', 'unité', 500),
            ('Robinetterie Salle de Bain', 'unité', 25000),
            ('WC Porcelaine', 'unité', 45000),
            ('Lavabo Céramique', 'unité', 35000),
            
            # Électricité
            ('Câble Électrique 2.5mm²', 'mètre', 800),
            ('Câble Électrique 6mm²', 'mètre', 1500),
            ('Câble Électrique 10mm²', 'mètre', 2200),
            ('Conduit PVC 20mm', 'mètre', 600),
            ('Boîtier de Dérivation', 'unité', 1500),
            ('Disjoncteur 20A', 'unité', 8500),
            ('Interrupteur Simple', 'unité', 3500),
            ('Prise de Courant', 'unité', 4500),
            
            # Isolation et Cloisons
            ('Laine de Verre 100mm', 'm²', 3500),
            ('Polystyrène Expansé 50mm', 'm²', 4500),
            ('Plaque de Plâtre Hydro 13mm', 'm²', 5500),
            ('Cloison Sèche Complète', 'm²', 25000),
            
            # Divers
            ('Mortier Ciment-Sable', 'm³', 180000),
            ('Béton Prêt à l\'Emploi C25', 'm³', 320000),
            ('Béton Désactivé', 'm²', 8500),
            ('Escalis en Béton', 'volée', 250000),
            ('Chevilles de Fixation', 'paquet', 2500),
            ('Clous Acier', 'kg', 1500),
            ('Vis de Construction', 'kg', 2000),
        ]
        
        created_count = 0
        for name, unit, cost in materials_data:
            material, created = Material.objects.get_or_create(
                name=name,
                defaults={
                    'unit': unit,
                    'estimated_cost_per_unit': Decimal(cost)
                }
            )
            if created:
                created_count += 1
                self.stdout.write(f'✅ {name}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'🎉 Materials database populated! Created {created_count} new materials.'
            )
        )
