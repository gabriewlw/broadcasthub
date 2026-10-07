'use strict';
const $ = id => document.getElementById(id);
let devices = [], editing = null, deleting = null, timer, currentTab = 'device';
let importWarnings = [];
const pendingNoteSaves = new Map();
const pendingWrites = new Set();
const tabSortOrders = {device: '', iptv: ''};
const nameCollator = new Intl.Collator(undefined, {sensitivity: 'base', numeric: true});
const tabDevices = () => devices.filter(d => (d.record_type || 'device') === currentTab);
const form = $('device-form');
const filters = ['search', 'venue-filter', 'system-filter', 'category-filter', 'source-filter', 'address-filter'];
const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const systems = ['Video', 'Audio', 'Lighting', 'Control', 'Network', 'Other'];
const deviceLabel = device => device.name || `record ${device.id}`;
const isDHCP = value => value.trim().toUpperCase() === 'DHCP';
function compareDirectoryRecords(a, b, order) {
  const [field, direction] = order.split('-');
  const sign = direction === 'desc' ? -1 : 1;
  let comparison = 0;
  if (field === 'ip') {
    const number = ip => /^(?:\d{1,3}\.){3}\d{1,3}$/.test(ip) && ip.split('.').every(octet => Number(octet) <= 255)
      ? ip.split('.').reduce((value, octet) => value * 256 + Number(octet), 0) : null;
    const left = number(a.ip), right = number(b.ip);
    // Static IPv4 addresses first, DHCP next, blank addresses last in either direction.
    const group = (record, value) => value !== null ? 0 : isDHCP(record.ip) ? 1 : 2;
    const grouping = group(a, left) - group(b, right);
    if (grouping) return grouping;
    if (left !== null && right !== null) comparison = left - right;
  } else {
    const key = field === 'system' ? (currentTab === 'iptv' ? 'channel_source' : 'discipline') : 'name';
    const left = (a[key] || '').trim(), right = (b[key] || '').trim();
    if (!left !== !right) return left ? -1 : 1;
    comparison = nameCollator.compare(left, right);
  }
  return comparison * sign || nameCollator.compare(a.name, b.name) || a.id - b.id;
}

let activeSystemMenu = null;
function closeSystemMenu(restoreFocus = false) {
  if (!activeSystemMenu) return;
  const {menu, button} = activeSystemMenu;
  activeSystemMenu = null; menu.remove(); button.setAttribute('aria-expanded', 'false');
  if (restoreFocus) button.focus();
}
document.addEventListener('pointerdown', event => {
  if (activeSystemMenu && !activeSystemMenu.menu.contains(event.target) && !activeSystemMenu.button.contains(event.target)) closeSystemMenu();
});
window.addEventListener('resize', () => activeSystemMenu?.position());
document.addEventListener('scroll', event => {
  if (activeSystemMenu && !activeSystemMenu.menu.contains(event.target)) activeSystemMenu.position();
}, true);
function systemDropdown(device) {
  const button = element('button', 'system-select system-tag');
  button.type = 'button'; button.dataset.value = device.discipline;
  button.setAttribute('role', 'combobox');
  button.setAttribute('aria-label', `System for ${deviceLabel(device)}`);
  button.setAttribute('aria-haspopup', 'listbox'); button.setAttribute('aria-expanded', 'false');
  button.setAttribute('aria-controls', `system-menu-${device.id}`);
  const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  arrow.classList.add('system-arrow'); arrow.setAttribute('viewBox', '0 0 12 12');
  arrow.setAttribute('aria-hidden', 'true'); arrow.setAttribute('focusable', 'false');
  const chevron = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  chevron.setAttribute('d', 'M3 4.5 6 7.5 9 4.5'); arrow.append(chevron);
  button.append(element('span', '', device.discipline), arrow);
  const open = (last = false) => {
    closeSystemMenu();
    const menu = element('div', 'system-options'); menu.id = `system-menu-${device.id}`;
    menu.setAttribute('role', 'listbox'); menu.setAttribute('aria-label', `Choose system for ${deviceLabel(device)}`);
    const choices = ['', ...systems].map(value => {
      const option = element('button', 'system-option system-tag', value || 'Clear system');
      option.type = 'button'; option.dataset.value = value; option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', String(value === device.discipline));
      option.onclick = async () => {
        closeSystemMenu(true); button.disabled = true;
        try {
          const updated = await api(`/api/devices/${device.id}/system`, 'POST', {discipline:value});
          devices = devices.map(row => row.id === updated.id ? {...row,discipline:updated.discipline} : row);
          updateFilterOptions(); render();
          document.querySelector(`.system-select[aria-controls="system-menu-${device.id}"]`)?.focus();
        } catch(error) { button.disabled = false; toast('Could not save system: ' + error.message); }
      };
      return option;
    });
    menu.append(...choices); document.body.append(menu);
    const position = () => {
      const rect = button.getBoundingClientRect(), width = Math.min(190, window.innerWidth - 16);
      menu.style.width = `${width}px`;
      menu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`;
      const height = Math.min(menu.scrollHeight, window.innerHeight - 16);
      menu.style.top = `${Math.max(8, rect.bottom + height + 8 <= window.innerHeight ? rect.bottom + 4 : rect.top - height - 4)}px`;
      menu.style.maxHeight = `${window.innerHeight - 16}px`;
    };
    activeSystemMenu = {menu, button, position}; position(); button.setAttribute('aria-expanded', 'true');
    const selected = choices.find(option => option.dataset.value === device.discipline);
    (last ? choices.at(-1) : selected || choices[0]).focus();
    menu.onkeydown = event => {
      const index = choices.indexOf(document.activeElement);
      if (event.key === 'Escape') { event.preventDefault(); closeSystemMenu(true); }
      else if (event.key === 'Tab') closeSystemMenu(true);
      else if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
        event.preventDefault();
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? choices.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : choices.length - 1)) % choices.length;
        choices[next].focus();
      }
    };
  };
  button.onclick = () => activeSystemMenu?.button === button ? closeSystemMenu() : open();
  button.onkeydown = event => {
    if (['ArrowDown','ArrowUp'].includes(event.key)) { event.preventDefault(); open(event.key === 'ArrowUp'); }
    else if (event.key === 'Escape') closeSystemMenu(true);
  };
  return button;
}
async function saveNotes(deviceId, notes) {
  const previous = pendingNoteSaves.get(deviceId) || Promise.resolve();
  const request = previous.catch(() => {}).then(() => api(`/api/devices/${deviceId}/notes`, 'POST', {notes}));
  pendingNoteSaves.set(deviceId, request);
  try { return await request; }
  finally { if (pendingNoteSaves.get(deviceId) === request) pendingNoteSaves.delete(deviceId); }
}
const cleanVenue = value => value.trim().replace(/^RD\s+/i, '').trim();
const venueColors = new Map();
const usedVenueColors = new Set();
function colorVenueButton(button, venue) {
  if (!venue) return;
  if (!venueColors.has(venue)) {
    let hash = 2166136261;
    for (const character of venue) hash = Math.imul(hash ^ character.codePointAt(0), 16777619) >>> 0;
    let hue = hash % 360;
    const saturation = 60 + (hash >>> 8) % 16, lightness = 65 + (hash >>> 16) % 10;
    let color = `hsl(${hue} ${saturation}% ${lightness}%)`;
    while (usedVenueColors.has(color)) {
      hue += 0.1;
      color = `hsl(${hue} ${saturation}% ${lightness}%)`;
    }
    venueColors.set(venue, color);
    usedVenueColors.add(color);
  }
  button.classList.add('venue-choice');
  button.style.setProperty('--venue-color', venueColors.get(venue));
}
// IDs preserve first appearance across imports even when the device list is sorted.
const savedVenues = () => [...new Set(tabDevices().slice().sort((a,b) => a.id-b.id).map(d => cleanVenue(d.venue)).filter(Boolean))];
function makeButtons(id, values, selected, onSelect, allLabel = null) {
  const choices = allLabel ? [['', allLabel], ...values.map(v => [v, v])] : values.map(v => [v, v]);
  $(id).replaceChildren(...choices.map(([value, label]) => {
    const button = element('button', 'choice-button', label);
    button.type = 'button';
    button.dataset.value = value;
    if (['venue-buttons', 'form-venue-buttons'].includes(id)) colorVenueButton(button, value);
    button.setAttribute('aria-pressed', String(value === selected));
    button.onclick = () => onSelect(value);
    return button;
  }));
}
function syncButtons(id, value) {
  $(id).querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.value === value)));
}
function updateVenueButtons() {
  const venues = savedVenues();
  if (!venues.includes($('venue-filter').value)) $('venue-filter').value = '';
  makeButtons('venue-buttons', venues, $('venue-filter').value, value => { $('venue-filter').value = value; render(); }, 'All venues');
}
makeButtons('system-buttons', systems, '', value => { $('system-filter').value = value; render(); }, 'All systems');
makeButtons('source-buttons', ['Onboard','Satellite'], '', value => { $('source-filter').value = value; render(); }, 'All sources');
makeButtons('address-buttons', ['DHCP'], '', value => { $('address-filter').value = value; render(); }, 'All addresses');
makeButtons('form-source-buttons', ['Onboard','Satellite'], '', value => { form.elements.channel_source.value = form.elements.channel_source.value === value ? '' : value; syncButtons('form-source-buttons', form.elements.channel_source.value); });
function updateFilterOptions() {
  updateVenueButtons();
  options('category-filter', tabDevices().map(d => d.category));
  $('venues').replaceChildren(...savedVenues().map(v => new Option(v, v)));
}
function switchTab(type) {
  closeSystemMenu();
  closeExportMenus();
  currentTab = type;
  const equipment = type === 'equipment';
  $('nav-transfer').href = equipment ? '#equipment-transfer' : '#transfer';
  $('equipment-panel').hidden = !equipment;
  $('inventory').hidden = equipment;
  document.querySelector('main > .stats').hidden = equipment;
  for (const [id, tab] of [['device-tab','device'], ['iptv-tab','iptv'], ['equipment-tab','equipment']]) {
    $(id).setAttribute('aria-selected', String(tab === type)); $(id).tabIndex = tab === type ? 0 : -1;
  }
  if (equipment) {
    $('hero-title').replaceChildren(document.createTextNode('Every asset.'), element('br'), document.createTextNode('Every location.'), element('br'), element('span', '', 'One clear view.'));
    $('hero-intro').textContent = 'Manage your broadcast equipment, spare stock, and production tools. Keep brands, models, serial numbers, and quantities organized from the control room to the storeroom.';
    $('example-ip').textContent = 'ATEM Mini Pro'; $('example-name').textContent = 'Blackmagic Design';
    $('example-tags').replaceChildren(...['Video switcher','Quantity 1','Broadcast center'].map(text => element('span','',text)));
    $('add-device').textContent = 'Add equipment'; $('validation-note').hidden = true;
    window.equipmentUI.load(); return;
  }
  filters.forEach(id => $(id).value = '');
  for (const [id, tab] of [['device-tab','device'], ['iptv-tab','iptv']]) {
    $(id).setAttribute('aria-selected', String(tab === type));
    $(id).tabIndex = tab === type ? 0 : -1;
  }
  $('inventory').setAttribute('aria-labelledby', type === 'iptv' ? 'iptv-tab' : 'device-tab');
  const iptv = type === 'iptv';
  $('sort-order').value = tabSortOrders[type];
  for (const direction of ['asc', 'desc']) {
    $('sort-order').querySelector(`option[value="system-${direction}"]`).textContent = `${iptv ? 'Source' : 'System'} · ${direction === 'asc' ? 'A–Z' : 'Z–A'}`;
  }

  $('hero-title').replaceChildren(document.createTextNode(iptv ? 'Every channel.' : 'Every device.'), element('br'), document.createTextNode(iptv ? 'Every source.' : 'Every venue.'), element('br'), element('span', '', 'One clear view.'));
  $('hero-intro').textContent = iptv ? 'Keep your onboard and satellite channel lineup in view. Track stream addresses and ports, organize channels by source, and take your inventory from the control room to your phone.' : 'Manage your broadcast equipment, channel lineups, and AV connections. Keep your production workspace organized from the control room to your phone.';
  $('example-ip').textContent = iptv ? '239.1.1.10' : '10.24.176.66';
  $('example-name').textContent = iptv ? 'Ship information' : 'ATEM video switcher';
  $('example-tags').replaceChildren(...(iptv ? ['Onboard', 'Port 1234'] : ['Liquid Lounge', 'Video', 'VLAN 1500']).map(text => element('span', '', text)));

  $('add-device').textContent = iptv ? 'Add channel' : 'Add device';
  $('empty-add').textContent = iptv ? 'Add a channel' : 'Add a device';
  $('empty-title').textContent = iptv ? 'Your channel lineup starts here' : 'Your inventory starts here';
  $('empty-description').textContent = iptv ? 'Add onboard and satellite channel addresses to your IPTV inventory.' : 'Add your first device to keep your ship’s AV network organized.';
  $('use-example').hidden = iptv;
  $('total-label').textContent = iptv ? 'Total channels' : 'Total devices';
  $('system-count-label').textContent = iptv ? 'Onboard / Satellite' : 'Video / Audio / Lighting';
  $('list-title').textContent = iptv ? 'IPTV channels' : 'All devices';
  $('search').placeholder = iptv ? 'Channel, IP, port, or notes…' : 'Name, IP, venue, or notes…';
  $('system-filter-group').hidden = $('category-filter-label').hidden = iptv;
  $('source-filter-group').hidden = !iptv;
  for (const id of ['venue-filter-group','venue-stat','vlan-stat','validation-note']) $(id).hidden = iptv;
  document.querySelector('.stats').classList.toggle('iptv-stats', iptv);
  $('confirmation-legend').textContent = iptv ? 'Channel addresses and stream ports · Onboard / Satellite' : 'Yellow: awaiting confirmation · Green: manually confirmed';
  updateFilterOptions(); render();
}
const inventoryTabs = [['device-tab','device'],['iptv-tab','iptv'],['equipment-tab','equipment']];
for (const [id, type] of inventoryTabs) {
  $(id).onclick = () => switchTab(type);
  $(id).onkeydown = event => {
    if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
      event.preventDefault();
      const index = inventoryTabs.findIndex(([,tab]) => tab === currentTab);
      const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (index + (event.key === 'ArrowRight' ? 1 : 2)) % 3;
      const [nextId,next] = inventoryTabs[nextIndex]; switchTab(next); $(nextId).focus();
    }
  };
}
function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(timer); timer = setTimeout(() => { $('toast').hidden = true; }, 6000);
}
async function api(path, method = 'GET', body) {
  const options = {method, headers: {'Content-Type': 'application/json'}};
  if (body !== undefined) options.body = JSON.stringify(body);
  const request = (async () => {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed. Please try again.');
    return data;
  })();
  if (method !== 'GET') pendingWrites.add(request);
  try { return await request; }
  finally { pendingWrites.delete(request); }
}
function closeExportMenus(restoreFocus = false) {
  document.querySelectorAll('.export-dropdown[open]').forEach(menu => {
    menu.open = false;
    if (restoreFocus && menu.contains(document.activeElement)) menu.querySelector('summary').focus();
  });
}
document.querySelectorAll('.export-dropdown').forEach(menu => {
  menu.addEventListener('toggle', () => {
    if (menu.open) document.querySelectorAll('.export-dropdown').forEach(other => { if (other !== menu) other.open = false; });
  });
  menu.addEventListener('click', event => {
    if (event.target.closest('a[download]')) { menu.open = false; menu.querySelector('summary').focus(); }
  });
});
document.addEventListener('pointerdown', event => {
  if (!event.target.closest('.export-dropdown')) closeExportMenus();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.querySelector('.export-dropdown[open]')) {
    event.preventDefault(); closeExportMenus(true);
  }
});
document.querySelectorAll('.report-download').forEach(link => {
  link.addEventListener('click', async event => {
    event.preventDefault();
    if (link.getAttribute('aria-disabled') === 'true') return;
    link.setAttribute('aria-disabled', 'true');
    try {
      // A download immediately after a note edit must include that saved note.
      if (document.activeElement?.matches('.device-notes-editor')) document.activeElement.blur();
      await Promise.all([...pendingNoteSaves.values(), ...pendingWrites]);
      const response = await fetch(link.href);
      if (!response.ok) throw new Error((await response.json()).error || 'Could not export inventory.');
      const url = URL.createObjectURL(await response.blob());
      const download = element('a'); download.href = url; download.download = link.download;
      document.body.append(download); download.click(); download.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch(error) { toast('Export failed: ' + error.message); }
    finally { link.removeAttribute('aria-disabled'); }
  });
});
function options(id, values) {
  const select = $(id), previous = select.value;
  while (select.options.length > 1) select.remove(1);
  [...new Set(values.filter(v => v !== null && v !== undefined && v !== ''))].sort((a,b) => typeof a === 'number' ? a-b : a.localeCompare(b)).forEach(value => select.add(new Option(value, value)));
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}
async function load() {
  if (currentTab === 'equipment') return window.equipmentUI.load();
  $('refresh').disabled = true;
  try {
    devices = (await api('/api/devices')).devices;
    $('load-error').hidden = true;
    updateFilterOptions();
    $('venues').replaceChildren(...savedVenues().map(v => new Option(v, v)));
    render();
    return true;
  } catch (error) {
    $('load-error').textContent = 'Could not refresh inventory. ' + error.message;
    $('load-error').hidden = false;
    return false;
  } finally { $('loading').hidden = true; $('refresh').disabled = false; }
}
function render() {
  closeSystemMenu();
  const iptvDirectory = currentTab === 'iptv';
  $('device-directory').classList.toggle('iptv-directory', iptvDirectory);
  $('directory-venue-title').hidden = iptvDirectory;
  $('directory-vlan-title').hidden = iptvDirectory;
  $('directory-device-title').textContent = iptvDirectory ? 'CHANNEL' : 'DEVICE';
  $('directory-system-title').textContent = iptvDirectory ? 'SOURCE' : 'SYSTEM';
  syncButtons('venue-buttons', $('venue-filter').value);
  syncButtons('system-buttons', $('system-filter').value);
  syncButtons('source-buttons', $('source-filter').value);
  syncButtons('address-buttons', $('address-filter').value);
  const current = tabDevices();
  const hasDHCP = current.some(d => isDHCP(d.ip));
  $('address-filter-group').hidden = !hasDHCP;
  if (!hasDHCP) $('address-filter').value = '';
  $('total').textContent = current.length;
  $('venue-count').textContent = savedVenues().length;
  $('vlan-count').textContent = new Set(current.map(d => d.vlan).filter(v => v !== null)).size;
  $('system-count').textContent = (currentTab === 'iptv' ? ['Onboard','Satellite'].map(source => current.filter(d => d.channel_source === source).length) : ['Video','Audio','Lighting'].map(system => current.filter(d => d.discipline === system).length)).join(' / ');
  const query = $('search').value.trim().toLowerCase();
  const results = current.filter(d =>
    [d.name,d.ip,d.venue,d.category,d.discipline,d.notes,d.channel_source || '',String(d.vlan || ''), String(d.port || '')].some(v => v.toLowerCase().includes(query)) &&
    (!$('venue-filter').value || cleanVenue(d.venue) === $('venue-filter').value) &&
    (!$('system-filter').value || d.discipline === $('system-filter').value) &&
    (!$('category-filter').value || d.category === $('category-filter').value) &&
    (!$('source-filter').value || d.channel_source === $('source-filter').value) &&
    (!$('address-filter').value || isDHCP(d.ip)));
  if ($('sort-order').value) results.sort((a, b) => compareDirectoryRecords(a, b, $('sort-order').value));
  $('result-count').textContent = results.length;
  $('showing').textContent = `${results.length} of ${current.length} ${currentTab === 'iptv' ? 'channels' : 'devices'}`;
  $('empty').hidden = current.length > 0;
  $('no-results').hidden = current.length === 0 || results.length > 0;
  const rows = results.map(device => {
    const row = element('article', 'device-row');
    const identity = element('div', 'device-identity identity-cell');
    const title = element('div');
    title.append(element('div', 'device-name', device.name), element('span', 'device-category', device.category));
    const notes = element('textarea', 'device-notes-editor');
    notes.rows = 1; notes.maxLength = 2000; notes.value = device.notes;
    notes.dataset.deviceId = device.id;
    notes.setAttribute('aria-label', `Notes for ${deviceLabel(device)}`);
    notes.title = 'Notes save when you leave this field.';
    notes.onchange = async () => {
      const draft = notes.value;
      const previous = devices.find(row => row.id === device.id)?.notes || '';
      devices = devices.map(row => row.id === device.id ? {...row,notes:draft} : row);
      try {
        const updated = await saveNotes(device.id, draft);
        // Keep the current field and focus; update only notes in case another edit ran too.
        devices = devices.map(row => row.id === updated.id && row.notes === draft ? {...row,notes:updated.notes} : row);
        const currentField = document.querySelector(`.device-notes-editor[data-device-id="${device.id}"]`);
        if (currentField?.value === draft) currentField.value = updated.notes;
      } catch(error) {
        devices = devices.map(row => row.id === device.id && row.notes === draft ? {...row,notes:previous} : row);
        toast('Could not save notes: ' + error.message);
      }
    };
    const notesCell = element('div', 'notes-cell');
    notesCell.append(notes);
    identity.append(title);
    const ip = element('div', 'ip-cell');
    const iptv = device.record_type === 'iptv';
    if (iptv) row.classList.add('iptv-row');
    const ipLine = element('div', 'ip-info-line');
    ipLine.append(element('div', 'device-ip', device.ip));
    ip.append(ipLine, element('span', 'cell-caption', iptv ? (device.port ? `Port ${device.port}` : '') : ''));
    const confirmation = element('button', `ip-confirm ${device.ip_confirmed ? 'confirmed' : 'pending'}`, device.ip_confirmed ? '✓ IP confirmed' : '● Confirm IP');
    confirmation.type = 'button';
    confirmation.disabled = Boolean(device.ip_confirmed);
    confirmation.setAttribute('aria-label', `${device.ip_confirmed ? 'IP confirmed for' : 'Confirm IP for'} ${deviceLabel(device)}`);
    confirmation.title = device.ip_confirmed ? 'Manually confirmed. This is not a reachability test.' : 'Click to manually confirm this IP assignment.';
    confirmation.onclick = async () => {
      confirmation.disabled = true;
      try {
        const updated = await api(`/api/devices/${device.id}/confirm`, 'POST', {ip:device.ip, vlan:device.vlan});
        devices = devices.map(row => row.id === updated.id ? {...row,ip_confirmed:updated.ip_confirmed} : row);
        render(); toast('IP assignment confirmed.');
      } catch(error) { confirmation.disabled = false; toast('Confirmation failed: ' + error.message); }
    };
    if (!iptv && device.ip && !isDHCP(device.ip)) ipLine.append(confirmation);
    const venue = element('div', 'venue-cell');
    const venueName = cleanVenue(device.venue);
    const venueLabel = element(venueName ? 'button' : 'div', 'device-venue', venueName);
    if (venueName) {
      venueLabel.type = 'button'; venueLabel.classList.add('choice-button');
      colorVenueButton(venueLabel, venueName);
      venueLabel.setAttribute('aria-label', `Filter venue ${venueName}`);
      venueLabel.onclick = () => { $('venue-filter').value = venueName; render(); };
    }
    venue.append(venueLabel);
    const system = element('div','system-cell');
    if (iptv) {
      if (device.channel_source) system.append(element('span', `badge ${device.discipline.toLowerCase()}`, device.channel_source));
    } else {
      system.append(systemDropdown(device));
    }
    const actions = element('div', 'row-actions');
    const edit = element('button', 'quiet', 'Edit'); edit.setAttribute('aria-label', `Edit ${deviceLabel(device)}`); edit.onclick = () => openForm(device);
    const remove = element('button', 'quiet', 'Delete'); remove.setAttribute('aria-label', `Delete ${deviceLabel(device)}`);
    remove.onclick = () => { deleting = device; $('delete-description').textContent = `${device.name} · ${device.ip} · ${iptv ? 'Port ' + (device.port || 'not set') : 'VLAN ' + device.vlan}`; $('delete-error').hidden = true; $('delete-dialog').showModal(); $('cancel-delete').focus(); };
    actions.append(edit,remove);
    if (!iptv) row.append(venue);
    row.append(identity,ip);
    if (!iptv) row.append(element('div', 'vlan-cell', device.vlan ?? ''));
    row.append(system,notesCell,actions); return row;
  });
  $('device-list').replaceChildren(...rows);
  renderImportWarnings();
}
function renderImportWarnings() {
  const duplicates = new Map();
  devices.filter(d => (d.record_type || 'device') === 'device' && d.ip && !isDHCP(d.ip)).forEach(d => {
    if (!duplicates.has(d.ip)) duplicates.set(d.ip, []);
    duplicates.get(d.ip).push(d.name);
  });
  const warnings = [...importWarnings, ...[...duplicates].filter(([, names]) => names.length > 1).map(([ip, names]) => `Duplicate IP ${ip} in existing inventory: ${names.join(', ')}. Edit or remove the repeated assignments.`)];
  $('import-warnings').hidden = currentTab !== 'device' || !warnings.length;
  $('import-warning-list').replaceChildren(...warnings.map(message => element('li', '', message)));
}
function openForm(device = null) {
  if (device?.id) device = devices.find(row => row.id === device.id) || device;
  editing = device?.id ?? null;
  form.reset(); $('form-error').hidden = true;
  const iptv = currentTab === 'iptv';
  form.elements.record_type.value = currentTab;
  $('category-field').hidden = false;
  $('form-system-group').hidden = iptv;
  $('form-source-group').hidden = !iptv;
  $('venue-field').hidden = $('vlan-field').hidden = iptv;
  form.elements.venue.disabled = form.elements.vlan.disabled = iptv;
  $('port-field').hidden = !iptv;
  form.elements.port.required = false; form.elements.port.disabled = !iptv;
  $('name-label').textContent = iptv ? 'Channel name' : 'Device name';
  $('form-intro').textContent = iptv ? 'Track the channel’s stream address, port, and source.' : 'Give this device a home in your inventory.';
  form.elements.name.placeholder = iptv ? 'e.g. Ship information or BBC News' : 'e.g. ATEM video switcher';
  form.elements.ip.placeholder = iptv ? 'e.g. 239.1.1.10 or DHCP' : '10.24.176.66 or DHCP';
  $('ip-hint').textContent = iptv ? 'IPv4 unicast, multicast, or DHCP' : 'IPv4 or DHCP · checked when saved';
  $('form-title').textContent = editing ? (iptv ? 'Edit channel' : 'Edit device') : (iptv ? 'Add channel' : 'Add device');
  $('save-device').textContent = editing ? 'Save changes' : (iptv ? 'Save channel' : 'Save device');
  if (device) for (const field of ['name','category','venue','discipline','ip','vlan','notes','channel_source','port']) form.elements[field].value = device[field] ?? '';
  syncButtons('form-source-buttons', form.elements.channel_source.value);
  form.elements.venue.value = cleanVenue(form.elements.venue.value);
  const venues = savedVenues();
  $('venue-suggestions').hidden = iptv || !venues.length;
  makeButtons('form-venue-buttons', venues, form.elements.venue.value, value => { form.elements.venue.value = value; syncButtons('form-venue-buttons', value); });
  $('device-dialog').showModal();
}
form.elements.venue.addEventListener('input', () => syncButtons('form-venue-buttons', form.elements.venue.value));
$('add-device').onclick = () => currentTab === 'equipment' ? window.equipmentUI.open() : openForm();
$('empty-add').onclick = () => openForm();
$('use-example').onclick = () => openForm({name:'ATEM video switcher', category:'Video switcher', venue:'Liquid Lounge', discipline:'Video', ip:'10.24.176.66', vlan:1500, notes:''});
for (const id of ['close-dialog','cancel-dialog']) $(id).onclick = () => $('device-dialog').close();
for (const id of filters) $(id).addEventListener(id === 'search' ? 'input' : 'change', render);
$('sort-order').onchange = () => { tabSortOrders[currentTab] = $('sort-order').value; render(); };
$('clear-filters').onclick = () => { filters.forEach(id => $(id).value = ''); render(); };
$('refresh').onclick = load;
form.onsubmit = async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(form));
  $('save-device').disabled = true; $('form-error').hidden = true;
  try {
    // Finish any inline note save before submitting newer changes from Edit.
    if (editing && pendingNoteSaves.has(editing)) await pendingNoteSaves.get(editing).catch(() => {});
    await api(editing ? `/api/devices/${editing}` : '/api/devices', editing ? 'PUT' : 'POST', data);
    $('device-dialog').close();
    toast(editing ? 'Record updated.' : currentTab === 'iptv' ? 'Channel added to IPTV inventory.' : 'Device added to inventory.');
    await load();
  } catch (error) { $('form-error').textContent = error.message; $('form-error').hidden = false; }
  finally { $('save-device').disabled = false; }
};
$('cancel-delete').onclick = () => $('delete-dialog').close();
$('confirm-delete').onclick = async () => {
  $('confirm-delete').disabled = true;
  try { await api(`/api/devices/${deleting.id}`, 'DELETE', {}); $('delete-dialog').close(); toast('Device deleted.'); await load(); }
  catch(error) { $('delete-error').textContent = error.message; $('delete-error').hidden = false; }
  finally { $('confirm-delete').disabled = false; }
};
let spreadsheetFile = null, spreadsheetData = null;
let spreadsheetReviewing = false, stopSpreadsheetReview = false;
let venueEdits = new Map();
const networkImportFields = [
  ['venue', 'Venue', ['venue','location','venue location','room','area']],
  ['name', 'Device name', ['device name','name','device','equipment','equipment name','hostname','channel','channel name']],
  ['ip', 'IP address', ['ip address','ip adress','ip','ipaddress','ipadress','ipv4','ipv4 address']],
  ['vlan', 'VLAN (optional)', ['vlan','vlan id','vlan number']],
  ['category', 'Category', ['category','device category','device type','type','model']],
  ['discipline', 'System', ['discipline','system','department','av system','function']],
  ['notes', 'Notes (optional)', ['notes','note','comments','description']],
  ['record_type', 'Inventory type', ['record type','inventory type']],
  ['channel_source', 'Channel source (IPTV)', ['channel source','source','onboard or satellite']],
  ['port', 'Port (IPTV)', ['port','udp port','stream port','port number']]
];
const equipmentImportFields = [
  ['brand','Brand',['brand','manufacturer','make']],
  ['model','Model',['model','model number','part number']],
  ['description','Description',['description','item','equipment','item description']],
  ['serial_number','Serial number (optional)',['serial number','serial','serial no','s/n','sn']],
  ['quantity','Quantity',['quantity','qty','count','stock']],
  ['location','Location',['location','venue','room','storage','storage location']],
  ['notes','Notes (optional)',['notes','note','comments']]
];
const iptvImportFields = [
  ['name', 'Channel Name', ['channel name','channel','name']],
  ['ip', 'MCAST IP [S]', ['mcast ip [s]','mcast ip','multicast ip','ip address','ip adress','ip','ipv4']],
  ['port', 'MCAST PORT [S]', ['mcast port [s]','mcast port','multicast port','port','udp port','stream port','port number']]
];
const importFields = () => currentTab === 'equipment' ? equipmentImportFields : currentTab === 'device'
  ? networkImportFields.filter(([field]) => ['venue','name','ip','vlan'].includes(field))
  : iptvImportFields;
const normalizedHeader = value => value.toLowerCase().replace(/[_-]/g, ' ').replace(/\s+/g, ' ').trim();
function mappedRows(applyVenueEdits = true) {
  return spreadsheetData.rows.map(row => {
    const mapped = Object.fromEntries(importFields().map(([field]) => {
      const column = $('map-' + field).value;
      let value = column === '' ? '' : row[Number(column)];
      if (field === 'record_type') value = value.toLowerCase() || currentTab;
      if (field === 'ip' && isDHCP(value)) value = 'DHCP';
      if (field === 'venue' || field === 'location') value = cleanVenue(value);
      if (field === 'vlan' && !/^[0-9]+$/.test(value)) value = '';
      if (field === 'channel_source') value = ({onboard:'Onboard', satellite:'Satellite'})[value.toLowerCase()] || value;
      if (field === 'discipline') {
        const aliases = {video:'Video', audio:'Audio', lighting:'Lighting', lights:'Lighting', light:'Lighting', control:'Control', network:'Network', other:'Other'};
        value = aliases[value.toLowerCase()] || value;
      }
      return [field, value];
    }));
    if (currentTab !== 'equipment') mapped.record_type = currentTab;
    const field = currentTab === 'equipment' ? 'location' : 'venue';
    if (applyVenueEdits && venueEdits.has(mapped[field])) mapped[field] = venueEdits.get(mapped[field]);
    return mapped;
  });
}
function showVenueEditors() {
  const equipment = currentTab === 'equipment', field = equipment ? 'location' : 'venue';
  const venues = [...new Set(mappedRows(false).filter(row => equipment || row.record_type !== 'iptv').map(row => row[field]).filter(Boolean))];
  $('import-venue-editor').hidden = !venues.length;
  $('import-venue-title').textContent = equipment ? 'Location buttons' : 'Venue buttons';
  $('import-venue-list').replaceChildren(...venues.map((original, index) => {
    const row = element('div', 'venue-editor-row');
    const button = element('button', 'choice-button', venueEdits.has(original) ? venueEdits.get(original) : original);
    button.type = 'button';
    colorVenueButton(button, button.textContent);
    const label = element('label');
    label.append(element('span', 'sr-only', `Edit ${equipment ? 'location' : 'venue'} ${original}`));
    const input = element('input');
    input.id = `import-venue-${index}`; input.value = button.textContent; input.maxLength = 120;
    input.autocomplete = 'off';
    input.oninput = () => {
      const venue = cleanVenue(input.value);
      venueEdits.set(original, venue);
      button.textContent = venue;
      colorVenueButton(button, venue);
      showSpreadsheetPreview();
    };
    input.onblur = () => { input.value = cleanVenue(input.value); };
    button.onclick = () => { input.focus(); input.select(); };
    label.append(input); row.append(button, label); return row;
  }));
}
function showSpreadsheetPreview() {
  const rows = mappedRows();
  $('spreadsheet-preview').replaceChildren(...rows.slice(0,3).map((row, index) => {
    const card = element('div', 'spreadsheet-preview-row');
    if (currentTab === 'equipment') {
      card.append(element('strong','', `Row ${spreadsheetData.row_numbers[index]} · ${[row.brand, row.model].filter(Boolean).join(' ')}`));
      card.append(element('p','', [row.quantity ? `Quantity ${row.quantity}` : '', row.location, row.serial_number ? `Serial ${row.serial_number}` : ''].filter(Boolean).join(' · ')));
      card.append(element('p','', row.description)); return card;
    }
    card.append(element('strong', '', `Row ${spreadsheetData.row_numbers[index]} · ${row.name}`));
    card.append(element('p', '', (row.record_type === 'iptv' ? [row.ip, row.port ? `Port ${row.port}` : '', row.channel_source] : [row.ip, row.vlan ? `VLAN ${row.vlan}` : '', row.venue]).filter(Boolean).join(' · ')));
    card.append(element('p', '', [row.discipline, row.category].filter(Boolean).join(' / ')));
    return card;
  }));
}
async function loadSpreadsheet() {
  $('confirm-import').disabled = true; $('reload-sheet').disabled = true;
  $('spreadsheet-error').hidden = true;
  try {
    const data = await api('/api/spreadsheet-preview', 'POST', {...spreadsheetFile, sheet: $('sheet-choice').value, header_row: Number($('header-row').value)});
    spreadsheetData = data;
    venueEdits = new Map();
    $('sheet-label').hidden = !data.sheets.length;
    $('sheet-choice').replaceChildren(...data.sheets.map(sheet => new Option(sheet, sheet)));
    $('sheet-choice').value = data.sheet;
    $('spreadsheet-summary').textContent = `${spreadsheetFile.filename} · ${data.rows.length} records`;
    if (data.ignored_columns?.length) $('spreadsheet-summary').textContent += ` · Ignored columns: ${data.ignored_columns.join(', ')}`;
    $('column-mappings').replaceChildren(...importFields().map(([field, label, aliases]) => {
      const group = element('div', 'mapping-row');
      const columnLabel = element('label', '', label);
      const select = element('select'); select.id = 'map-' + field;
      select.add(new Option('Leave blank', ''));
      data.headers.forEach((header, index) => select.add(new Option(`${index+1}. ${header}`, String(index))));
      // Prefer the requested header before falling back to broader aliases.
      const matched = aliases.map(alias => data.headers.findIndex(header => normalizedHeader(header) === alias)).find(index => index >= 0) ?? -1;
      if (matched >= 0) select.value = String(matched);
      columnLabel.append(select); group.append(columnLabel);
      select.onchange = () => { showVenueEditors(); showSpreadsheetPreview(); };
      return group;
    }));
    showVenueEditors(); showSpreadsheetPreview();
    $('confirm-import').textContent = `Review ${data.rows.length} rows`;
    $('confirm-import').disabled = false;
  } catch (error) {
    $('spreadsheet-error').textContent = error.message;
    $('spreadsheet-error').hidden = false;
  } finally { $('reload-sheet').disabled = false; }
}
function closeSpreadsheet() {
  if (spreadsheetReviewing) { stopSpreadsheetReview = true; return; }
  $('spreadsheet-dialog').close(); spreadsheetData = null; spreadsheetFile = null; venueEdits = new Map();
}
$('close-spreadsheet').onclick = $('cancel-spreadsheet').onclick = closeSpreadsheet;
$('spreadsheet-dialog').addEventListener('cancel', event => {
  if (spreadsheetReviewing) { event.preventDefault(); stopSpreadsheetReview = true; }
  else { spreadsheetData = null; spreadsheetFile = null; venueEdits = new Map(); }
});
$('reload-sheet').onclick = loadSpreadsheet;
// Sheet/header changes must be loaded before an import can be confirmed.
$('sheet-choice').onchange = $('header-row').oninput = () => { $('confirm-import').disabled = true; };
const meaningfulImportRow = row => Object.entries(row).some(([field,value]) => field !== 'record_type' && value !== '');
let finishRowReview = null, rowReviewSaving = false;
function endRowReview(result) {
  if (rowReviewSaving || !finishRowReview) return;
  const finish = finishRowReview; finishRowReview = null;
  $('row-review-dialog').close(); finish(result);
}
$('stop-row-review').onclick = $('cancel-row-review').onclick = () => endRowReview(null);
$('skip-review-row').onclick = () => endRowReview({skippedRow:true});
$('row-review-dialog').addEventListener('cancel', event => { event.preventDefault(); endRowReview(null); });
function reviewImportRow(entry, index, total, tab) {
  return new Promise(resolve => {
    finishRowReview = resolve;
    const equipment = tab === 'equipment';
    $('row-review-title').textContent = equipment ? 'Import this equipment?' : tab === 'iptv' ? 'Import this channel?' : 'Import this device?';
    $('row-review-progress').textContent = `Row ${entry.number} · ${index + 1} of ${total} · ${spreadsheetFile.filename}`;
    $('row-review-error').hidden = true;
    const controls = new Map();
    const fields = importFields();
    $('row-review-fields').style.setProperty('--review-columns', fields.length);
    $('row-review-fields').replaceChildren(...fields.map(([field, label]) => {
      const group = element('label', '', label.replace(' (optional)', ''));
      const input = element('input'); input.id = `review-${field}`;
      input.value = entry.row[field] ?? ''; input.autocomplete = 'off';
      input.maxLength = field === 'notes' || field === 'description' ? 2000 : 120;
      if (field === 'ip') input.spellcheck = false;
      group.append(input); controls.set(field, input);
      if (field === 'ip') {
        const actions = element('div', 'review-ip-actions');
        const dhcp = element('button', 'choice-button', 'DHCP'); dhcp.type = 'button'; dhcp.id = 'review-dhcp';
        const blank = element('button', 'quiet', 'Clear'); blank.type = 'button'; blank.id = 'review-clear-ip';
        const update = () => {
          dhcp.setAttribute('aria-pressed', String(isDHCP(input.value)));
          $('row-review-ip-hint').hidden = !input.value.trim() || isDHCP(input.value) || !/[^0-9.\s]/.test(input.value);
        };
        dhcp.onclick = () => { input.value = 'DHCP'; update(); };
        blank.onclick = () => { input.value = ''; update(); input.focus(); };
        input.oninput = update; update(); actions.append(dhcp, blank); group.append(actions);
      }
      return group;
    }));
    if (equipment) $('row-review-ip-hint').hidden = true;
    $('accept-review-row').onclick = async () => {
      if (rowReviewSaving) return;
      const row = {...entry.row};
      controls.forEach((input, field) => { row[field] = input.value.trim(); });
      if (!equipment) {
        if (isDHCP(row.ip)) row.ip = 'DHCP';
        if (tab === 'device') {
          row.venue = cleanVenue(row.venue);
          if (!/^[0-9]+$/.test(row.vlan)) row.vlan = '';
        }
      } else row.location = cleanVenue(row.location);
      // Clearing the final value makes this an empty row, which needs no write.
      if (!meaningfulImportRow(row)) { endRowReview({skippedRow:true}); return; }
      const dialogControls = [...$('row-review-dialog').querySelectorAll('button,input')];
      rowReviewSaving = true; dialogControls.forEach(control => { control.disabled = true; });
      $('row-review-error').hidden = true;
      let result;
      try {
        result = await api(equipment ? '/api/equipment/import' : '/api/import', 'POST', equipment
          ? {version:1,equipment:[row]}
          : {version:1,devices:[row],source:'spreadsheet',row_numbers:[entry.number]});
      } catch(error) {
        $('row-review-error').textContent = error.message.replace('Nothing was imported.', 'This row was not imported. Previously accepted rows remain saved.');
        $('row-review-error').hidden = false;
      } finally {
        rowReviewSaving = false; dialogControls.forEach(control => { control.disabled = false; });
      }
      if (result) endRowReview(result);
    };
    $('row-review-dialog').showModal();
    $('accept-review-row').focus();
  });
}
$('spreadsheet-form').onsubmit = async event => {
  event.preventDefault();
  if (!spreadsheetData || $('confirm-import').disabled) return;
  $('confirm-import').disabled = true; $('spreadsheet-error').hidden = true;
  spreadsheetReviewing = true; stopSpreadsheetReview = false;
  try {
    const tab = currentTab;
    const entries = mappedRows().map((row,index) => ({row,number:spreadsheetData.row_numbers[index]})).filter(({row}) => meaningfulImportRow(row));
    let added = 0, existing = 0, skipped = 0, stopped = false;
    if (tab === 'device') importWarnings = [];
    for (let index = 0; index < entries.length; index++) {
      if (stopSpreadsheetReview) { stopped = true; break; }
      const result = await reviewImportRow(entries[index], index, entries.length, tab);
      if (result === null) { stopped = true; break; }
      if (result.skippedRow) skipped++;
      else {
        added += result.added; existing += result.skipped;
        if (tab === 'device') importWarnings.push(...(result.warnings || []));
        await load();
      }
    }
    spreadsheetReviewing = false; closeSpreadsheet();
    toast(`${stopped ? 'Review stopped. ' : ''}Imported ${added} records. Skipped ${skipped} rows and ${existing} existing assignments.`);
    await load();
  } catch(error) { $('spreadsheet-error').textContent = error.message; $('spreadsheet-error').hidden = false; }
  finally { spreadsheetReviewing = false; $('confirm-import').disabled = false; }
};
$('import').onclick = () => $('import-file').click();
$('import-file').onchange = async event => {
  const file = event.target.files[0]; if (!file) return;
  $('import').disabled = true;
  try {
    if (file.size > 5_000_000) throw new Error('Choose a file smaller than 5 MB.');
    if (/\.(xlsx|csv)$/i.test(file.name)) {
      const content = await new Promise((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(new Error('Could not read file.')); reader.readAsDataURL(file);
      });
      spreadsheetFile = {filename:file.name, content};
      spreadsheetData = null; venueEdits = new Map(); $('import-venue-editor').hidden = true;
      $('import-venue-list').replaceChildren(); $('header-row').value = '1'; $('sheet-choice').replaceChildren();
      $('column-mappings').replaceChildren(); $('spreadsheet-preview').replaceChildren();
      $('spreadsheet-summary').textContent = 'Reading ' + file.name + '…';
      $('spreadsheet-dialog').showModal();
      await loadSpreadsheet();
    } else if (/\.json$/i.test(file.name)) {
      const result = await api(currentTab === 'equipment' ? '/api/equipment/import' : '/api/import', 'POST', JSON.parse(await file.text()));
      if (currentTab === 'device') importWarnings = result.warnings || [];
      toast(`Imported ${result.added} records. Skipped ${result.skipped} existing assignments.`);
      await load();
    } else throw new Error('Choose .xlsx, .csv, or a Broadcast Hub .json export.');
  } catch(error) { toast('Import failed: ' + error.message); }
  finally { event.target.value = ''; $('import').disabled = false; }
};
load();
