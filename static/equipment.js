/* Equipment uses its own records and forms, with shared spreadsheet import. */
(() => {
  let items = [], editingId = null, deletingItem = null;
  let visibleItems = [];
  const selectedItems = new Set();
  const pendingConfirmations = new Map();
  let inventoryId = 1, inventories = [], inventoryReady = false, loadVersion = 0;
  let formInventoryId = 1, renamingInventoryId = null;
  let inventoryLoad = Promise.resolve();
  try { inventoryId = Number(localStorage.getItem('avtrack-equipment-inventory')) || 1; } catch (_) {}
  const currentInventory = () => {
    if (!inventoryReady) throw new Error('Wait for the inventory to finish loading.');
    return {...inventories.find(inventory => inventory.id === inventoryId)};
  };
  function resetEquipmentFilters(switchedInventory = false) {
    if (switchedInventory) {
      selectedItems.clear();
      $('equipment-export-scope').value = 'filtered';
    }
    ['equipment-search','equipment-location-filter','equipment-status-filter'].forEach(id => { $(id).value = ''; });
    $('equipment-status-buttons').querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.value === '')));
  }
  const equipmentForm = $('equipment-form');
  const fields = ['description','brand','model','serial_number','quantity','location','notes'];
  const label = field => field === 'description' ? 'Item' : field.replaceAll('_', ' ').replace(/^./, s => s.toUpperCase());
  const displayName = item => [item.brand, item.model].filter(Boolean).join(' ') || `record ${item.id}`;
  function updateEquipmentSelection() {
    const visibleSelected = visibleItems.filter(item => selectedItems.has(item.id)).length;
    const check = $('select-visible-equipment');
    check.disabled = !visibleItems.length;
    check.checked = !!visibleItems.length && visibleSelected === visibleItems.length;
    check.indeterminate = visibleSelected > 0 && visibleSelected < visibleItems.length;
    $('equipment-rows').querySelectorAll('.row-select').forEach(checkbox => { checkbox.checked = selectedItems.has(Number(checkbox.dataset.recordId)); });
    $('equipment-selection-summary').hidden = !selectedItems.size;
    $('equipment-selection-count').textContent = `${selectedItems.size} selected`;
    updateExportScope('equipment-export-scope', visibleItems.length, selectedItems.size, items.length);
  }
  $('select-visible-equipment').onchange = event => {
    visibleItems.forEach(item => event.target.checked ? selectedItems.add(item.id) : selectedItems.delete(item.id));
    if (selectedItems.size) $('equipment-export-scope').value = 'selected';
    updateEquipmentSelection();
  };
  $('clear-equipment-selection').onclick = () => { selectedItems.clear(); updateEquipmentSelection(); };
  function loadEquipment(targetId = inventoryId) {
    inventoryLoad = fetchEquipment(targetId);
    return inventoryLoad;
  }
  async function fetchEquipment(targetId) {
    const version = ++loadVersion, previouslyReady = inventoryReady;
    inventoryReady = false;
    $('equipment-refresh').disabled = true;
    ['equipment-inventory-select','new-equipment-inventory','rename-equipment-inventory','equipment-import'].forEach(id => { $(id).disabled = true; });
    $('equipment-rows').inert = true;
    try {
      await Promise.all([...pendingConfirmations.values()]);
      const catalog = (await api('/api/equipment/inventories')).inventories;
      const target = catalog.find(inventory => inventory.id === targetId) || catalog.find(inventory => inventory.id === 1);
      const records = (await api(`/api/equipment?inventory_id=${target.id}`)).equipment;
      if (version !== loadVersion) return false;
      if (inventoryId !== target.id) resetEquipmentFilters(true);
      inventoryId = target.id; inventories = catalog; items = records; inventoryReady = true;
      $('equipment-inventory-select').replaceChildren(...catalog.map(inventory => new Option(inventory.name, inventory.id)));
      $('equipment-inventory-select').value = String(inventoryId);
      $('equipment-inventory-title').textContent = target.name;
      try { localStorage.setItem('avtrack-equipment-inventory', inventoryId); } catch (_) {}
      $('equipment-error').hidden = true;
      options('equipment-location-filter', items.map(i => i.location));
      $('equipment-location-options').replaceChildren(...[...new Set(items.map(i => i.location))].map(v => new Option(v,v)));
      renderEquipment();
      await loadOverview();
      return true;
    } catch(error) {
      if (version !== loadVersion) return false;
      inventoryReady = previouslyReady;
      $('equipment-inventory-select').value = String(inventoryId);
      $('equipment-error').textContent = 'Could not load equipment. ' + error.message;
      $('equipment-error').hidden = false;
      return false;
    } finally {
      if (version === loadVersion) {
        $('equipment-refresh').disabled = false;
        ['equipment-inventory-select','new-equipment-inventory','rename-equipment-inventory','equipment-import'].forEach(id => { $(id).disabled = !inventoryReady; });
        $('equipment-rows').inert = !inventoryReady;
      }
    }
  }
  function renderEquipment() {
    updatePageSummary(items, inventories.find(inventory => inventory.id === inventoryId)?.name || 'Equipment inventory');

    renderLocationButtons();
    const query = $('equipment-search').value.trim().toLowerCase();
    const results = items.filter(item => fields.some(field => String(item[field] ?? '').toLowerCase().includes(query)) &&
      (!$('equipment-location-filter').value || item.location === $('equipment-location-filter').value) &&
      (!$('equipment-status-filter').value || Boolean(item.item_confirmed) === ($('equipment-status-filter').value === 'found')));
    visibleItems = results;
    const availableIds = new Set(results.map(item => item.id));
    for (const id of selectedItems) if (!availableIds.has(id)) selectedItems.delete(id);
    $('equipment-records').textContent = items.length;
    $('equipment-units').textContent = items.reduce((total,item) => total + (item.quantity ?? 0), 0);
    $('equipment-units').title = 'Sum of known quantities; blank quantities are not counted.';
    $('equipment-locations').textContent = new Set(items.map(i => i.location).filter(Boolean)).size;
    $('equipment-found').textContent = items.filter(item => item.item_confirmed).length;
    $('equipment-result-count').textContent = results.length;
    $('equipment-showing').textContent = `${results.length} of ${items.length} items · ${results.filter(item => item.item_confirmed).length} located in this view`;
    $('equipment-empty').hidden = items.length > 0;
    $('equipment-no-results').hidden = !items.length || !!results.length;
    $('equipment-table').hidden = !results.length;
    $('equipment-rows').replaceChildren(...results.map(item => {
      const row = element('tr');
      row.dataset.itemId = item.id;
      fields.forEach(field => {
        const cell = element('td', '', item[field] ?? '');
        if (field === 'description') {
          const value = element('div', 'equipment-brand-value');
          value.append(selectionControl(item.id, `equipment ${displayName(item)}`, selectedItems, () => {
            if (selectedItems.size) $('equipment-export-scope').value = 'selected';
            updateEquipmentSelection();
          }), element('span', '', item[field] ?? ''));
          cell.replaceChildren(value);
        }
        cell.dataset.label = label(field); row.append(cell);
        if (field === 'location') {
          const status = element('td', 'equipment-status'); status.dataset.label = 'Located';
          const control = element('label', `equipment-confirm-label${item.item_confirmed ? ' confirmed' : ''}`);
          const check = element('input', 'equipment-confirm'); check.type = 'checkbox';
          check.checked = Boolean(item.item_confirmed); check.disabled = pendingConfirmations.has(item.id);
          check.setAttribute('aria-label', `Mark equipment ${displayName(item)} as located`);
          control.append(check, element('span', '', item.item_confirmed ? 'Located' : 'Not located'));
          check.onchange = async () => {
            const write = api(`/api/equipment/${item.id}/confirm`, 'POST', {...item, item_confirmed:check.checked});
            pendingConfirmations.set(item.id, write); check.disabled = true;
            try {
              const updated = await write;
              items = items.map(record => record.id === updated.id ? updated : record);
            } catch(error) { toast('Could not update located status: ' + error.message); }
            finally { pendingConfirmations.delete(item.id); renderEquipment(); }
          };
          status.append(control); row.append(status);
        }
      });
      const actions = element('td', 'equipment-actions'); actions.dataset.label = 'Actions';
      const edit = element('button', 'quiet', 'Edit'); edit.setAttribute('aria-label', `Edit equipment ${displayName(item)}`); edit.onclick = () => openEquipment(item);
      const remove = element('button', 'quiet', 'Delete'); remove.setAttribute('aria-label', `Delete equipment ${displayName(item)}`);
      remove.onclick = () => {
        deletingItem = item;
        $('equipment-delete-description').textContent = `${displayName(item)} · Quantity ${item.quantity} · ${item.location}`;
        $('equipment-delete-error').hidden = true;
        $('equipment-delete-dialog').showModal(); $('cancel-equipment-delete').focus();
      };
      actions.append(edit,remove); row.append(actions); return row;
    }));
    updateEquipmentSelection();
  }
  const locations = () => [...new Set(items.map(i => i.location).filter(Boolean))].sort(nameCollator.compare);
  function renderLocationButtons() {
    const selected = $('equipment-location-filter').value;
    $('equipment-manage-locations').disabled = !inventoryReady || !locations().length;
    $('equipment-location-buttons').replaceChildren(...['', ...locations()].map(location => {
      const button = element('button', 'choice-button', location || 'All locations');
      button.type = 'button'; button.setAttribute('aria-pressed', String(selected === location));
      if (location) colorVenueButton(button, location);
      button.onclick = () => { $('equipment-location-filter').value = location; renderEquipment(); };
      return button;
    }));
  }
  function updateLocationAction() {
    const source = $('equipment-location-source').value;
    const previous = $('equipment-location-target').value;
    $('equipment-location-target').replaceChildren(...locations().filter(value => value !== source).map(value => new Option(value, value)));
    if (locations().includes(previous) && previous !== source) $('equipment-location-target').value = previous;
    const merging = $('equipment-location-action').value === 'merge';
    $('equipment-location-target-label').hidden = !merging;
    $('equipment-location-target').required = merging;
    const count = items.filter(item => item.location === source).length;
    $('equipment-location-impact').textContent = `${count} equipment record${count === 1 ? '' : 's'} will ${merging ? 'move to the destination location' : 'have their location cleared'}.`;
    $('save-equipment-locations').textContent = merging ? 'Merge location' : 'Delete location label';
    $('save-equipment-locations').disabled = !source || (merging && !$('equipment-location-target').value);
    $('equipment-location-error').hidden = true;
  }
  $('equipment-manage-locations').onclick = () => {
    currentInventory();
    $('equipment-location-source').replaceChildren(...locations().map(value => new Option(value, value)));
    if ($('equipment-location-filter').value) $('equipment-location-source').value = $('equipment-location-filter').value;
    $('equipment-location-action').value = locations().length > 1 ? 'merge' : 'delete';
    updateLocationAction(); $('equipment-location-dialog').showModal();
  };
  for (const id of ['equipment-location-source', 'equipment-location-action']) $(id).onchange = updateLocationAction;
  for (const id of ['close-equipment-locations', 'cancel-equipment-locations']) $(id).onclick = () => $('equipment-location-dialog').close();
  $('equipment-location-form').onsubmit = async event => {
    event.preventDefault(); $('save-equipment-locations').disabled = true;
    try {
      await inventoryLoad;
      const result = await api('/api/equipment/locations', 'POST', {
        inventory_id: currentInventory().id,
        source: $('equipment-location-source').value, action: $('equipment-location-action').value,
        target: $('equipment-location-target').value
      });
      $('equipment-location-filter').value = '';
      $('equipment-location-dialog').close(); toast(`Updated ${result.updated} equipment records.`); await loadEquipment();
    } catch(error) { $('equipment-location-error').textContent = error.message; $('equipment-location-error').hidden = false; }
    finally { $('save-equipment-locations').disabled = false; }
  };
  function openEquipment(item = null) {
    if (!inventoryReady) { toast('Wait for the inventory to finish loading.'); return; }
    formInventoryId = item?.inventory_id ?? inventoryId;
    editingId = item?.id ?? null;
    equipmentForm.reset(); $('equipment-form-error').hidden = true;
    $('equipment-form-title').textContent = editingId ? 'Edit equipment' : 'Add equipment';
    $('save-equipment').textContent = editingId ? 'Save changes' : 'Save equipment';
    if (item) fields.forEach(field => { equipmentForm.elements[field].value = item[field] ?? ''; });
    $('equipment-dialog').showModal();
  }
  equipmentForm.onsubmit = async event => {
    event.preventDefault(); $('save-equipment').disabled = true;
    $('equipment-form-error').hidden = true;
    try {
      await api(editingId ? `/api/equipment/${editingId}` : '/api/equipment', editingId ? 'PUT' : 'POST', {...Object.fromEntries(new FormData(equipmentForm)), inventory_id:formInventoryId});
      $('equipment-dialog').close(); toast(editingId ? 'Equipment updated.' : 'Equipment added.'); await loadEquipment();
    } catch(error) { $('equipment-form-error').textContent = error.message; $('equipment-form-error').hidden = false; }
    finally { $('save-equipment').disabled = false; }
  };
  for (const id of ['close-equipment','cancel-equipment']) $(id).onclick = () => $('equipment-dialog').close();
  $('equipment-empty-add').onclick = () => openEquipment();
  $('equipment-refresh').onclick = () => loadEquipment();
  $('equipment-inventory-select').onchange = event => loadEquipment(Number(event.target.value));
  function openInventoryForm(rename = false) {
    if (!inventoryReady) return;
    renamingInventoryId = rename ? inventoryId : null;
    $('equipment-inventory-form').reset();
    $('equipment-inventory-name').value = rename ? currentInventory().name : '';
    $('equipment-inventory-form-title').textContent = rename ? 'Rename inventory' : 'New inventory';
    $('save-equipment-inventory').textContent = rename ? 'Save name' : 'Create inventory';
    $('equipment-inventory-form-error').hidden = true;
    $('equipment-inventory-dialog').showModal(); $('equipment-inventory-name').focus();
  }
  $('new-equipment-inventory').onclick = () => openInventoryForm();
  $('rename-equipment-inventory').onclick = () => openInventoryForm(true);
  for (const id of ['close-equipment-inventory','cancel-equipment-inventory']) $(id).onclick = () => $('equipment-inventory-dialog').close();
  $('equipment-inventory-form').onsubmit = async event => {
    event.preventDefault(); $('save-equipment-inventory').disabled = true;
    $('equipment-inventory-form-error').hidden = true;
    try {
      const inventory = await api(renamingInventoryId ? `/api/equipment/inventories/${renamingInventoryId}` : '/api/equipment/inventories', renamingInventoryId ? 'PUT' : 'POST', {name:$('equipment-inventory-name').value});
      $('equipment-inventory-dialog').close();
      await loadEquipment(inventory.id);
      toast(renamingInventoryId ? 'Inventory renamed.' : 'Inventory created. Import a file or add items.');
    } catch(error) { $('equipment-inventory-form-error').textContent = error.message; $('equipment-inventory-form-error').hidden = false; }
    finally { $('save-equipment-inventory').disabled = false; }
  };
  $('equipment-import').onclick = () => $('import-file').click();
  for (const id of ['equipment-search','equipment-location-filter']) $(id).addEventListener(id.endsWith('search') ? 'input' : 'change', renderEquipment);
  for (const [value, text] of [['','All items'], ['pending','Not located'], ['found','Located']]) {
    const button = element('button', 'choice-button', text); button.type = 'button';
    button.dataset.value = value; button.setAttribute('aria-pressed', String(value === ''));
    button.onclick = () => {
      $('equipment-status-filter').value = value;
      $('equipment-status-buttons').querySelectorAll('button').forEach(choice => choice.setAttribute('aria-pressed', String(choice === button)));
      renderEquipment();
    };
    $('equipment-status-buttons').append(button);
  }
  $('equipment-clear').onclick = () => {
    resetEquipmentFilters();
    renderEquipment();
  };
  $('cancel-equipment-delete').onclick = () => $('equipment-delete-dialog').close();
  $('confirm-equipment-delete').onclick = async () => {
    $('confirm-equipment-delete').disabled = true;
    try { await api(`/api/equipment/${deletingItem.id}`, 'DELETE', {inventory_id:deletingItem.inventory_id}); $('equipment-delete-dialog').close(); toast('Equipment deleted.'); await loadEquipment(); }
    catch(error) { $('equipment-delete-error').textContent = error.message; $('equipment-delete-error').hidden = false; }
    finally { $('confirm-equipment-delete').disabled = false; }
  };
  window.equipmentUI = {load:loadEquipment, open:openEquipment,
    currentInventory,
    waitUntilReady:async () => { await inventoryLoad; return currentInventory(); },
    flush:() => Promise.all([...pendingConfirmations.values()]),
    exportData:scope => {
      const inventory = currentInventory();
      const records = scope === 'all' ? items : scope === 'selected' ? visibleItems.filter(item => selectedItems.has(item.id)) : visibleItems;
      return {inventory_id:inventory.id, ids:records.map(item => item.id), name:inventory.name};
    }};
})();
