'use strict';
const $ = id => document.getElementById(id);
let devices = [], editing = null, deleting = null, timer;
const form = $('device-form');
const filters = ['search', 'venue-filter', 'system-filter', 'category-filter', 'vlan-filter'];
const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const systems = ['Video', 'Audio', 'Lighting', 'Control', 'Network', 'Other'];
function makeButtons(id, values, selected, onSelect, allLabel = null) {
  const choices = allLabel ? [['', allLabel], ...values.map(v => [v, v])] : values.map(v => [v, v]);
  $(id).replaceChildren(...choices.map(([value, label]) => {
    const button = element('button', 'choice-button', label);
    button.type = 'button';
    button.dataset.value = value;
    button.setAttribute('aria-pressed', String(value === selected));
    button.onclick = () => onSelect(value);
    return button;
  }));
}
function syncButtons(id, value) {
  $(id).querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.value === value)));
}
function updateVenueButtons() {
  const venues = [...new Set(devices.map(d => d.venue))].sort((a,b) => a.localeCompare(b));
  if (!venues.includes($('venue-filter').value)) $('venue-filter').value = '';
  makeButtons('venue-buttons', venues, $('venue-filter').value, value => { $('venue-filter').value = value; render(); }, 'All venues');
}
makeButtons('system-buttons', systems, '', value => { $('system-filter').value = value; render(); }, 'All systems');
makeButtons('form-system-buttons', systems, '', value => { form.elements.discipline.value = value; syncButtons('form-system-buttons', value); });
function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(timer); timer = setTimeout(() => { $('toast').hidden = true; }, 6000);
}
async function api(path, method = 'GET', body) {
  const options = {method, headers: {'Content-Type': 'application/json'}};
  if (body !== undefined) options.body = JSON.stringify(body);
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed. Please try again.');
  return data;
}
function options(id, values) {
  const select = $(id), previous = select.value;
  while (select.options.length > 1) select.remove(1);
  [...new Set(values)].sort((a,b) => typeof a === 'number' ? a-b : a.localeCompare(b)).forEach(value => select.add(new Option(value, value)));
  if ([...select.options].some(option => option.value === previous)) select.value = previous;
}
async function load() {
  $('refresh').disabled = true;
  try {
    devices = (await api('/api/devices')).devices;
    $('load-error').hidden = true;
    $('total').textContent = devices.length;
    $('venue-count').textContent = new Set(devices.map(d => d.venue)).size;
    $('vlan-count').textContent = new Set(devices.map(d => d.vlan)).size;
    $('system-count').textContent = ['Video', 'Audio', 'Lighting'].map(s => devices.filter(d => d.discipline === s).length).join(' / ');
    updateVenueButtons();
    options('category-filter', devices.map(d => d.category));
    options('vlan-filter', devices.map(d => d.vlan));
    $('venues').replaceChildren(...[...new Set(devices.map(d => d.venue))].map(v => new Option(v, v)));
    render();
    return true;
  } catch (error) {
    $('load-error').textContent = 'Could not refresh inventory. ' + error.message;
    $('load-error').hidden = false;
    return false;
  } finally { $('loading').hidden = true; $('refresh').disabled = false; }
}
function render() {
  syncButtons('venue-buttons', $('venue-filter').value);
  syncButtons('system-buttons', $('system-filter').value);
  const query = $('search').value.trim().toLowerCase();
  const results = devices.filter(d =>
    [d.name,d.ip,d.venue,d.category,d.discipline,d.notes,String(d.vlan)].some(v => v.toLowerCase().includes(query)) &&
    (!$('venue-filter').value || d.venue === $('venue-filter').value) &&
    (!$('system-filter').value || d.discipline === $('system-filter').value) &&
    (!$('category-filter').value || d.category === $('category-filter').value) &&
    (!$('vlan-filter').value || String(d.vlan) === $('vlan-filter').value));
  $('result-count').textContent = results.length;
  $('showing').textContent = `${results.length} of ${devices.length} devices`;
  $('empty').hidden = devices.length > 0;
  $('no-results').hidden = devices.length === 0 || results.length > 0;
  const rows = results.map(device => {
    const row = element('article', 'device-row');
    const identity = element('div', 'device-identity identity-cell');
    const icon = element('span', 'device-icon', {Video:'▣',Audio:'♫',Lighting:'☼',Network:'⌘',Control:'⌁',Other:'◇'}[device.discipline]);
    icon.setAttribute('aria-hidden','true');
    const title = element('div');
    title.append(element('div', 'device-name', device.name), element('span', 'device-category', device.category));
    if (device.notes) title.append(element('div', 'device-notes', device.notes));
    identity.append(icon, title);
    const ip = element('div', 'ip-cell');
    ip.append(element('div', 'device-ip', device.ip), element('span', 'cell-caption', `VLAN ${device.vlan} · Format valid`));
    const venue = element('div', 'venue-cell');
    venue.append(element('div', 'device-venue', device.venue), element('span', 'cell-caption', 'Venue'));
    const system = element('div','system-cell');
    system.append(element('span', `badge ${device.discipline.toLowerCase()}`, device.discipline));
    const actions = element('div', 'row-actions');
    const edit = element('button', 'quiet', 'Edit'); edit.setAttribute('aria-label', `Edit ${device.name}`); edit.onclick = () => openForm(device);
    const remove = element('button', 'quiet', 'Delete'); remove.setAttribute('aria-label', `Delete ${device.name}`);
    remove.onclick = () => { deleting = device; $('delete-description').textContent = `${device.name} · ${device.ip} · VLAN ${device.vlan}`; $('delete-error').hidden = true; $('delete-dialog').showModal(); $('cancel-delete').focus(); };
    actions.append(edit,remove); row.append(identity,ip,venue,system,actions); return row;
  });
  $('device-list').replaceChildren(...rows);
}
function openForm(device = null) {
  editing = device?.id ?? null;
  form.reset(); $('form-error').hidden = true;
  $('form-title').textContent = editing ? 'Edit device' : 'Add device';
  $('save-device').textContent = editing ? 'Save changes' : 'Save device';
  if (device) for (const field of ['name','category','venue','discipline','ip','vlan','notes']) form.elements[field].value = device[field] ?? '';
  syncButtons('form-system-buttons', form.elements.discipline.value);
  const venues = [...new Set(devices.map(d => d.venue))].sort((a,b) => a.localeCompare(b));
  $('venue-suggestions').hidden = !venues.length;
  makeButtons('form-venue-buttons', venues, form.elements.venue.value, value => { form.elements.venue.value = value; syncButtons('form-venue-buttons', value); });
  $('device-dialog').showModal();
}
form.elements.venue.addEventListener('input', () => syncButtons('form-venue-buttons', form.elements.venue.value));
$('add-device').onclick = () => openForm();
$('empty-add').onclick = () => openForm();
$('use-example').onclick = () => openForm({name:'ATEM video switcher', category:'Video switcher', venue:'Liquid Lounge', discipline:'Video', ip:'10.24.176.66', vlan:1500, notes:''});
for (const id of ['close-dialog','cancel-dialog']) $(id).onclick = () => $('device-dialog').close();
for (const id of filters) $(id).addEventListener(id === 'search' ? 'input' : 'change', render);
$('clear-filters').onclick = () => { filters.forEach(id => $(id).value = ''); render(); };
$('refresh').onclick = load;
form.onsubmit = async event => {
  event.preventDefault();
  if (!form.elements.discipline.value) {
    $('form-error').textContent = 'Choose a system for this device.';
    $('form-error').hidden = false;
    $('form-system-buttons').querySelector('button').focus();
    return;
  }
  const data = Object.fromEntries(new FormData(form));
  $('save-device').disabled = true; $('form-error').hidden = true;
  try {
    await api(editing ? `/api/devices/${editing}` : '/api/devices', editing ? 'PUT' : 'POST', data);
    $('device-dialog').close();
    toast(editing ? 'Device updated.' : 'Device added to inventory.');
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
const importFields = [
  ['name', 'Device name', ['name','device','device name','equipment','equipment name','hostname'], ''],
  ['category', 'Category', ['category','device category','device type','type','model'], 'Other'],
  ['venue', 'Venue', ['venue','location','venue location','room','area'], ''],
  ['discipline', 'System', ['discipline','system','department','av system','function'], 'Other'],
  ['ip', 'IP address', ['ip','ip address','ipaddress','ipv4','ipv4 address'], ''],
  ['vlan', 'VLAN', ['vlan','vlan id','vlan number'], ''],
  ['notes', 'Notes (optional)', ['notes','note','comments','description'], '']
];
const normalizedHeader = value => value.toLowerCase().replace(/[_-]/g, ' ').replace(/\s+/g, ' ').trim();
function mappedRows() {
  return spreadsheetData.rows.map(row => Object.fromEntries(importFields.map(([field]) => {
    const column = $('map-' + field).value;
    let value = (column === '' ? '' : row[Number(column)]) || $('default-' + field).value.trim();
    if (field === 'discipline') {
      const aliases = {video:'Video', audio:'Audio', lighting:'Lighting', lights:'Lighting', light:'Lighting', control:'Control', network:'Network', other:'Other'};
      value = aliases[value.toLowerCase()] || value;
    }
    return [field, value];
  })));
}
function showSpreadsheetPreview() {
  const rows = mappedRows();
  $('spreadsheet-preview').replaceChildren(...rows.slice(0,3).map((row, index) => {
    const card = element('div', 'spreadsheet-preview-row');
    card.append(element('strong', '', `Row ${spreadsheetData.row_numbers[index]} · ${row.name || 'Missing device name'}`));
    card.append(element('p', '', `${row.ip || 'Missing IP'} · VLAN ${row.vlan || '?'} · ${row.venue || 'Missing venue'}`));
    card.append(element('p', '', `${row.discipline || 'Missing system'} / ${row.category || 'Missing category'}`));
    return card;
  }));
}
async function loadSpreadsheet() {
  $('confirm-import').disabled = true; $('reload-sheet').disabled = true;
  $('spreadsheet-error').hidden = true;
  try {
    const data = await api('/api/spreadsheet-preview', 'POST', {...spreadsheetFile, sheet: $('sheet-choice').value, header_row: Number($('header-row').value)});
    spreadsheetData = data;
    $('sheet-label').hidden = !data.sheets.length;
    $('sheet-choice').replaceChildren(...data.sheets.map(sheet => new Option(sheet, sheet)));
    $('sheet-choice').value = data.sheet;
    $('spreadsheet-summary').textContent = `${spreadsheetFile.filename} · ${data.rows.length} device rows`;
    $('column-mappings').replaceChildren(...importFields.map(([field, label, aliases, defaultValue]) => {
      const group = element('div', 'mapping-row');
      const columnLabel = element('label', '', label);
      const select = element('select'); select.id = 'map-' + field;
      select.add(new Option('Use default only', ''));
      data.headers.forEach((header, index) => select.add(new Option(`${index+1}. ${header}`, String(index))));
      const matched = data.headers.findIndex(header => aliases.includes(normalizedHeader(header)));
      if (matched >= 0) select.value = String(matched);
      const fallbackLabel = element('label', '', 'Default if missing');
      const fallback = element('input'); fallback.id = 'default-' + field; fallback.value = defaultValue;
      fallback.placeholder = field === 'notes' ? 'Optional' : `Default ${label.toLowerCase()}`;
      fallback.maxLength = field === 'notes' ? 2000 : 120;
      columnLabel.append(select); fallbackLabel.append(fallback); group.append(columnLabel, fallbackLabel);
      select.onchange = fallback.oninput = showSpreadsheetPreview;
      return group;
    }));
    showSpreadsheetPreview();
    $('confirm-import').textContent = `Import ${data.rows.length} devices`;
    $('confirm-import').disabled = !data.rows.length;
    if (!data.rows.length) {
      $('spreadsheet-error').textContent = 'No device rows in this selection. Choose another worksheet or header row and reload the preview.';
      $('spreadsheet-error').hidden = false;
    }
  } catch (error) {
    $('spreadsheet-error').textContent = error.message;
    $('spreadsheet-error').hidden = false;
  } finally { $('reload-sheet').disabled = false; }
}
function closeSpreadsheet() {
  $('spreadsheet-dialog').close(); spreadsheetData = null; spreadsheetFile = null;
}
$('close-spreadsheet').onclick = $('cancel-spreadsheet').onclick = closeSpreadsheet;
$('spreadsheet-dialog').addEventListener('cancel', () => { spreadsheetData = null; spreadsheetFile = null; });
$('reload-sheet').onclick = loadSpreadsheet;
// Sheet/header changes must be loaded before an import can be confirmed.
$('sheet-choice').onchange = $('header-row').oninput = () => { $('confirm-import').disabled = true; };
$('spreadsheet-form').onsubmit = async event => {
  event.preventDefault();
  if (!spreadsheetData || $('confirm-import').disabled) return;
  $('confirm-import').disabled = true; $('spreadsheet-error').hidden = true;
  try {
    const rows = mappedRows();
    const missing = rows.findIndex(row => ['name','category','venue','discipline','ip','vlan'].some(field => !row[field]));
    if (missing >= 0) throw new Error(`Spreadsheet row ${spreadsheetData.row_numbers[missing]} has a missing required field. Choose its column or enter a default.`);
    const result = await api('/api/import', 'POST', {version:1, devices:rows});
    closeSpreadsheet();
    toast(`Imported ${result.added} devices. Skipped ${result.skipped} existing IP/VLAN assignments.`);
    await load();
  } catch(error) { $('spreadsheet-error').textContent = error.message; $('spreadsheet-error').hidden = false; }
  finally { $('confirm-import').disabled = false; }
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
      spreadsheetData = null; $('header-row').value = '1'; $('sheet-choice').replaceChildren();
      $('column-mappings').replaceChildren(); $('spreadsheet-preview').replaceChildren();
      $('spreadsheet-summary').textContent = 'Reading ' + file.name + '…';
      $('spreadsheet-dialog').showModal();
      await loadSpreadsheet();
    } else if (/\.json$/i.test(file.name)) {
      const result = await api('/api/import', 'POST', JSON.parse(await file.text()));
      toast(`Imported ${result.added} devices. Skipped ${result.skipped} existing IP/VLAN assignments.`);
      await load();
    } else throw new Error('Choose .xlsx, .csv, or an IP Tracking .json export.');
  } catch(error) { toast('Import failed: ' + error.message); }
  finally { event.target.value = ''; $('import').disabled = false; }
};
load();
