const defaultInventoryLayout = {"columns": [{"key": "description", "label": "Item", "type": "text", "important": true, "filter": "none", "options": []}, {"key": "brand", "label": "Brand", "type": "text", "important": true, "filter": "none", "options": []}, {"key": "model", "label": "Model", "type": "text", "important": true, "filter": "none", "options": []}, {"key": "serial_number", "label": "Serial number", "type": "text", "important": true, "filter": "none", "options": []}, {"key": "quantity", "label": "Quantity", "type": "text", "important": true, "filter": "none", "options": []}, {"key": "location", "label": "Location", "type": "text", "important": true, "filter": "buttons", "options": []}, {"key": "notes", "label": "Notes", "type": "text", "important": false, "filter": "none", "options": []}], "primary_search": "serial_number", "identifier": ""};
const scalaInventoryLayout = {"columns": [{"key": "asset_id", "label": "ID", "type": "text", "important": true, "filter": "none", "options": []}, {"key": "location", "label": "Location", "type": "text", "important": true, "filter": "none", "options": []}, {"key": "monitor_model", "label": "Monitor model", "type": "text", "important": true, "filter": "dropdown", "options": []}, {"key": "orientation", "label": "Orientation", "type": "buttons", "important": false, "filter": "dropdown", "options": ["Vertical", "Horizontal"]}, {"key": "notes", "label": "Notes", "type": "text", "important": false, "filter": "none", "options": []}], "primary_search": "asset_id", "identifier": "asset_id"};
const inventoryBaseFields = new Set(['description','brand','model','serial_number','quantity','location','notes']);
const inventoryValue = (row,key) => inventoryBaseFields.has(key) ? row[key] ?? '' : row.custom_values?.[key] ?? '';
function inventoryInput(column,value = '', {allowClear = true} = {}) {
  // Orientation stays easy to set later, including inventories that used a text column.
  if (column.key === 'orientation') {
    column = {...column,type:'buttons',options:column.options.length ? column.options : ['Vertical','Horizontal']};
    allowClear = false;
  }
  const wrapper = element('div', 'inventory-value-input');
  const control = element(column.type === 'select' ? 'select' : 'input');
  control.dataset.columnKey = column.key; control.setAttribute('aria-label',column.label);
  control.value = value; control.maxLength = column.key === 'notes' ? 2000 : 120;
  if (column.type === 'select') {
    control.append(new Option('Leave blank',''),...column.options.map(value => new Option(value,value)));
    if(value&&!column.options.includes(value))control.append(new Option('Review: '+value,value));
    control.value = value;
  } else if (column.type === 'checkbox') {
    control.type='hidden';
    const label=element('label','inventory-checkbox-control');
    const check=element('input');check.type='checkbox';check.checked=value==='Yes';check.indeterminate=!value;check.setAttribute('aria-label',column.label);
    const text=element('span','',value || 'Unknown');
    check.onchange=()=>{control.value=check.checked?'Yes':'No';text.textContent=control.value;control.dispatchEvent(new Event('change',{bubbles:true}));};
    const clear=element('button','quiet','Clear');clear.type='button';clear.onclick=()=>{control.value='';check.checked=false;check.indeterminate=true;text.textContent='Unknown';control.dispatchEvent(new Event('change',{bubbles:true}));};
    label.append(check,text);wrapper.append(label);if(allowClear)wrapper.append(clear);
  } else if (column.type === 'buttons') {
    control.type='hidden';const group=element('div','choice-buttons');group.setAttribute('role','group');group.setAttribute('aria-label',column.label);
    (allowClear ? ['',...column.options] : column.options).forEach(value=>{const button=element('button','choice-button',value || 'Clear');button.type='button';button.dataset.value=value;button.setAttribute('aria-pressed',String(value===control.value));button.onclick=()=>{control.value=value;group.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));control.dispatchEvent(new Event('change',{bubbles:true}));};group.append(button);});wrapper.append(group);
  } else { control.type=column.key==='quantity'?'number':'text';if(column.key==='quantity'){control.min='0';control.max='1000000';} }
  wrapper.append(control);return {wrapper,control};
}
