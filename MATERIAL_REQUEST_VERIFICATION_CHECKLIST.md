# Material Request Enhancement - Pre-Deployment Verification Checklist

## 🔍 Code Review Checklist

### Models (`materials/models.py`)
- [ ] `MaterialRequest.notes` field added (TextField, blank=True)
- [ ] `MaterialRequestItem` model created with:
  - [ ] `request` ForeignKey with related_name='items'
  - [ ] `material` ForeignKey
  - [ ] `quantity` DecimalField
  - [ ] `notes` TextField (optional)
  - [ ] `created_at`, `updated_at` timestamps
- [ ] `unique_together` constraint on (request, material)
- [ ] `total_items` property returns count
- [ ] `total_estimated_cost` property uses aggregation
- [ ] No syntax errors in file

### Forms (`materials/forms.py`)
- [ ] `MaterialRequestForm` has fields: site, notes
- [ ] `MaterialRequestItemForm` has fields: material, quantity, notes
- [ ] `MaterialRequestItemFormSet` configured with:
  - [ ] `form_class=MaterialRequestItemForm`
  - [ ] `extra=1`
  - [ ] `min_num=1`
  - [ ] `can_delete=True`
- [ ] All widgets use correct CSS classes (form-select, form-control)
- [ ] No syntax errors in file

### Views (`materials/views.py`)
- [ ] `MaterialRequestCreateView`:
  - [ ] Has `get_context_data()` method
  - [ ] Passes `items_formset` to template
  - [ ] `form_valid()` saves main form and formset
  - [ ] Handles formset validation errors
- [ ] `MaterialRequestUpdateView` created and implemented
- [ ] `MaterialRequestListView` uses `prefetch_related('items__material')`
- [ ] `MaterialRequestDetailView` updated for multiple items
- [ ] `materials_data_api` function returns JsonResponse
  - [ ] Structure: {id: {name, unit, estimated_cost_per_unit}}
  - [ ] Handles all materials
- [ ] All imports are correct
- [ ] No syntax errors in file

### URLs (`materials/urls.py`)
- [ ] `request_update` path added: `'requests/<int:pk>/edit/'`
- [ ] `materials_data_api` path added: `'api/materials-data/'`
- [ ] All view names referenced correctly
- [ ] No syntax errors in file

### Admin (`materials/admin.py`)
- [ ] `MaterialRequestItemAdmin` class created
- [ ] `MaterialRequestAdmin` has:
  - [ ] `list_display` includes `get_items_count`
  - [ ] `fieldsets` organized logically
  - [ ] `readonly_fields` includes timestamps
  - [ ] `MaterialRequestItemAdmin` as inline
- [ ] `get_items_count()` method implemented
- [ ] All imports are correct
- [ ] No syntax errors in file

### Migration (`materials/migrations/0004_refactor_material_request.py`)
- [ ] File exists in migrations folder
- [ ] Has AddField operation for `notes`
- [ ] Has CreateModel operation for `MaterialRequestItem`
- [ ] Has AlterUniqueTogether operation
- [ ] Dependencies chain is correct
- [ ] Python syntax is valid

---

## 🎨 Template Review Checklist

### request_form.html
- [ ] Hero header section present
- [ ] Site select dropdown visible
- [ ] `{{ items_formset.management_form }}` included
- [ ] Material items container exists (#materials-container)
- [ ] Each item has:
  - [ ] Material select field
  - [ ] Quantity input field
  - [ ] Notes textarea
  - [ ] Delete button
- [ ] "Add Another Material" button present (#add-material-btn)
- [ ] Summary card shows:
  - [ ] Total items count (#item-count-badge)
  - [ ] Total estimated cost (#total-cost)
- [ ] General notes textarea present
- [ ] Submit and Cancel buttons visible
- [ ] JavaScript initialized on page load
- [ ] Bootstrap 5 classes used consistently
- [ ] No template syntax errors

### request_detail.html
- [ ] Site name and link displayed
- [ ] Status badge shown correctly
- [ ] General notes displayed (if present)
- [ ] Materials table shows:
  - [ ] Material name column
  - [ ] Quantity with unit column
  - [ ] Estimated cost column
  - [ ] Item notes (if present)
- [ ] Total estimated cost in table footer
- [ ] Summary card shows:
  - [ ] Total items count
  - [ ] Total estimated cost
  - [ ] Status progress bar
- [ ] Edit button visible for PENDING requests
- [ ] Requester info section present
- [ ] Dates formatted correctly
- [ ] Bootstrap 5 styling applied
- [ ] No template syntax errors

### request_list.html
- [ ] Table headers present:
  - [ ] Site
  - [ ] Materials
  - [ ] Total Items
  - [ ] Est. Cost
  - [ ] Status
  - [ ] Date
  - [ ] Actions
- [ ] Site link functional
- [ ] Material badges show preview (first 3)
- [ ] "+N more" badge shown for >3 items
- [ ] Total items badge displayed
- [ ] Est. cost shown and color-coded
- [ ] Status badges color-coded correctly
- [ ] View button visible
- [ ] Edit button visible for PENDING requests
- [ ] Empty state message present
- [ ] Bootstrap 5 styling applied
- [ ] No template syntax errors

---

## 🚀 JavaScript Verification Checklist

### Data Fetching
- [ ] `fetchMaterialData()` function defined
- [ ] Fetch URL correct: `{% url "materials:materials_data_api" %}`
- [ ] Response parsed as JSON
- [ ] Data cached in `materialData` variable
- [ ] Error handling included
- [ ] Returns proper structure: `{id: {name, unit, estimated_cost_per_unit}}`

### Dynamic Form Management
- [ ] `addMaterialItem()` function works
- [ ] New form index incremented correctly
- [ ] `items-TOTAL_FORMS` updated on add
- [ ] `items-TOTAL_FORMS` updated on delete
- [ ] New items have event listeners attached
- [ ] Delete button removes/hides items correctly

### Event Handlers
- [ ] Material select change → calls `updateUnit()`
- [ ] Material select change → calls `updateTotalCost()`
- [ ] Quantity input change → calls `updateTotalCost()`
- [ ] Delete button click → sets DELETE checkbox (for existing)
- [ ] Delete button click → removes DOM node (for new)
- [ ] Add button click → creates new form row

### Calculations
- [ ] `calculateItemCost()` formula: qty × cost_per_unit
- [ ] `updateTotalCost()` sums all visible items
- [ ] Deleted items excluded from calculation
- [ ] Cost display updated in real-time
- [ ] Currency formatting (2 decimals, $ prefix)
- [ ] `updateItemCount()` counts visible items

### Initialization
- [ ] `initializeItem()` called for each item
- [ ] Event listeners attached to all fields
- [ ] `setupMaterialSelect()` called
- [ ] `setupRemoveBtn()` called
- [ ] On page load, all handlers initialized
- [ ] No JavaScript errors in console

---

## 📊 Functional Testing Checklist

### Create Request
- [ ] Navigate to `/materials/requests/create/`
- [ ] Site dropdown populated
- [ ] Add first material
  - [ ] Material select populated
  - [ ] Quantity input accepted
  - [ ] Unit displays when material selected
- [ ] Click "Add Another Material"
  - [ ] New form row appears
  - [ ] Form indices incremented (items-1-*)
  - [ ] Event handlers attached
- [ ] Cost displays correctly
  - [ ] Item cost = quantity × unit_cost
  - [ ] Total cost = sum of item costs
  - [ ] Updates on quantity change
- [ ] Add notes at request level
- [ ] Add notes at item level
- [ ] Delete an item
  - [ ] Item hidden
  - [ ] Total cost recalculated
  - [ ] Item count updated
- [ ] Submit form
  - [ ] Redirect to detail view
  - [ ] Request created with correct status (PENDING)
  - [ ] All materials linked to request
  - [ ] Costs and quantities saved correctly

### List View
- [ ] Navigate to `/materials/requests/`
- [ ] Requests displayed in table
- [ ] For each request:
  - [ ] Site name linked correctly
  - [ ] Material badges show (up to 3)
  - [ ] "+N more" badge visible if >3
  - [ ] Total items count correct
  - [ ] Est. cost displays correctly
  - [ ] Status badge color correct
  - [ ] Date formatted correctly
  - [ ] View button links to detail
  - [ ] Edit button visible (PENDING only)

### Detail View
- [ ] Navigate to request detail
- [ ] Header shows site name
- [ ] Status badge displayed
- [ ] General notes shown (if present)
- [ ] Materials table displays:
  - [ ] All materials listed
  - [ ] Quantity with unit correct
  - [ ] Item notes displayed
  - [ ] Individual costs correct
- [ ] Table footer:
  - [ ] Total items counted correctly
  - [ ] Total estimated cost correct
- [ ] Summary card shows:
  - [ ] Item count matches
  - [ ] Cost matches
  - [ ] Progress bar shows correct status
- [ ] Requester info section:
  - [ ] Name displayed
  - [ ] Date formatted correctly
- [ ] Edit button links to update view (PENDING only)
- [ ] Approve/Reject buttons visible (PENDING + authorized)

### Update Request
- [ ] Click Edit on PENDING request
- [ ] Form pre-populated with:
  - [ ] Current site selected
  - [ ] Current materials listed
  - [ ] Current quantities filled
  - [ ] Current notes displayed
- [ ] Add new material
  - [ ] Saved correctly
  - [ ] Total cost updated
- [ ] Change quantity
  - [ ] Saved correctly
  - [ ] Cost recalculated
- [ ] Delete material
  - [ ] Marked for deletion
  - [ ] Removed on save
- [ ] Update notes
  - [ ] Saved correctly
- [ ] Submit and verify in detail view

### Admin Interface
- [ ] Navigate to `/admin/materials/materialrequest/`
- [ ] Create new request:
  - [ ] Site select available
  - [ ] Notes field visible
  - [ ] MaterialRequestItemAdmin inline appears
  - [ ] Can add items inline
- [ ] Edit existing request:
  - [ ] Item count displays
  - [ ] Items listed inline
  - [ ] Can add/remove items
  - [ ] Can edit quantities
- [ ] Verify:
  - [ ] Changes saved correctly
  - [ ] Database updated
  - [ ] No validation errors

---

## 📈 Performance Testing Checklist

### Database Queries
- [ ] List view: ~2 queries (with prefetch_related)
- [ ] Detail view: ~2 queries (with prefetch_related)
- [ ] Use Django Debug Toolbar to verify
- [ ] No N+1 queries present

### API Endpoint
- [ ] Visit `/materials/api/materials-data/`
- [ ] Response time < 200ms
- [ ] Valid JSON structure
- [ ] All materials included
- [ ] No errors in response

### Frontend Performance
- [ ] Page load time < 2 seconds
- [ ] Form interactions responsive
- [ ] Cost calculations instant (no lag)
- [ ] "Add Material" button doesn't freeze UI
- [ ] Delete operations smooth

### Browser Compatibility
- [ ] Chrome: All features work
- [ ] Firefox: All features work
- [ ] Safari: All features work
- [ ] Edge: All features work
- [ ] Mobile responsive: Form usable on mobile

---

## 🔐 Security Verification Checklist

### Authentication & Authorization
- [ ] Forms require login (LoginRequiredMixin)
- [ ] Admin actions check user roles
- [ ] Approval buttons check authorization
- [ ] Edit button only visible to request owner/admin
- [ ] Delete operations restricted appropriately

### Form Security
- [ ] CSRF token present on all forms
- [ ] Form validation prevents injection
- [ ] Formset validation prevents invalid data
- [ ] Unique constraint prevents duplicates
- [ ] Foreign key constraints enforced

### Data Validation
- [ ] Quantity must be > 0
- [ ] Material selection required
- [ ] Site selection required
- [ ] Quantity field uses proper field type
- [ ] Cost calculations use Decimal (not float)

### API Security
- [ ] materials_data_api public endpoint (OK)
- [ ] No sensitive data exposed
- [ ] Response structure safe
- [ ] Rate limiting considered (if high traffic)

---

## 📚 Documentation Verification Checklist

### Files Present
- [ ] MATERIAL_REQUEST_ENHANCEMENT.md (technical docs)
- [ ] MATERIAL_REQUEST_QUICKSTART.md (deployment guide)
- [ ] MATERIAL_REQUEST_CODE_REFERENCE.md (code examples)
- [ ] MATERIAL_REQUEST_COMPLETION_SUMMARY.md (overview)
- [ ] MATERIAL_REQUEST_ARCHITECTURE_DIAGRAMS.md (diagrams)
- [ ] MATERIAL_REQUEST_VERIFICATION_CHECKLIST.md (this file)

### Content Quality
- [ ] Each file has clear table of contents
- [ ] Code examples are accurate
- [ ] API responses documented
- [ ] Database schema shown
- [ ] Troubleshooting section present
- [ ] Deployment steps clear
- [ ] No outdated information

### Code Comments
- [ ] Complex functions commented
- [ ] Model properties explained
- [ ] API endpoint documented
- [ ] JavaScript functions documented
- [ ] URL patterns documented

---

## 🐛 Bug Testing Checklist

### Form Validation
- [ ] Submitting empty form shows errors
- [ ] Submitting without material shows error
- [ ] Submitting without quantity shows error
- [ ] Submitting 0 quantity shows error
- [ ] Minimum 1 material enforced
- [ ] Duplicate materials prevented (unique constraint)

### Delete Operations
- [ ] Delete existing item marks for deletion
- [ ] Delete new item removes from DOM
- [ ] Can undo delete by unchecking checkbox
- [ ] At least 1 material required (min_num=1)
- [ ] Trying to delete last item shows validation error

### Cost Calculations
- [ ] Cost updates on material change
- [ ] Cost updates on quantity change
- [ ] Cost shows 2 decimal places
- [ ] Total cost is sum of all items
- [ ] Deleted items excluded from total
- [ ] No negative costs
- [ ] No floating-point errors

### UI Issues
- [ ] No overlapping elements
- [ ] Form responsive on mobile
- [ ] Buttons clickable on touch devices
- [ ] Dropdowns work on mobile
- [ ] No console errors
- [ ] No broken CSS classes

### Data Integrity
- [ ] All fields saved correctly
- [ ] Related objects created properly
- [ ] Timestamps set automatically
- [ ] No orphaned items
- [ ] Foreign key constraints enforced
- [ ] Unique constraint working

---

## 🚢 Deployment Pre-Check

### Environment Setup
- [ ] Database backed up
- [ ] Django settings configured
- [ ] Static files collected
- [ ] Secret key set
- [ ] Debug mode OFF in production

### Migration Readiness
- [ ] Migration file created (0004_refactor_material_request.py)
- [ ] Migration file reviewed for correctness
- [ ] No reversions blocking migration
- [ ] Rollback plan documented

### Code Quality
- [ ] No syntax errors
- [ ] No import errors
- [ ] No circular dependencies
- [ ] All required packages installed
- [ ] No hardcoded paths or credentials

### Testing Complete
- [ ] Unit tests pass (if created)
- [ ] Integration tests pass (if created)
- [ ] Manual testing completed
- [ ] Edge cases handled
- [ ] Performance acceptable

---

## ✅ Sign-Off Checklist

### Development Team
- [ ] Code reviewed by team
- [ ] All files checked in to version control
- [ ] Git commits descriptive
- [ ] Branch ready to merge
- [ ] No merge conflicts

### QA Team
- [ ] Test plan created and executed
- [ ] All critical features verified
- [ ] Edge cases tested
- [ ] Performance benchmarks met
- [ ] Security scan passed

### Operations Team
- [ ] Deployment plan created
- [ ] Rollback procedure documented
- [ ] Monitoring setup configured
- [ ] Alerting configured
- [ ] Documentation reviewed

### Project Manager
- [ ] Scope complete
- [ ] All requirements met
- [ ] Timeline on schedule
- [ ] Budget acceptable
- [ ] Stakeholder approval obtained

---

## 📝 Final Notes

### Known Limitations
- [ ] Documented in enhancement docs
- [ ] Acceptable for current release
- [ ] Future enhancements identified
- [ ] No blocking issues

### Future Work
- [ ] Identified enhancement ideas documented
- [ ] Prioritized if applicable
- [ ] Not blocking current release
- [ ] Backlog items created

### Support Resources
- [ ] Team trained on changes
- [ ] Documentation accessible
- [ ] Support contacts identified
- [ ] Troubleshooting guide available

---

**Checklist Version:** 1.0
**Created:** Current Session
**Last Updated:** Current Session
**Status:** Ready for Deployment ✅

---

## How to Use This Checklist

1. **Before Starting:** Review each section
2. **During Development:** Check items as completed
3. **Before Testing:** Ensure all dev items checked
4. **During Testing:** Verify all test items pass
5. **Before Deployment:** Ensure all deployment items ready
6. **After Deployment:** Archive this checklist with release notes

### Sign-Off Process
Print this checklist and have appropriate team members sign off:
- [ ] Developer: _________________ Date: _______
- [ ] QA Lead: __________________ Date: _______
- [ ] Ops Lead: _________________ Date: _______
- [ ] Project Manager: __________ Date: _______
