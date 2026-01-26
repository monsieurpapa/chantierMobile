# Material Request Enhancement - Architecture Diagrams

## 1. Data Model Relationship Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATABASE SCHEMA                           │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│      Site (*)        │
├──────────────────────┤
│ id (PK)              │
│ name                 │
│ location             │
│ ...                  │
└──────────────────────┘
         ▲
         │ 1:N
         │ (ForeignKey)
         │
┌──────────────────────────────────────┐
│   MaterialRequest                    │
├──────────────────────────────────────┤
│ id (PK)                              │
│ site_id (FK) ─────────────────┐      │
│ notes (TextField)             │      │
│ status (PENDING|APPROVED|...) │      │
│ requested_by_id (FK)          │      │
│ created_at                    │      │
│ updated_at                    │      │
├──────────────────────────────────────┤
│ Properties:                          │
│ • total_items                        │
│ • total_estimated_cost               │
└──────────────────────────────────────┘
         ▲
         │ 1:N
         │ (Reverse relation: items)
         │
┌──────────────────────────────────────┐
│   MaterialRequestItem (Junction)     │
├──────────────────────────────────────┤
│ id (PK)                              │
│ request_id (FK) ──────────────┐      │
│ material_id (FK) ─────────────┼──┐   │
│ quantity (DecimalField)       │  │   │
│ notes (TextField)             │  │   │
│ created_at                    │  │   │
│ updated_at                    │  │   │
├──────────────────────────────────────┤
│ Constraints:                         │
│ • unique_together (request, material)│
├──────────────────────────────────────┤
│ Properties:                          │
│ • estimated_cost                     │
└──────────────────────────────────────┘
                                  │
                                  │ N:1
                                  │ (ForeignKey)
                                  │
                     ┌────────────────────┐
                     │   Material (*)     │
                     ├────────────────────┤
                     │ id (PK)            │
                     │ name               │
                     │ unit               │
                     │ estimated_cost_... │
                     │ ...                │
                     └────────────────────┘
```

## 2. Request Lifecycle State Machine

```
┌─────────────────────────────────────────────────────────────────┐
│                    REQUEST STATUS FLOW                           │
└─────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │   Created    │
    └──────┬───────┘
           │
           ▼
    ┌──────────────────┐
    │  PENDING ────┐   │  (Awaiting approval)
    │  [User can   │   │
    │   edit/add]  │   │
    └──────┬───────┘   │
           │           │
           ├───────────┼──────────────────────┐
           │           │                      │
           ▼           ▼                      ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  APPROVED    │  │  REJECTED    │  │   (Manual)   │
    │  (Director   │  │  (Director   │  │   (Re-edit)  │
    │   approves)  │  │   rejects)   │  │              │
    └──────┬───────┘  └──────────────┘  └──────┬───────┘
           │                                    │
           └────────────────┬───────────────────┘
                            │
                            ▼
                   ┌──────────────────┐
                   │   ORDERED        │ (Procurement)
                   │  (Materials      │
                   │   ordered)       │
                   └──────┬───────────┘
                          │
                          ▼
                   ┌──────────────────┐
                   │   DELIVERED      │ (Final state)
                   │  (Materials      │
                   │   received)      │
                   └──────────────────┘
```

## 3. Request Creation Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                  CREATE/EDIT REQUEST FLOW                        │
└─────────────────────────────────────────────────────────────────┘

   User visits /materials/requests/create/
            │
            ▼
   ┌─────────────────────────┐
   │ MaterialRequestCreateView│
   │ (GET request)           │
   └────────────┬────────────┘
                │
                ▼
   ┌─────────────────────────────────────┐
   │ Render request_form.html            │
   │ ┌───────────────────────────────┐   │
   │ │ Main Form (MaterialRequestForm)   │
   │ ├───────────────────────────────┤   │
   │ │ • Site (required)             │   │
   │ │ • Notes (optional)            │   │
   │ └───────────────────────────────┘   │
   │                                     │
   │ ┌───────────────────────────────┐   │
   │ │ Formset (MaterialRequest....) │   │
   │ ├───────────────────────────────┤   │
   │ │ Item 0:                       │   │
   │ │ • Material (required)         │   │
   │ │ • Quantity (required)         │   │
   │ │ • Notes (optional)            │   │
   │ └───────────────────────────────┘   │
   │                                     │
   │ ┌───────────────────────────────┐   │
   │ │ JavaScript Functions          │   │
   │ ├───────────────────────────────┤   │
   │ │ • fetchMaterialData()         │   │
   │ │ • updateUnit()                │   │
   │ │ • calculateItemCost()         │   │
   │ │ • addMaterialItem()           │   │
   │ │ • setupRemoveBtn()            │   │
   │ └───────────────────────────────┘   │
   └─────────────────────────────────────┘
                │
                │ User fills form & clicks Submit
                ▼
   ┌─────────────────────────────────────┐
   │ MaterialRequestCreateView           │
   │ (POST request)                      │
   ├─────────────────────────────────────┤
   │ form_valid()                        │
   │ ├─ Validate MaterialRequestForm     │
   │ ├─ Validate MaterialRequestFormSet  │
   │ └─ Both valid?                      │
   └────────────┬─────────────────────────┘
                │
        ┌───────┴────────┐
        │                │
     YES│                │NO
        ▼                ▼
   ┌─────────┐    ┌──────────────┐
   │ Save    │    │ Re-render    │
   │ Request │    │ form with    │
   │ +Items  │    │ error msgs   │
   └────┬────┘    └──────────────┘
        │
        ▼
   ┌──────────────────┐
   │ Redirect to      │
   │ request_detail   │
   └──────────────────┘
```

## 4. Form Data Structure

```
┌─────────────────────────────────────────────────────────────────┐
│                   FORMSET DATA STRUCTURE                         │
└─────────────────────────────────────────────────────────────────┘

HTML Form:
  └─ POST Data
     ├─ site: "5"
     ├─ notes: "General notes"
     │
     └─ Formset Management:
        ├─ items-TOTAL_FORMS: "3"
        ├─ items-INITIAL_FORMS: "0"
        ├─ items-MIN_NUM_FORMS: "1"
        ├─ items-MAX_NUM_FORMS: "1000"
        │
        ├─ Item 0 (First material):
        │  ├─ items-0-material: "1"
        │  ├─ items-0-quantity: "10"
        │  ├─ items-0-notes: "First material"
        │  ├─ items-0-DELETE: (unchecked/empty)
        │  └─ items-0-id: (empty for new)
        │
        ├─ Item 1 (Second material):
        │  ├─ items-1-material: "2"
        │  ├─ items-1-quantity: "50"
        │  ├─ items-1-notes: "Second material"
        │  ├─ items-1-DELETE: (unchecked/empty)
        │  └─ items-1-id: (empty for new)
        │
        └─ Item 2 (Third material - new):
           ├─ items-2-material: "3"
           ├─ items-2-quantity: "25"
           ├─ items-2-notes: ""
           ├─ items-2-DELETE: (unchecked/empty)
           └─ items-2-id: (empty for new)

Django Formset Processing:
  └─ MaterialRequestItemFormSet
     ├─ form 0: MaterialRequestItemForm
     │  └─ cleaned_data: {material: 1, quantity: 10, notes: "..."}
     ├─ form 1: MaterialRequestItemForm
     │  └─ cleaned_data: {material: 2, quantity: 50, notes: "..."}
     └─ form 2: MaterialRequestItemForm
        └─ cleaned_data: {material: 3, quantity: 25, notes: ""}

Database Operations:
  └─ For each valid form:
     └─ MaterialRequestItem.objects.create(
          request=request,
          material=form.cleaned_data['material'],
          quantity=form.cleaned_data['quantity'],
          notes=form.cleaned_data['notes']
        )
```

## 5. API Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                  API & JAVASCRIPT INTERACTION                    │
└─────────────────────────────────────────────────────────────────┘

Frontend (request_form.html):
  │
  ├─ Page Load
  │  └─ document.addEventListener('DOMContentLoaded', ...)
  │
  ├─ Call: fetchMaterialData()
  │  │
  │  └─ Async fetch('/materials/api/materials-data/')
  │     │
  │     ▼ HTTP GET Request
  │
Backend (materials_data_api):
  │
  ├─ Query all Material objects
  │
  ├─ Build dict: {id: {name, unit, estimated_cost_per_unit}}
  │
  └─ Return JsonResponse
     │
     ▼ HTTP 200 OK
      └─ JSON Response:
         {
           "1": {
             "name": "Cement Bag",
             "unit": "bag",
             "estimated_cost_per_unit": 5.50
           },
           "2": {
             "name": "Steel Rod",
             "unit": "meter",
             "estimated_cost_per_unit": 2.25
           },
           ...
         }

Frontend (continued):
  │
  ├─ Store in: materialData (global cache)
  │
  ├─ When Material Selected:
  │  └─ updateUnit(select)
  │     └─ materialData[selected_id].unit
  │
  ├─ When Quantity Changed:
  │  └─ calculateItemCost()
  │     └─ quantity × materialData[material_id].estimated_cost_per_unit
  │
  └─ Update Display:
     └─ document.getElementById('item-cost').textContent = "$123.45"
```

## 6. View Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    VIEW ARCHITECTURE                             │
└─────────────────────────────────────────────────────────────────┘

URL Routes:
  ├─ /materials/requests/
  │  └─ MaterialRequestListView (GET)
  │
  ├─ /materials/requests/create/
  │  ├─ MaterialRequestCreateView (GET)
  │  └─ MaterialRequestCreateView (POST)
  │
  ├─ /materials/requests/<id>/
  │  └─ MaterialRequestDetailView (GET)
  │
  ├─ /materials/requests/<id>/edit/
  │  ├─ MaterialRequestUpdateView (GET)
  │  └─ MaterialRequestUpdateView (POST)
  │
  └─ /materials/api/materials-data/
     └─ materials_data_api (GET) → JSON

View Hierarchy:
  ├─ CreateView (Django)
  │  └─ MaterialRequestCreateView
  │     ├─ form_class: MaterialRequestForm
  │     ├─ get_context_data()
  │     │  └─ Add items_formset
  │     └─ form_valid()
  │        ├─ Save main form
  │        ├─ Save formset
  │        └─ Redirect to detail
  │
  ├─ UpdateView (Django)
  │  └─ MaterialRequestUpdateView
  │     ├─ (same as CreateView)
  │     └─ Works with existing instance
  │
  ├─ ListView (Django)
  │  └─ MaterialRequestListView
  │     ├─ queryset with prefetch_related
  │     └─ paginate_by: 25
  │
  ├─ DetailView (Django)
  │  └─ MaterialRequestDetailView
  │     ├─ queryset with prefetch_related
  │     └─ context: items list
  │
  └─ FunctionView (Django)
     └─ materials_data_api
        └─ Return JsonResponse
```

## 7. Template Rendering Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                  TEMPLATE RENDERING FLOW                         │
└─────────────────────────────────────────────────────────────────┘

List View:
  request_list.html
  ├─ for loop: {% for request in requests %}
  │  ├─ Display: {{ request.site.name }}
  │  ├─ Display: {{ request.total_items }}
  │  ├─ Display: {{ request.total_estimated_cost }}
  │  ├─ Inner loop:
  │  │  └─ {% for item in request.items.all|slice:":3" %}
  │  │     └─ Show material preview badges
  │  │
  │  └─ Actions: View / Edit buttons
  │
  └─ empty: No requests found message

Detail View:
  request_detail.html
  ├─ Display: {{ request.site.name }}
  ├─ Display: {{ request.status }}
  ├─ Display: {{ request.notes }}
  │
  ├─ Materials Table:
  │  ├─ thead: Material | Qty | Cost
  │  ├─ tbody:
  │  │  └─ {% for item in request.items.all %}
  │  │     ├─ {{ item.material.name }}
  │  │     ├─ {{ item.quantity }} {{ item.material.unit }}
  │  │     ├─ {{ item.estimated_cost }}
  │  │     └─ {% if item.notes %} {{ item.notes }} {% endif %}
  │  │
  │  └─ tfoot:
  │     └─ Total: {{ request.total_estimated_cost }}
  │
  ├─ Summary Card:
  │  ├─ Total Items: {{ request.total_items }}
  │  ├─ Total Cost: {{ request.total_estimated_cost }}
  │  └─ Status Progress Bar
  │
  └─ Requester Info & Actions

Form View:
  request_form.html
  ├─ Main Form (MaterialRequestForm):
  │  ├─ Site Select
  │  └─ Notes Textarea
  │
  ├─ Formset Management:
  │  └─ {{ items_formset.management_form }}
  │
  ├─ Items Loop:
  │  └─ {% for form in items_formset %}
  │     ├─ Material Select
  │     ├─ Quantity Input
  │     ├─ Notes Textarea
  │     ├─ Delete Button
  │     └─ Form Hidden Fields (id, DELETE checkbox)
  │
  ├─ Add Material Button:
  │  └─ JavaScript click handler
  │
  ├─ JavaScript Functions:
  │  ├─ fetchMaterialData()
  │  ├─ updateUnit()
  │  ├─ calculateItemCost()
  │  ├─ addMaterialItem()
  │  └─ setupRemoveBtn()
  │
  └─ Submit/Cancel Buttons
```

## 8. Performance Query Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUERY OPTIMIZATION                            │
└─────────────────────────────────────────────────────────────────┘

WITHOUT Optimization (N+1 Problem):
  ListViewquery
  ├─ Query 1: SELECT * FROM material_request LIMIT 25
  ├─ For each request in results (N):
  │  └─ Query: SELECT * FROM material_request_item WHERE request_id = ?
  │     ├─ For each item in results (M):
  │     │  └─ Query: SELECT * FROM material WHERE id = ?
  │     │
  │     └─ Total queries: 1 + N + (N × M)
  │        └─ Example: 1 + 25 + (25 × 3) = 101 queries!

WITH prefetch_related (Optimized):
  ListView.get_queryset()
  ├─ prefetch_related('items__material')
  │
  ├─ Execution:
  │  ├─ Query 1: SELECT * FROM material_request LIMIT 25
  │  ├─ Query 2: SELECT * FROM material_request_item 
  │  │           WHERE request_id IN (list_of_25_ids)
  │  └─ Query 3: SELECT * FROM material 
  │             WHERE id IN (list_of_all_material_ids)
  │
  └─ Total queries: 3 (regardless of N/M)
     └─ 25 requests × 3 items = 75 rows from Query 2
        └─ All materials fetched in single Query 3

Performance Improvement:
  ├─ Without optimization: 101 queries
  ├─ With optimization: 3 queries
  └─ Improvement: 97% reduction! ✅
```

---

**Diagrams Version:** 1.0
**Last Updated:** Current Session
