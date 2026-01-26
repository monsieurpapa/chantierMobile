# Management Commands Documentation

This document describes the Django management commands available for the ChantiérMobile platform to manage sample data and database operations.

## Overview

The management commands are designed to help developers and testers quickly populate the database with realistic sample data in French, following the actual platform models and business logic.

## Available Commands

### 1. `seed_sample_data` - Comprehensive Sample Data Generation

Populates the entire database with complete demo data including users, companies, sites, personnel, materials, budgets, and financial data.

#### Usage

```bash
# Generate sample data (will skip existing data)
python manage.py seed_sample_data

# Clear existing data first, then generate fresh sample data
python manage.py seed_sample_data --clear
```

#### What It Creates

**Users and Access Control:**
- 5 demo users with different roles (Director, Chief Engineer, Engineer, Accountant, Cashier)
- Assigned to construction companies (Cabinets) with role-based permissions
- Default password: `password123`

**Demo Users:**
- `directeur_001` - Cabinet Director (Jean Diallo)
- `ingenieur_chef_001` - Chief of Engineers (Marie Sow)
- `ingenieur_001` - Engineer (Ahmed Ba)
- `comptable_001` - Accountant (Fatou Ndiaye)
- `caissier_001` - Cashier (Moussa Gueye)

**Construction Companies (Cabinets):**
- BTP Solutions Sénégal
- Constructions Modernes SARL

**Job Skills (8 types):**
- Maçon (Mason)
- Ferrailleur (Reinforcement worker)
- Électricien (Electrician)
- Plombier (Plumber)
- Peintre (Painter)
- Menuisier (Carpenter)
- Conducteur d'équipe (Team leader)
- Chef de chantier (Site foreman)

**Personnel:**
- 6 workers with assigned skills and daily rates (15,000 - 20,000 FCFA)
- Realistic Senegalese names

**Construction Sites:**
- Residential building in Plateau (ACTIVE)
- Commercial center in Point E (PLANNING)
- School renovation in Médina (ACTIVE)

**Project Phases per Site:**
- Multiple phases with realistic timelines
- Start/end dates covering 6+ months

**Progress Reports:**
- Sample progress reports (45% complete) with status descriptions

**Personnel Assignments:**
- Workers assigned to sites with specific roles
- 60-120 day assignments

**Materials (Comprehensive):**
- 8 key construction materials with realistic costs
- Includes cement, sand, gravel, steel, bricks, tiles, paint, windows

**Material Requests:**
- 2 material requests (1 pending, 1 approved)
- Items linked to specific materials with quantities

**Financial Data:**
- Budgets: 50M - 200M FCFA per site
- Expense Categories: 7 types (Labor, Materials, Transport, etc.)
- Sample Expenses: 5 entries totaling 9.8M FCFA
- Contracts and Invoices for revenue tracking

#### Data Summary

```
✅ 5 users created
✅ 2 cabinets created
✅ 8 skills created
✅ 6 personnel created
✅ 3 construction sites created
✅ 9 project phases created
✅ 3 progress reports created
✅ 8 personnel assignments created
✅ 8 materials created
✅ 2 material requests created
✅ 3 budgets created
✅ 7 expense categories created
✅ 5 expenses created
✅ Contracts and invoices created
```

---

### 2. `clear_sample_data` - Data Cleanup

Safely removes all sample/demo data from the database while preserving superuser accounts.

#### Usage

```bash
# Clear data with confirmation prompt
python manage.py clear_sample_data

# Clear data without confirmation prompt
python manage.py clear_sample_data --confirm
```

#### What It Deletes

- All Invoices
- All Contracts
- All Expenses and approvals
- All Budgets
- All Material Requests and items
- All Material definitions
- All Site Assignments
- All Personnel
- All Progress Reports
- All Project Phases
- All Construction Sites
- All Skills
- All User Cabinet Roles
- All Cabinets
- All regular (non-superuser) Users

**Note:** Superuser accounts are preserved for admin access.

#### Safety Features

- Requires user confirmation before deletion
- Provides `--confirm` flag to bypass confirmation (useful for scripts)
- Lists each model as it's cleared for transparency

---

### 3. `populate_materials` - Comprehensive Materials Database

Populates the materials catalog with 80+ realistic construction materials commonly used in Senegal with accurate pricing.

#### Usage

```bash
# Populate materials catalog
python manage.py populate_materials
```

#### Materials Included

The command creates materials organized by category:

**Ciments et Liants (Cements & Binders):**
- Ciment CEM II/A 42.5 - 8,500 FCFA/sac
- Ciment CEM I 52.5 - 9,200 FCFA/sac
- Chaux vive - 850 FCFA/kg
- Plâtre de construction - 500 FCFA/kg

**Granulats (Aggregates):**
- Sable Construction 0-4mm - 35,000 FCFA/m³
- Sable Fin 0-2mm - 38,000 FCFA/m³
- Gravier 4-6mm - 40,000 FCFA/m³
- Gravillon 6-10mm - 38,000 FCFA/m³
- Tout-venant - 25,000 FCFA/m³

**Aciers et Ferraillage (Steel & Reinforcement):**
- Acier HA500 (Various diameters: Ø8, Ø10, Ø12, Ø16) - 950 FCFA/kg
- Fil d'acier recuit - 1,200 FCFA/kg
- Treillis soudé - 4,500 FCFA/m²

**Éléments de Maçonnerie (Masonry):**
- Brique de Construction - 350 FCFA/unité
- Parpaing Creux - 2,500 FCFA/unité
- Parpaing Plein - 3,200 FCFA/unité
- Pierre de taille - 25,000 FCFA/m²
- Moellon - 45,000 FCFA/m³

**Couverture et Étanchéité (Roofing & Waterproofing):**
- Tuiles Mécaniques - 5,500 FCFA/m²
- Ardoise Naturelle - 8,500 FCFA/m²
- Membrane Bitumineuse - 6,500 FCFA/m²
- Feuille de Zinc - 12,000 FCFA/m²

**Menuiserie et Charpente (Carpentry & Framing):**
- Bois de Charpente - 450,000 FCFA/m³
- Fenêtres Aluminium - 85,000 FCFA/unité
- Portes Bois Massif - 125,000 FCFA/unité
- Escalier Préfabriqué - 850,000 FCFA/volée

**Revêtements (Finishes):**
- Carrelage Murs - 4,500 FCFA/m²
- Carrelage Sol - 6,500 FCFA/m²
- Mosaïque Céramique - 8,500 FCFA/m²
- Revêtement Vinyl - 3,500 FCFA/m²

**Peintures et Vernis (Paint & Varnish):**
- Peinture Intérieure - 12,000 FCFA/litre
- Peinture Extérieure - 15,000 FCFA/litre
- Vernis Transparent - 18,000 FCFA/litre

**Plomberie (Plumbing):**
- Tuyau PVC (20mm, 32mm, 50mm) - 1,200-2,500 FCFA/mètre
- Tuyau Cuivre - 4,500-6,500 FCFA/mètre
- Robinetterie Salle de Bain - 25,000 FCFA/unité
- WC Porcelaine - 45,000 FCFA/unité

**Électricité (Electrical):**
- Câble Électrique (2.5mm², 6mm², 10mm²) - 800-2,200 FCFA/mètre
- Disjoncteur 20A - 8,500 FCFA/unité
- Interrupteur Simple - 3,500 FCFA/unité
- Prise de Courant - 4,500 FCFA/unité

**Isolation et Cloisons (Insulation & Partitions):**
- Laine de Verre 100mm - 3,500 FCFA/m²
- Polystyrène Expansé 50mm - 4,500 FCFA/m²
- Plaque de Plâtre Hydro - 5,500 FCFA/m²

**Divers (Miscellaneous):**
- Mortier Ciment-Sable - 180,000 FCFA/m³
- Béton Prêt à l'Emploi C25 - 320,000 FCFA/m³
- Vis, clous, chevilles, etc.

#### Idempotent Operation

The command is idempotent—running it multiple times won't create duplicates. If a material already exists, it's skipped.

---

## Sample Data Flow & Relationships

```
Cabinet (Construction Company)
  ├── Users (with roles)
  ├── Sites (Projects)
  │   ├── ProjectPhases
  │   │   └── SiteProgress (reports)
  │   ├── SiteAssignments (personnel working on site)
  │   ├── MaterialRequests (items needed)
  │   │   └── MaterialRequestItems
  │   ├── Budget
  │   ├── Expenses
  │   └── Contract
  │       └── Invoices
  │
  └── Personnel
      ├── Skills (specializations)
      └── SiteAssignments (to sites)
```

---

## Quick Start Guide

### Setting Up Demo Environment

```bash
# 1. Clear any existing data (optional)
python manage.py clear_sample_data --confirm

# 2. Generate comprehensive sample data
python manage.py seed_sample_data

# 3. Optionally populate extended materials catalog
python manage.py populate_materials

# 4. Create superuser for admin access (if needed)
python manage.py createsuperuser
```

### Test Login Credentials

After running `seed_sample_data`:

| Username | Role | Password | Email |
|----------|------|----------|-------|
| directeur_001 | Director | password123 | directeur@construction.sn |
| ingenieur_chef_001 | Chief Engineer | password123 | chef_ingenieur@construction.sn |
| ingenieur_001 | Engineer | password123 | ingenieur1@construction.sn |
| comptable_001 | Accountant | password123 | comptable@construction.sn |
| caissier_001 | Cashier | password123 | caissier@construction.sn |

---

## Advanced Usage

### Custom Data Generation

To modify sample data, edit the respective command file:

- `seed_sample_data.py` - Edit data dictionaries in each `create_*` method
- `populate_materials.py` - Edit `materials_data` list for different materials

### Data Localization

All sample data uses French names and descriptions to match the Senegalese context:

- Personnel names: Senegalese names (Diallo, Sow, Ba, Ndiaye, Gueye)
- Locations: Dakar neighborhoods (Plateau, Point E, Médina)
- Skills: Construction trades in French
- Categories: Expense types relevant to construction in Senegal

### Performance Considerations

- `seed_sample_data` is optimized with `get_or_create()` to prevent duplicates
- `populate_materials` creates 80+ records efficiently
- All commands use bulk operations where possible

---

## Troubleshooting

### Command Not Found

```bash
# Ensure management commands are discovered
python manage.py --help | grep seed_sample_data
```

If the command isn't listed, check:
1. Command file is in `app/management/commands/`
2. Directory has `__init__.py` files
3. Run `python manage.py makemigrations` if needed

### Data Already Exists

```bash
# Use --clear flag to start fresh
python manage.py seed_sample_data --clear
```

### Foreign Key Errors

Ensure all apps are properly installed in `INSTALLED_APPS`:
- accounts
- projects
- personnel
- materials
- finance
- core

---

## Development Notes

### Currency

All prices are in **FCFA (West African CFA franc)**, the currency used in Senegal and other West African countries.

### Realistic Pricing

Material costs are based on:
- Local market rates in Senegal
- Construction industry standards
- Supplier pricing from 2024-2025

### Customization

To adapt sample data for other countries/contexts:
1. Modify personnel names
2. Update location names
3. Adjust material prices (exchange rates)
4. Change company names and details
5. Translate expense categories

---

## Support & Maintenance

For issues or enhancements:
1. Review command help: `python manage.py seed_sample_data --help`
2. Check Django logs for detailed error messages
3. Verify database migrations are applied: `python manage.py migrate`

