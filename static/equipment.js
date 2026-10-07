/* Equipment uses its own records and forms, with shared spreadsheet import. */
(() => {
  let items = [], editingId = null, deletingItem = null;
  const equipmentForm = $('equipment-form');
  const fields = ['brand','model','description','serial_number','quantity','location','notes'];
  const label = field => field.replaceAll('_', ' ').replace(/^./, s => s.toUpperCase());
  const displayName = item => `${item.brand} ${item.model}`;
  async function loadEquipment() {
    $('equipment-refresh').disabled = true;
    try {
      items = (await api('/api/equipment')).equipment;
      $('equipment-error').hidden = true;
      options('equipment-location-filter', items.map(i => i.location));
      $('equipment-location-options').replaceChildren(...[...new Set(items.map(i => i.location))].map(v => new Option(v,v)));
      renderEquipment();
      return true;
    } catch(error) {
      $('equipment-error').textContent = 'Could not load equipment. ' + error.message;
      $('equipment-error').hidden = false;
      return false;
    } finally { $('equipment-refresh').disabled = false; }
  }
  function renderEquipment() {
    const query = $('equipment-search').value.trim().toLowerCase();
    const results = items.filter(item => fields.some(field => String(item[field]).toLowerCase().includes(query)) &&
      (!$('equipment-location-filter').value || item.location === $('equipment-location-filter').value));
    $('equipment-records').textContent = items.length;
    $('equipment-units').textContent = items.reduce((total,item) => total + item.quantity, 0);
    $('equipment-locations').textContent = new Set(items.map(i => i.location)).size;
    $('equipment-brands').textContent = new Set(items.map(i => i.brand)).size;
    $('equipment-result-count').textContent = results.length;
    $('equipment-showing').textContent = `${results.length} of ${items.length} inventory records`;
    $('equipment-empty').hidden = items.length > 0;
    $('equipment-no-results').hidden = !items.length || !!results.length;
    $('equipment-table').hidden = !results.length;
    $('equipment-rows').replaceChildren(...results.map(item => {
      const row = element('tr');
      fields.forEach(field => {
        const cell = element('td', '', item[field] === '' ? '—' : item[field]);
        cell.dataset.label = label(field); row.append(cell);
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
  }
  function openEquipment(item = null) {
    editingId = item?.id ?? null;
    equipmentForm.reset(); $('equipment-form-error').hidden = true;
    $('equipment-form-title').textContent = editingId ? 'Edit equipment' : 'Add equipment';
    $('save-equipment').textContent = editingId ? 'Save changes' : 'Save equipment';
    if (item) fields.forEach(field => { equipmentForm.elements[field].value = item[field]; });
    $('equipment-dialog').showModal();
  }
  equipmentForm.onsubmit = async event => {
    event.preventDefault(); $('save-equipment').disabled = true;
    $('equipment-form-error').hidden = true;
    try {
      await api(editingId ? `/api/equipment/${editingId}` : '/api/equipment', editingId ? 'PUT' : 'POST', Object.fromEntries(new FormData(equipmentForm)));
      $('equipment-dialog').close(); toast(editingId ? 'Equipment updated.' : 'Equipment added.'); await loadEquipment();
    } catch(error) { $('equipment-form-error').textContent = error.message; $('equipment-form-error').hidden = false; }
    finally { $('save-equipment').disabled = false; }
  };
  for (const id of ['close-equipment','cancel-equipment']) $(id).onclick = () => $('equipment-dialog').close();
  $('equipment-empty-add').onclick = () => openEquipment();
  $('equipment-refresh').onclick = loadEquipment;
  $('equipment-import').onclick = () => $('import-file').click();
  for (const id of ['equipment-search','equipment-location-filter']) $(id).addEventListener(id.endsWith('search') ? 'input' : 'change', renderEquipment);
  $('equipment-clear').onclick = () => { ['equipment-search','equipment-location-filter'].forEach(id => { $(id).value = ''; }); renderEquipment(); };
  $('cancel-equipment-delete').onclick = () => $('equipment-delete-dialog').close();
  $('confirm-equipment-delete').onclick = async () => {
    $('confirm-equipment-delete').disabled = true;
    try { await api(`/api/equipment/${deletingItem.id}`, 'DELETE', {}); $('equipment-delete-dialog').close(); toast('Equipment deleted.'); await loadEquipment(); }
    catch(error) { $('equipment-delete-error').textContent = error.message; $('equipment-delete-error').hidden = false; }
    finally { $('confirm-equipment-delete').disabled = false; }
  };
  window.equipmentUI = {load:loadEquipment, open:openEquipment};
})();
