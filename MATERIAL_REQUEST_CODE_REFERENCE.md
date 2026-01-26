# Material Request Enhancement - Code Reference

This document provides detailed code examples and patterns used in the material request enhancement.

## Table of Contents
1. [Model Code Patterns](#model-code-patterns)
2. [Form Code Patterns](#form-code-patterns)
3. [View Code Patterns](#view-code-patterns)
4. [Template Code Patterns](#template-code-patterns)
5. [JavaScript Code Patterns](#javascript-code-patterns)
6. [API Response Examples](#api-response-examples)

---

## Model Code Patterns

### Parent Model: MaterialRequest
```python
from django.db import models
from django.db.models import F, Sum

class MaterialRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('ORDERED', 'Ordered'),
        ('DELIVERED', 'Delivered'),
        ('REJECTED', 'Rejected'),
    ]
    
    site = models.ForeignKey('projects.Site', on_delete=models.CASCADE)
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def total_items(self):
        """Count total number of materials in this request"""
        return self.items.count()
    
    @property
    def total_estimated_cost(self):
        """Calculate sum of all item costs: quantity × material.estimated_cost_per_unit"""
        from django.db.models import F, Sum
        result = self.items.aggregate(
            total=Sum(F('quantity') * F('material__estimated_cost_per_unit'),
                      output_field=models.DecimalField())
        )
        return result['total'] or 0
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Material Request'
        verbose_name_plural = 'Material Requests'
```

### Child Model: MaterialRequestItem
```python
class MaterialRequestItem(models.Model):
    """Junction table linking materials to requests with item-level quantity"""
    
    request = models.ForeignKey(MaterialRequest, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name='request_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def estimated_cost(self):
        """Calculate cost for this item: quantity × material.estimated_cost_per_unit"""
        return self.quantity * self.material.estimated_cost_per_unit
    
    class Meta:
        unique_together = ('request', 'material')  # Prevent duplicates
        verbose_name = 'Material Request Item'
        verbose_name_plural = 'Material Request Items'
```

---

## Form Code Patterns

### Main Request Form
```python
class MaterialRequestForm(forms.ModelForm):
    """Form for request-level information only"""
    
    class Meta:
        model = MaterialRequest
        fields = ['site', 'notes']
        widgets = {
            'site': forms.Select(attrs={
                'class': 'form-select',
                'required': True,
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Add any general notes for this request...',
            }),
        }
```

### Item Form
```python
class MaterialRequestItemForm(forms.ModelForm):
    """Form for individual material items"""
    
    class Meta:
        model = MaterialRequestItem
        fields = ['material', 'quantity', 'notes']
        widgets = {
            'material': forms.Select(attrs={
                'class': 'form-select material-select',
                'required': True,
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control quantity-input',
                'step': '0.01',
                'min': '0.01',
                'required': True,
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Item-specific notes...',
            }),
        }
```

### Formset Definition
```python
# In materials/forms.py
MaterialRequestItemFormSet = inlineformset_factory(
    MaterialRequest,
    MaterialRequestItemItem,
    form=MaterialRequestItemForm,
    extra=1,  # Show one empty form
    min_num=1,  # Require at least one material
    validate_min=True,
    can_delete=True,  # Allow deletion
)
```

---

## View Code Patterns

### Create View with Formset
```python
class MaterialRequestCreateView(LoginRequiredMixin, CreateView):
    model = MaterialRequest
    form_class = MaterialRequestForm
    template_name = 'materials/request_form.html'
    success_url = reverse_lazy('materials:request_list')
    
    def form_valid(self, form):
        """Save main form and process formset"""
        context = self.get_context_data()
        items_formset = context['items_formset']
        
        if items_formset.is_valid():
            self.object = form.save(commit=False)
            self.object.requested_by = self.request.user
            self.object.save()
            
            # Save all items
            items_formset.instance = self.object
            items_formset.save()
            
            return redirect(self.success_url)
        else:
            return self.form_invalid(form)
    
    def get_context_data(self, **kwargs):
        """Add formset to context"""
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['items_formset'] = MaterialRequestItemFormSet(self.request.POST)
        else:
            context['items_formset'] = MaterialRequestItemFormSet()
        return context
```

### Update View with Formset
```python
class MaterialRequestUpdateView(LoginRequiredMixin, UpdateView):
    model = MaterialRequest
    form_class = MaterialRequestForm
    template_name = 'materials/request_form.html'
    
    def form_valid(self, form):
        """Save main form and process formset"""
        context = self.get_context_data()
        items_formset = context['items_formset']
        
        if items_formset.is_valid():
            self.object = form.save()
            items_formset.instance = self.object
            items_formset.save()
            
            return redirect(self.object.get_absolute_url())
        else:
            return self.form_invalid(form)
    
    def get_context_data(self, **kwargs):
        """Add formset to context"""
        context = super().get_context_data(**kwargs)
        if self.request.POST:
            context['items_formset'] = MaterialRequestItemFormSet(
                self.request.POST,
                instance=self.object
            )
        else:
            context['items_formset'] = MaterialRequestItemFormSet(instance=self.object)
        return context
```

### API Endpoint
```python
from django.http import JsonResponse

def materials_data_api(request):
    """Return material data for frontend"""
    materials = Material.objects.all().values('id', 'name', 'unit', 'estimated_cost_per_unit')
    
    # Convert to dictionary by id for easy lookup
    data = {
        str(m['id']): {
            'name': m['name'],
            'unit': m['unit'],
            'estimated_cost_per_unit': float(m['estimated_cost_per_unit']),
        }
        for m in materials
    }
    
    return JsonResponse(data)
```

### List View with Optimization
```python
class MaterialRequestListView(LoginRequiredMixin, ListView):
    model = MaterialRequest
    template_name = 'materials/request_list.html'
    context_object_name = 'requests'
    paginate_by = 25
    
    def get_queryset(self):
        """Optimize queries with prefetch_related"""
        return MaterialRequest.objects.prefetch_related(
            'items__material',  # Prefetch items and their materials
            'site'
        ).order_by('-created_at')
```

---

## Template Code Patterns

### Django Formset in Template
```html
<!-- Main form -->
<form method="post" class="needs-validation">
    {% csrf_token %}
    
    <!-- Main form fields -->
    <div class="form-group">
        <label for="{{ form.site.id_for_label }}">Site</label>
        {{ form.site }}
    </div>
    
    <!-- Formset -->
    {{ items_formset.management_form }}
    
    <div id="materials-container">
        {% for form in items_formset %}
            <div class="material-item form-row">
                {{ form.id }}  {# Hidden PK field #}
                
                <div class="col-md-5">
                    <label>Material</label>
                    {{ form.material }}
                </div>
                
                <div class="col-md-3">
                    <label>Quantity</label>
                    <input type="number" name="{{ form.quantity.html_name }}" step="0.01">
                </div>
                
                <div class="col-md-4">
                    <!-- Delete checkbox (hidden) -->
                    {{ form.DELETE }}
                    <button type="button" class="btn btn-danger btn-sm delete-btn">
                        Delete
                    </button>
                </div>
            </div>
        {% endfor %}
    </div>
    
    <button type="submit">Submit</button>
</form>
```

### Formset Field Naming Convention
```
Form name prefix: items

Field name: items-{index}-{fieldname}

Examples:
- items-0-material      # Material for first item
- items-0-quantity      # Quantity for first item
- items-0-notes        # Notes for first item
- items-0-DELETE       # Delete checkbox for first item
- items-0-id           # ID for first item
- items-TOTAL_FORMS    # Total number of forms
- items-INITIAL_FORMS  # Number of initial forms
- items-MIN_NUM_FORMS  # Minimum forms required
- items-MAX_NUM_FORMS  # Maximum forms allowed
```

### Loop Through Items in Detail
```html
<table class="table">
    <tbody>
        {% for item in request.items.all %}
        <tr>
            <td>
                <h6>{{ item.material.name }}</h6>
                {% if item.notes %}
                <small>{{ item.notes }}</small>
                {% endif %}
            </td>
            <td>{{ item.quantity }} {{ item.material.unit }}</td>
            <td>${{ item.estimated_cost|floatformat:2 }}</td>
        </tr>
        {% endfor %}
    </tbody>
    <tfoot>
        <tr>
            <td colspan="2">Total:</td>
            <td>${{ request.total_estimated_cost|floatformat:2 }}</td>
        </tr>
    </tfoot>
</table>
```

### Material Preview in List
```html
<!-- Show first 3 materials, "+N more" for rest -->
{% for item in request.items.all|slice:":3" %}
    <span class="badge bg-light">{{ item.material.name }} ({{ item.quantity }})</span>
{% endfor %}
{% if request.items.count > 3 %}
    <span class="badge bg-secondary">+{{ request.items.count|add:-3 }} more</span>
{% endif %}
```

---

## JavaScript Code Patterns

### Fetch Material Data (Cache)
```javascript
let materialData = null;

async function fetchMaterialData() {
    if (materialData) {
        return materialData;  // Return cached
    }
    
    try {
        const response = await fetch('{% url "materials:materials_data_api" %}');
        const data = await response.json();
        materialData = data;
        return data;
    } catch (error) {
        console.error('Failed to fetch materials:', error);
        return {};
    }
}
```

### Dynamic Item Addition
```javascript
let itemCount = document.querySelectorAll('.material-item').length;

document.getElementById('add-material-btn').addEventListener('click', async function() {
    const container = document.getElementById('materials-container');
    const newIndex = itemCount;
    
    // Create new row HTML
    const newRow = document.createElement('div');
    newRow.className = 'material-item p-3 border rounded-3 mb-3';
    newRow.innerHTML = `
        <div class="row g-2">
            <div class="col-md-5">
                <label class="form-label">Material</label>
                <select name="items-${newIndex}-material" class="form-select material-select">
                    <option value="">Select material...</option>
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label">Quantity</label>
                <input type="number" name="items-${newIndex}-quantity" 
                       class="form-control quantity-input" step="0.01" min="0.01">
                <small class="text-muted unit-display">unit</small>
            </div>
            <div class="col-md-4">
                <button type="button" class="btn btn-sm btn-outline-danger delete-btn">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>
        </div>
    `;
    
    container.appendChild(newRow);
    
    // Update total forms count
    const totalFormsInput = document.querySelector('[name="items-TOTAL_FORMS"]');
    totalFormsInput.value = ++itemCount;
    
    // Initialize handlers for new item
    initializeItem(newRow);
});
```

### Material Selection Handler
```javascript
function setupMaterialSelect(item) {
    const select = item.querySelector('.material-select');
    const quantityInput = item.querySelector('.quantity-input');
    const unitDisplay = item.querySelector('.unit-display');
    
    select.addEventListener('change', async function() {
        const materialId = this.value;
        const data = await fetchMaterialData();
        
        if (materialId && data[materialId]) {
            const material = data[materialId];
            unitDisplay.textContent = material.unit;
        }
        
        updateTotalCost();
    });
    
    quantityInput.addEventListener('input', updateTotalCost);
}
```

### Cost Calculation
```javascript
function calculateItemCost(item) {
    const select = item.querySelector('.material-select');
    const quantityInput = item.querySelector('.quantity-input');
    const materialId = select.value;
    const quantity = parseFloat(quantityInput.value) || 0;
    
    if (materialId && materialData) {
        const material = materialData[materialId];
        if (material) {
            return quantity * material.estimated_cost_per_unit;
        }
    }
    
    return 0;
}

function updateTotalCost() {
    let total = 0;
    document.querySelectorAll('.material-item').forEach(item => {
        const deleteCheckbox = item.querySelector('[name*="DELETE"]');
        if (!deleteCheckbox || !deleteCheckbox.checked) {
            total += calculateItemCost(item);
        }
    });
    
    const costDisplay = document.getElementById('total-cost');
    if (costDisplay) {
        costDisplay.textContent = '$' + total.toFixed(2);
    }
    
    updateItemCount();
}

function updateItemCount() {
    let count = 0;
    document.querySelectorAll('.material-item').forEach(item => {
        const deleteCheckbox = item.querySelector('[name*="DELETE"]');
        if (!deleteCheckbox || !deleteCheckbox.checked) {
            count++;
        }
    });
    
    const badge = document.getElementById('item-count-badge');
    if (badge) {
        badge.textContent = count;
    }
}
```

### Delete Handler
```javascript
function setupRemoveBtn(item) {
    const deleteBtn = item.querySelector('.delete-btn');
    const deleteCheckbox = item.querySelector('[name*="DELETE"]');
    
    deleteBtn.addEventListener('click', function() {
        if (deleteCheckbox) {
            // For existing items, set DELETE checkbox
            deleteCheckbox.checked = true;
            item.style.display = 'none';
        } else {
            // For new items, just remove
            item.remove();
            
            // Update total forms
            const totalFormsInput = document.querySelector('[name="items-TOTAL_FORMS"]');
            totalFormsInput.value--;
        }
        
        updateTotalCost();
    });
}
```

---

## API Response Examples

### Materials Data API Response
```json
{
  "1": {
    "name": "Cement Bag (50kg)",
    "unit": "bag",
    "estimated_cost_per_unit": 5.50
  },
  "2": {
    "name": "Steel Rod (12mm)",
    "unit": "meter",
    "estimated_cost_per_unit": 2.25
  },
  "3": {
    "name": "Sand",
    "unit": "cubic meter",
    "estimated_cost_per_unit": 45.00
  },
  "4": {
    "name": "Gravel",
    "unit": "cubic meter",
    "estimated_cost_per_unit": 40.00
  }
}
```

### Formset POST Data Format
```
POST /materials/requests/create/

site: 5
notes: General notes for the request
items-TOTAL_FORMS: 2
items-INITIAL_FORMS: 0
items-MIN_NUM_FORMS: 1
items-MAX_NUM_FORMS: 1000
items-0-material: 1
items-0-quantity: 10
items-0-notes: First material notes
items-0-DELETE: (unchecked/missing)
items-1-material: 2
items-1-quantity: 50
items-1-notes: Second material notes
items-1-DELETE: (unchecked/missing)
```

### Formset Response (edit existing)
```html
<!-- When editing existing request with 2 items:

items-TOTAL_FORMS: 3
items-INITIAL_FORMS: 2
items-MIN_NUM_FORMS: 1
items-MAX_NUM_FORMS: 1000

items-0-id: 45          <!-- Existing item #1 -->
items-0-material: 1
items-0-quantity: 10
items-0-DELETE: (unchecked)

items-1-id: 46          <!-- Existing item #2 -->
items-1-material: 2
items-1-quantity: 50
items-1-DELETE: (unchecked)

items-2-material: 3     <!-- New item being added -->
items-2-quantity: 25
items-2-DELETE: (unchecked)
-->
```

---

## Common Patterns & Best Practices

### Always Use Prefetch for Performance
```python
# ✅ Good
requests = MaterialRequest.objects.prefetch_related('items__material')

# ❌ Bad (N+1 queries)
requests = MaterialRequest.objects.all()
for req in requests:
    for item in req.items.all():  # Query per request!
        print(item.material.name)
```

### Always Include CSRF Token
```html
<!-- ✅ Good -->
<form method="post">
    {% csrf_token %}
    ...
</form>

<!-- ❌ Bad -->
<form method="post">
    ...
</form>
```

### Always Validate Formset Min/Max
```python
# ✅ Good
MaterialRequestItemFormSet = inlineformset_factory(
    MaterialRequest,
    MaterialRequestItem,
    min_num=1,
    max_num=100,
    validate_min=True,
    validate_max=True,
)

# ❌ Bad
MaterialRequestItemFormSet = inlineformset_factory(
    MaterialRequest,
    MaterialRequestItem,
)  # No validation!
```

### Always Check Delete Checkbox
```python
# When processing deleted items
if item_form.cleaned_data.get('DELETE'):
    # Item marked for deletion
    pass
```

---

## Debugging Tips

### Check Formset Errors
```python
def form_invalid(self, form):
    """Debug formset errors"""
    context = self.get_context_data()
    items_formset = context['items_formset']
    
    print("Form errors:", form.errors)
    print("Formset errors:", items_formset.errors)
    print("Non-form errors:", items_formset.non_form_errors())
    
    return super().form_invalid(form)
```

### Debug Field Names
```html
<!-- Print field names for debugging -->
<p>Material field name: {{ form.material.html_name }}</p>
<!-- Output: items-0-material -->
```

### JavaScript Console Debugging
```javascript
// Log formset structure
document.querySelectorAll('input[name*="items-"]').forEach(el => {
    console.log(el.name, el.value);
});

// Check TOTAL_FORMS value
console.log('Total forms:', document.querySelector('[name="items-TOTAL_FORMS"]').value);
```

---

**Last Updated:** Current Session
**Reference Version:** 1.0
