# Sample Data Examples

This document shows examples of the actual data created by the management commands.

---

## Users Created

```
Username: directeur_001
Email: directeur@construction.sn
Name: Jean Diallo
Phone: +221 77 123 4567
Role: Cabinet Director
Cabinet: BTP Solutions Sénégal
Status: APPROVED

Username: ingenieur_chef_001
Email: chef_ingenieur@construction.sn
Name: Marie Sow
Phone: +221 77 234 5678
Role: Chief of Engineers
Cabinet: BTP Solutions Sénégal
Status: APPROVED

Username: ingenieur_001
Email: ingenieur1@construction.sn
Name: Ahmed Ba
Phone: +221 77 345 6789
Role: Engineer
Cabinet: BTP Solutions Sénégal
Status: APPROVED

Username: comptable_001
Email: comptable@construction.sn
Name: Fatou Ndiaye
Phone: +221 77 456 7890
Role: Accountant
Cabinet: BTP Solutions Sénégal
Status: APPROVED

Username: caissier_001
Email: caissier@construction.sn
Name: Moussa Gueye
Phone: +221 77 567 8901
Role: Cashier
Cabinet: BTP Solutions Sénégal
Status: APPROVED
```

**All passwords:** `password123`

---

## Construction Companies (Cabinets)

```
Cabinet 1:
  Name: BTP Solutions Sénégal
  Address: 123 Avenue Cheikh Anta Diop, Dakar
  Tax ID: SN123456789
  
  Users: 5 (all roles)
  Sites: 2
  Personnel: 6

Cabinet 2:
  Name: Constructions Modernes SARL
  Address: 456 Boulevard de l'Indépendance, Dakar
  Tax ID: SN987654321
  
  Users: 2
  Sites: 1
  Personnel: 0
```

---

## Job Skills

```
1. Maçon (Mason)
2. Ferrailleur (Reinforcement worker)
3. Électricien (Electrician)
4. Plombier (Plumber)
5. Peintre (Painter)
6. Menuisier (Carpenter)
7. Conducteur d'équipe (Team leader)
8. Chef de chantier (Site foreman)
```

---

## Personnel Examples

```
Worker 1:
  Name: Samba Sane
  Skills: Maçon
  Daily Rate: 15,000 FCFA
  Cabinet: BTP Solutions Sénégal
  Assignments: 2 sites
  
Worker 2:
  Name: Ibrahima Toure
  Skills: Ferrailleur
  Daily Rate: 18,000 FCFA
  Cabinet: BTP Solutions Sénégal
  Assignments: 1 site
  
Worker 3:
  Name: Lamine Diallo
  Skills: Peintre, Conducteur d'équipe
  Daily Rate: 16,000 FCFA
  Cabinet: BTP Solutions Sénégal
  Assignments: 2 sites
```

---

## Construction Sites

### Site 1: Residential Building

```
Name: Immeuble Residential Plateau
Location: Plateau, Dakar
Status: ACTIVE
Start Date: 120 days ago
Expected End: 180 days from now
Budget: 150,000,000 FCFA
Cabinet: BTP Solutions Sénégal

Phases:
  ├── Terrassement et Fondation (30 days)
  ├── Structure Béton (60 days)
  └── Cloisons et Finitions (60 days)

Personnel Assignments: 4
Material Requests: 1 (PENDING)
Expenses: 3 (APPROVED)
Contract: $100,000,000 CAD
```

### Site 2: Commercial Center

```
Name: Centre Commercial Point E
Location: Point E, Dakar
Status: PLANNING
Start Date: 30 days from now
Expected End: 480 days from now
Budget: 200,000,000 FCFA
Cabinet: BTP Solutions Sénégal

Phases:
  ├── Étude et Préparation (30 days)
  └── Fondations (50 days)

Personnel Assignments: 0
Material Requests: 0
Expenses: 0
Contract: $100,000,000 CAD
```

### Site 3: School Renovation

```
Name: Rénovation École Secondaire Malick Sy
Location: Médina, Dakar
Status: ACTIVE
Start Date: 60 days ago
Expected End: 120 days from now
Budget: 50,000,000 FCFA
Cabinet: Constructions Modernes SARL

Phases:
  ├── Démolition Sélective (20 days)
  └── Reconstruction (60 days)

Personnel Assignments: 3
Material Requests: 1 (APPROVED)
Expenses: 2 (APPROVED)
Contract: $100,000,000 CAD
```

---

## Material Request Example

```
Request #1:
  Site: Immeuble Residential Plateau
  Requested By: Ahmed Ba (Engineer)
  Status: PENDING
  Created: 5 days ago
  Notes: Matériaux nécessaires pour la phase 1 du chantier
  
  Items:
    ├── Ciment CEM II/A 42.5: 10 sacs
    ├── Sable Construction: 20 m³
    ├── Gravier: 30 m³
    └── Acier HA500: 40 kg
  
  Total Cost: ~2,180,500 FCFA
  Status: Awaiting approval
```

---

## Sample Materials (Core 8)

```
1. Ciment CEM II/A 42.5
   Unit: sacs (bags)
   Cost: 8,500 FCFA per bag
   Usage: Concrete, mortar

2. Sable Construction
   Unit: m³ (cubic meter)
   Cost: 35,000 FCFA per m³
   Usage: Concrete, mortar, foundations

3. Gravier (Gravel)
   Unit: m³
   Cost: 40,000 FCFA per m³
   Usage: Concrete aggregate, drainage

4. Acier HA500
   Unit: kg
   Cost: 950 FCFA per kg
   Usage: Concrete reinforcement

5. Brique de Construction
   Unit: unité (pieces)
   Cost: 350 FCFA per brick
   Usage: Walls, partitions

6. Tuiles de Toiture
   Unit: m² (square meter)
   Cost: 5,500 FCFA per m²
   Usage: Roofing

7. Peinture Intérieure
   Unit: litre
   Cost: 12,000 FCFA per liter
   Usage: Interior painting

8. Fenêtres Aluminium
   Unit: unité (pieces)
   Cost: 85,000 FCFA per window
   Usage: Exterior openings
```

---

## Budget Example

```
Site: Immeuble Residential Plateau
Total Budget: 150,000,000 FCFA
Period: 120 days ago to 180 days from now

Spending Analysis:
  Total Approved Expenses: ~9,800,000 FCFA
  Remaining Budget: 140,200,000 FCFA
  Usage: 6.5%
  Status: On track

Breakdown:
  ├── Materials: 5,000,000 FCFA
  ├── Labor: 2,500,000 FCFA
  ├── Transport: 800,000 FCFA
  ├── Equipment: 1,200,000 FCFA
  └── Permits: 300,000 FCFA
```

---

## Expense Examples

```
Expense 1:
  Site: Immeuble Residential Plateau
  Category: Matériaux de Construction
  Amount: 5,000,000 FCFA
  Description: Achat de ciment et sable pour les fondations
  Requested By: Ahmed Ba (Engineer)
  Status: APPROVED
  Date: 5 days ago

Expense 2:
  Site: Immeuble Residential Plateau
  Category: Main d'œuvre
  Amount: 2,500,000 FCFA
  Description: Salaires des ouvriers - janvier
  Requested By: Ahmed Ba (Engineer)
  Status: APPROVED
  Date: 5 days ago

Expense 3:
  Site: Immeuble Residential Plateau
  Category: Transport et Logistique
  Amount: 800,000 FCFA
  Description: Transport des matériaux vers le chantier
  Requested By: Ahmed Ba (Engineer)
  Status: APPROVED
  Date: 5 days ago
```

---

## Expense Categories

```
1. Matériaux de Construction (Building Materials)
2. Main d'œuvre (Labor)
3. Transport et Logistique (Transport & Logistics)
4. Équipements et Outils (Equipment & Tools)
5. Permis et Autorisations (Permits & Authorizations)
6. Assurance (Insurance)
7. Frais Administratifs (Administrative Fees)
```

---

## Contract & Invoice Example

```
Contract:
  Site: Immeuble Residential Plateau
  Client: Client - Immeuble Residential Plateau
  Value: 100,000,000 FCFA
  Signed Date: 120 days ago
  Status: ACTIVE
  Related: 3 invoices

Invoice 1:
  Number: INV-e3ccc8ee-001
  Amount: 20,000,000 FCFA
  Issued: 30 days ago
  Due: 60 days from now
  Status: DRAFT
  
Invoice 2:
  Number: INV-e3ccc8ee-002
  Amount: 20,000,000 FCFA
  Issued: 20 days ago
  Due: 50 days from now
  Status: PAID
  
Invoice 3:
  Number: INV-e3ccc8ee-003
  Amount: 20,000,000 FCFA
  Issued: 10 days ago
  Due: 40 days from now
  Status: PAID
```

---

## Personnel Assignment Example

```
Assignment 1:
  Worker: Samba Sane (Maçon)
  Site: Immeuble Residential Plateau
  Role: Ouvrier Qualifié (Skilled Worker)
  Start: 60 days ago
  End: 120 days from now
  Daily Rate: 15,000 FCFA
  Total Period: 180 days
  Estimated Cost: 2,700,000 FCFA

Assignment 2:
  Worker: Lamine Diallo (Peintre, Chef d'équipe)
  Site: Rénovation École Secondaire Malick Sy
  Role: Ouvrier (Worker)
  Start: 30 days ago
  End: 90 days from now
  Daily Rate: 16,000 FCFA
  Total Period: 120 days
  Estimated Cost: 1,920,000 FCFA
```

---

## Progress Report Example

```
Site: Immeuble Residential Plateau
Phase: Structure Béton
Report Date: Today
Completion: 45%
Status: On Track

Description: Travaux en cours selon le planning prévu. 
             Aucun retard à signaler.
             (Work in progress as planned. No delays to report.)

Key Metrics:
  - Concrete pour volume completed
  - Reinforcement steel installation ongoing
  - Formwork still in progress
  - Weather: Good conditions
  - Workforce: Full capacity
  - Equipment: Operating normally
```

---

## Extended Materials Catalog Preview

The `populate_materials` command adds 80+ materials:

### Aggregates (Granulats)
- Sable Construction 0-4mm: 35,000 FCFA/m³
- Sable Fin 0-2mm: 38,000 FCFA/m³
- Gravier 4-6mm: 40,000 FCFA/m³
- Gravillon 6-10mm: 38,000 FCFA/m³
- Tout-venant: 25,000 FCFA/m³

### Masonry (Éléments de Maçonnerie)
- Parpaing Creux: 2,500 FCFA/unité
- Parpaing Plein: 3,200 FCFA/unité
- Pierre de taille: 25,000 FCFA/m²

### Roofing (Couverture)
- Tuiles Mécaniques: 5,500 FCFA/m²
- Ardoise Naturelle: 8,500 FCFA/m²
- Feuille de Zinc: 12,000 FCFA/m²

### Carpentry (Menuiserie)
- Bois de Charpente: 450,000 FCFA/m³
- Fenêtres Aluminium: 85,000 FCFA/unité
- Portes Bois Massif: 125,000 FCFA/unité

### Finishes (Revêtements)
- Carrelage Sol: 6,500 FCFA/m²
- Mosaïque Céramique: 8,500 FCFA/m²
- Revêtement Vinyl: 3,500 FCFA/m²

### Paint (Peintures)
- Peinture Intérieure: 12,000 FCFA/litre
- Peinture Extérieure: 15,000 FCFA/litre
- Vernis Transparent: 18,000 FCFA/litre

### Plumbing (Plomberie)
- Tuyau PVC 20mm: 1,200 FCFA/mètre
- Tuyau PVC 50mm: 2,500 FCFA/mètre
- WC Porcelaine: 45,000 FCFA/unité

### Electrical (Électricité)
- Câble Électrique 2.5mm²: 800 FCFA/mètre
- Câble Électrique 10mm²: 2,200 FCFA/mètre
- Disjoncteur 20A: 8,500 FCFA/unité
- Prise de Courant: 4,500 FCFA/unité

---

## Data Statistics

```
Total Records Created:
  ├── Users: 5
  ├── Cabinets: 2
  ├── Personnel: 6
  ├── Skills: 8 (assigned to 6 workers)
  ├── Sites: 3
  ├── Project Phases: 9
  ├── Progress Reports: 3
  ├── Site Assignments: 8
  ├── Materials: 8 (core) + 80 (extended) = 88 total
  ├── Material Requests: 2
  ├── Material Request Items: 8
  ├── Budgets: 3
  ├── Expense Categories: 7
  ├── Expenses: 5
  ├── Contracts: 2
  ├── Invoices: 6
  
Total: 100+ records
Execution Time: 2-5 seconds
Database Size: ~200 KB
```

---

## Timeline Example

All dates are relative to today:

```
Timeline for Immeuble Residential Plateau:

Days -120: Project start
  Phase 1 begins: Terrassement et Fondation
  
Days -60: Current date (60 days into Phase 1)
  Phase 1 nearly complete
  Material request created
  First expenses recorded
  
Days 0: TODAY
  Phase 1 (75% complete)
  Phase 2 starting: Structure Béton
  Progress report at 45% completion
  
Days +30: Next month
  Phase 2 in full swing
  More material deliveries expected
  
Days +120: 4 months from now
  Phase 2 complete
  Phase 3 begins: Cloisons et Finitions
  
Days +180: 6 months from now
  Expected project completion
  Final invoicing and handover
```

---

## French Vocabulary Reference

| Term | English |
|------|---------|
| Maçon | Mason |
| Ferrailleur | Reinforcement worker |
| Électricien | Electrician |
| Plombier | Plumber |
| Peintre | Painter |
| Menuisier | Carpenter |
| Chef d'équipe | Team leader |
| Chef de chantier | Site foreman |
| Terrassement | Excavation |
| Fondation | Foundation |
| Béton | Concrete |
| Cloison | Partition |
| Finition | Finish |
| Toiture | Roofing |
| Étanchéité | Waterproofing |
| Démolition | Demolition |

---

This document provides realistic examples of the data structure and content that will be created by running the management commands. All prices are in FCFA and reflect the Senegalese market as of 2024-2025.
