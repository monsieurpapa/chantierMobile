# Management Commands Quick Reference

Fast reference guide for Django management commands available in ChantiérMobile.

## Commands Overview

| Command | Purpose | Usage |
|---------|---------|-------|
| `seed_sample_data` | Generate comprehensive sample data | `python manage.py seed_sample_data [--clear]` |
| `clear_sample_data` | Remove all sample data | `python manage.py clear_sample_data [--confirm]` |
| `populate_materials` | Populate 80+ construction materials | `python manage.py populate_materials` |

---

## Quick Start

### Step 1: Start Fresh (Optional)
```bash
python manage.py clear_sample_data --confirm
```

### Step 2: Generate Sample Data
```bash
python manage.py seed_sample_data
```

### Step 3: Add Extended Materials Catalog (Optional)
```bash
python manage.py populate_materials
```

### Step 4: Access the App
- **URL:** http://localhost:8000
- **Admin:** http://localhost:8000/admin

---

## Sample Users

All with password: `password123`

```
directeur_001          → Director
ingenieur_chef_001     → Chief Engineer
ingenieur_001          → Engineer
comptable_001          → Accountant
caissier_001           → Cashier
```

---

## What Gets Created

### seed_sample_data
✅ 5 users with different roles  
✅ 2 construction companies  
✅ 8 job skills  
✅ 6 workers/personnel  
✅ 3 construction sites  
✅ 9 project phases  
✅ 3 progress reports  
✅ 8 personnel assignments  
✅ 8 materials  
✅ 2 material requests  
✅ 3 budgets  
✅ 7 expense categories  
✅ 5 expenses  
✅ Contracts & invoices  

### populate_materials
✅ 80+ realistic construction materials  
✅ Accurate FCFA pricing  
✅ Senegal-focused materials list  

---

## Common Tasks

### Reset Everything
```bash
python manage.py clear_sample_data --confirm
python manage.py seed_sample_data
```

### Add More Materials
```bash
python manage.py populate_materials
```

### Clean Database
```bash
python manage.py clear_sample_data --confirm
```

### Quick Data Check
```bash
# Count objects
python manage.py shell
>>> from accounts.models import User
>>> User.objects.count()
```

---

## Data Details

**Currency:** FCFA (West African CFA franc)  
**Language:** French (names, descriptions, labels)  
**Location:** Senegal (Dakar-based)  
**Daily Rates:** 15,000 - 20,000 FCFA  
**Budget Sizes:** 50M - 200M FCFA  
**Material Costs:** 350 FCFA - 850,000 FCFA  

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Command not found | Ensure migrations are applied: `python manage.py migrate` |
| Data exists | Use `--clear` flag: `python manage.py seed_sample_data --clear` |
| Foreign key errors | Check all apps in INSTALLED_APPS are installed |
| No data created | Check Django logs for errors: `python manage.py seed_sample_data --verbosity=2` |

---

## Documentation

For detailed documentation, see: [MANAGEMENT_COMMANDS_GUIDE.md](MANAGEMENT_COMMANDS_GUIDE.md)

---

## File Locations

- Commands: `accounts/management/commands/`
  - `seed_sample_data.py`
  - `clear_sample_data.py`
  - `populate_materials.py`

---

**Version:** 1.0  
**Last Updated:** January 2026
