# Multilingual Support - Quick Reference

## Essential Commands

```bash
# Extract translatable strings
python manage.py makemessages -l fr -l en

# Compile translations
python manage.py compilemessages

# Create new language
python manage.py makemessages -l es

# Check translations
python manage.py shell
>>> from django.utils import translation
>>> translation.get_language()  # Current language
```

## How to Mark Strings for Translation

### In Python Models/Views:
```python
from django.utils.translation import gettext_lazy as _

# For model choices
class Status(models.TextChoices):
    PENDING = 'PENDING', _('En attente')
    ACTIVE = 'ACTIVE', _('Actif')

# In views/functions
message = _("This will be translated")
```

### In Templates:
```django
{% load i18n %}

<!-- Single string -->
<h1>{% trans "Welcome" %}</h1>

<!-- With variable -->
{% blocktrans %}
  Hello {{ name }}, you have {{ count }} messages.
{% endblocktrans %}
```

## Translation Files

### Location
```
locale/
├── fr/LC_MESSAGES/
│   ├── django.po   (Edit this for French)
│   └── django.mo   (Auto-generated)
└── en/LC_MESSAGES/
    ├── django.po   (Edit this for English)
    └── django.mo   (Auto-generated)
```

### `.po` File Format
```po
msgid "Original text"
msgstr "Translated text"

# With context
msgctxt "button"
msgid "Save"
msgstr "Enregistrer"

# Plural
msgid "You have %d file"
msgid_plural "You have %d files"
msgstr[0] "Vous avez %d fichier"
msgstr[1] "Vous avez %d fichiers"
```

## Using Translations in Templates

```django
{% load i18n %}

<!-- Simple -->
<button>{% trans "Save" %}</button>

<!-- With variable -->
<p>{% trans "Hello" %} {{ user.name }}</p>

<!-- Block with variables -->
{% blocktrans count counter=items|length %}
  You have {{ counter }} item.
{% plural %}
  You have {{ counter }} items.
{% endblocktrans %}

<!-- Language switcher -->
{% include 'includes/language-switcher.html' %}
```

## Available Template Context Variables

```django
{{ LANGUAGE_CODE }}        <!-- 'fr' or 'en' -->
{{ current_language }}     <!-- Full language object -->
{{ languages }}            <!-- List of all languages -->
```

## Language Switching

### Via URL
```
/set-language/?language=en
/set-language/?language=fr
```

### Via Template (included)
```django
{% include 'includes/language-switcher.html' %}
```

### Via Python
```python
from django.utils import translation
translation.activate('fr')  # Activate French
translation.get_language()   # Get current language
```

## Complete Workflow

1. **Write code with translation markers**
   ```python
   message = _("Text to translate")
   ```

2. **Extract translatable strings**
   ```bash
   python manage.py makemessages -l fr -l en
   ```

3. **Edit translation files**
   - `locale/fr/LC_MESSAGES/django.po` - Add French translations
   - `locale/en/LC_MESSAGES/django.po` - Add English translations

4. **Compile translations**
   ```bash
   python manage.py compilemessages
   ```

5. **Restart server and test**
   ```bash
   python manage.py runserver
   ```

## Common Translation Patterns

### Model Choices
```python
class Status(models.TextChoices):
    PENDING = 'PENDING', _('En attente')
    APPROVED = 'APPROVED', _('Approuvé')
    REJECTED = 'REJECTED', _('Rejeté')

# Usage
{{ object.get_status_display() }}  <!-- Auto-translates -->
```

### Admin Verbose Names
```python
class MyModel(models.Model):
    name = models.CharField(_('Nom'), max_length=100)
    status = models.CharField(_('Statut'), max_length=20)
```

### Form Labels
```python
class MyForm(forms.ModelForm):
    class Meta:
        fields = ('name', 'status')
        labels = {
            'name': _('Nom'),
            'status': _('Statut'),
        }
```

### View Messages
```python
from django.contrib import messages

def my_view(request):
    messages.success(request, _('Saved successfully'))
    messages.error(request, _('Error occurred'))
```

## Testing Translations

### Test in Django Shell
```python
>>> from django.utils import translation
>>> translation.activate('fr')
>>> from accounts.models import UserCabinetRole
>>> str(UserCabinetRole.Role.DIRECTOR[1])
'Directeur de Cabinet'
>>> translation.activate('en')
>>> str(UserCabinetRole.Role.DIRECTOR[1])
'Cabinet Director'
```

### Check Translation Coverage
```bash
# Generate messages
python manage.py makemessages -l fr

# Open django.po and count untranslated (empty msgstr)
grep -c 'msgstr ""' locale/fr/LC_MESSAGES/django.po
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Translations not showing | Run `compilemessages` and restart server |
| New strings not translating | Mark with `_()` or `{% trans %}`, run `makemessages` |
| Wrong language | Check session/cookie, test with switcher |
| `.mo` files missing | Run `compilemessages` |
| Settings import error | Ensure `gettext_lazy` imported at top |

## Settings Summary

```python
# Default language
LANGUAGE_CODE = 'fr'

# Supported languages
LANGUAGES = [
    ('fr', _('Français')),
    ('en', _('English')),
]

# Translation files location
LOCALE_PATHS = [BASE_DIR / 'locale']

# Required middleware
MIDDLEWARE = [..., 'django.middleware.locale.LocaleMiddleware', ...]

# Required in TEMPLATES context_processors
'django.template.context_processors.i18n',
```

## Files

### Configuration
- `chantiermobile/settings.py` - i18n settings
- `chantiermobile/urls.py` - Language routes

### Utilities
- `core/i18n_utils.py` - Helper functions
- `core/i18n_views.py` - Language switching views
- `core/context_processors.py` - Template context

### UI Components
- `templates/includes/language-switcher.html` - Language dropdown

### Translations
- `locale/fr/LC_MESSAGES/django.po` - French translations
- `locale/en/LC_MESSAGES/django.po` - English translations

## Documentation

Full guides available:
- [MULTILINGUAL_IMPLEMENTATION_GUIDE.md](MULTILINGUAL_IMPLEMENTATION_GUIDE.md) - Complete guide
- [MULTILINGUAL_SUPPORT_SUMMARY.md](MULTILINGUAL_SUPPORT_SUMMARY.md) - Overview

---

**Key Point**: After editing `.po` files, always run `python manage.py compilemessages` and restart the server!
