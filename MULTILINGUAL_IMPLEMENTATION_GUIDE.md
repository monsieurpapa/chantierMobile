# Multilingual Support Implementation Guide

## Overview

ChantiérMobile now supports multilingual interface in **French (Français)** and **English**. All user-facing text has been marked for translation and the infrastructure is in place for complete localization.

## Architecture

### 1. Settings Configuration
- **LANGUAGE_CODE**: Default language set to French (`'fr'`)
- **LANGUAGES**: Supports French and English
- **LOCALE_PATHS**: Translation files stored in `locale/` directory
- **LocaleMiddleware**: Automatically detects and sets language based on:
  - User's language preference from settings
  - HTTP Accept-Language header
  - Session language setting

### 2. Translation Files Structure
```
locale/
├── fr/
│   └── LC_MESSAGES/
│       ├── django.po      (French translations)
│       └── django.mo      (Compiled translations)
└── en/
    └── LC_MESSAGES/
        ├── django.po      (English translations)
        └── django.mo      (Compiled translations)
```

### 3. Translation Tags

In templates, use:
```django
{% load i18n %}

<!-- Translate static text -->
{% trans "text to translate" %}

<!-- Translate variable text -->
{{ variable|default:_("Default text") }}

<!-- Block translations -->
{% blocktrans %}
  Hello {{ name }}, you have {{ count }} messages.
{% endblocktrans %}
```

In Python code, use:
```python
from django.utils.translation import gettext_lazy as _

# For immediate use (e.g., in views)
message = _("Hello, world!")

# For model choices and similar
class Status(models.TextChoices):
    PENDING = 'PENDING', _('Pending')
    APPROVED = 'APPROVED', _('Approved')
```

## Workflow: Adding Translations

### Step 1: Mark Strings for Translation

In Python files:
```python
from django.utils.translation import gettext_lazy as _

message = _("This text will be translated")
```

In Template files:
```django
{% load i18n %}
<h1>{% trans "Welcome" %}</h1>
```

### Step 2: Extract Translatable Strings

Run the command to create/update `.po` files:

```bash
python manage.py makemessages -l fr -l en
```

This scans all `.py` and `.html` files and creates/updates:
- `locale/fr/LC_MESSAGES/django.po`
- `locale/en/LC_MESSAGES/django.po`

### Step 3: Edit Translation Files

Open `locale/fr/LC_MESSAGES/django.po` and add French translations:

```po
#: accounts/models.py:10
msgid "Welcome"
msgstr "Bienvenue"

#: projects/models.py:25
msgid "Active"
msgstr "Actif"
```

Similarly edit `locale/en/LC_MESSAGES/django.po` for English translations.

### Step 4: Compile Translations

Convert `.po` files to binary `.mo` files:

```bash
python manage.py compilemessages
```

### Step 5: Restart Django

The translations are now active. Restart the development server:

```bash
python manage.py runserver
```

## Usage: Language Switching

### In Templates

Include the language switcher component:
```django
{% include 'includes/language-switcher.html' %}
```

This displays a dropdown menu to switch between French and English.

### In Views

```python
from django.utils import translation

# Activate a language
translation.activate('fr')

# Get current language
current_lang = translation.get_language()  # Returns 'fr' or 'en'
```

### In URLs

Visit `/set-language/?language=en` to switch to English.

## Implementation Details

### Files Modified

1. **Settings** (`chantiermobile/settings.py`):
   - Added `LocaleMiddleware`
   - Configured `LANGUAGES`
   - Set `LOCALE_PATHS`
   - Updated context processors

2. **URLs** (`chantiermobile/urls.py`):
   - Added language switching route
   - Included Django's i18n URLs

3. **Models**:
   - Updated all `TextChoices` with translated labels
   - Used `gettext_lazy` for all choice strings

4. **Templates**:
   - Added `{% load i18n %}` tags
   - Wrapped user-facing text with `{% trans %}` tags
   - Added language switcher component

### New Files Created

1. **core/i18n_utils.py**: Translation utilities
2. **core/i18n_views.py**: Language switching views
3. **core/context_processors.py**: Template context helpers
4. **templates/includes/language-switcher.html**: Language switcher UI

## Model Fields Translated

### Accounts
- UserCabinetRole.Role: Director → Directeur de Cabinet
- UserCabinetRole.Status: Pending Approval → En attente d'approbation

### Projects
- Site.Status: Active → Actif, Planning → En planification, etc.

### Materials
- MaterialRequest.Status: All status choices translated

### Finance
- Expense.Status: All status choices translated

### Revenue
- Invoice.Status: Draft → Brouillon, Paid → Payé, etc.
- Payment.Method: Bank Transfer → Virement bancaire, etc.

## Translation Coverage

### Currently Translated
- ✅ Model choice fields
- ✅ Navigation menu
- ✅ Common buttons (Create, Edit, Delete, etc.)
- ✅ Status messages
- ✅ User profile menu

### To Be Translated
- Form labels and help texts
- Email templates
- Error messages
- System notifications

## Best Practices

### 1. Always Use Translation Tags
```django
<!-- Good -->
<h1>{% trans "Welcome" %}</h1>

<!-- Bad -->
<h1>Welcome</h1>
```

### 2. Use Lazy Translation in Models
```python
# Good
status = _("Active")

# Bad
status = "Active"
```

### 3. Handle Plurals
```django
{% blocktrans count counter=obj_count %}
  You have {{ counter }} object.
{% plural %}
  You have {{ counter }} objects.
{% endblocktrans %}
```

### 4. Keep Translation Strings Simple
```python
# Good
_("Save changes")

# Bad
_("Do you want to save the changes you made?")  # Too long
```

### 5. Use Context to Disambiguate
```python
# When same word has different meanings
_("May")  # The month
pgettext("month", "May")

# For different uses
pgettext("button", "Save")  # Button label
pgettext("status", "Save")  # Status message
```

## Workflow Commands

### Extract all translatable strings
```bash
python manage.py makemessages -l fr -l en --ignore=venv
```

### Extract strings for specific language
```bash
python manage.py makemessages -l fr
```

### Update existing translations
```bash
python manage.py makemessages -l fr -l en --update
```

### Compile translations
```bash
python manage.py compilemessages
```

### Check translation files
```bash
django-admin compilemessages --check-changes
```

### Create new locale
```bash
python manage.py makemessages -l es  # For Spanish, for example
```

## Language Persistence

### Session-Based
Language selection is stored in Django session and persists across page navigation.

### Cookie-Based
A language preference cookie is set with configurable lifetime.

### Database-Based (Optional)
Can be enhanced to store user language preference in the User model:

```python
class User(AbstractUser):
    language = models.CharField(
        max_length=5,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE
    )
```

## Admin Interface Localization

The Django admin interface automatically translates based on the user's language setting. Model field verbose names can be customized:

```python
class SiteAdmin(admin.ModelAdmin):
    fieldsets = (
        (_('Site Information'), {
            'fields': ('name', 'location', 'status')
        }),
        (_('Timeline'), {
            'fields': ('start_date', 'expected_end_date')
        }),
    )
```

## Debugging Translation Issues

### 1. Check if strings are marked
Run makemessages and check if your strings appear in `.po` files:
```bash
python manage.py makemessages -l fr
grep "your text" locale/fr/LC_MESSAGES/django.po
```

### 2. Verify compilation
Check if `.mo` files exist:
```bash
ls -la locale/fr/LC_MESSAGES/
ls -la locale/en/LC_MESSAGES/
```

### 3. Clear cache
Django caches translations. Clear it:
```bash
python manage.py compilemessages
# Restart server
```

### 4. Check active language
In shell:
```bash
python manage.py shell
>>> from django.utils import translation
>>> translation.get_language()
'fr'  # Should show current language
```

## Testing Translations

### Test French
```python
# In tests
from django.utils import translation

def test_french_translation():
    with translation.override('fr'):
        assert str(Site.Status.ACTIVE[1]) == "Actif"
```

### Test Language Switching
```python
def test_language_switch(client):
    response = client.get('/set-language/?language=en')
    assert response.status_code == 302
    # Check session language
    assert client.session.get('django_language') == 'en'
```

## Future Enhancements

1. **Additional Languages**: Spanish, Arabic, Portuguese
2. **User Preferences**: Store language choice in User model
3. **RTL Support**: For Arabic and other RTL languages
4. **Date/Time Localization**: Format dates based on language
5. **Number Formatting**: Currency and decimal formatting per locale
6. **Translation Management UI**: Admin interface for managing translations

## Support

For questions or issues with translations:

1. Check Django documentation: https://docs.djangoproject.com/en/stable/topics/i18n/
2. Review the locale files in the repository
3. Check existing translations for patterns
4. Test using `python manage.py shell` with `translation.override()`

## Quick Reference

```bash
# Complete workflow
python manage.py makemessages -l fr -l en      # Extract strings
# Edit locale/*/LC_MESSAGES/django.po           # Add translations
python manage.py compilemessages               # Compile
python manage.py runserver                     # Restart

# Check current language
python manage.py shell
>>> from django.utils import translation
>>> translation.get_language()

# Switch language in view
from django.utils import translation
translation.activate('fr')

# In template
{% load i18n %}
{% trans "Your text here" %}
```

This implementation provides a solid foundation for multilingual support and can be easily extended to support additional languages.
