"""Read-only, one-to-one source inventory reconciliation across all worksheets."""
import re
from collections import Counter
from spreadsheets import preview

ALIASES = {
    'brand': ('brand', 'manufacturer', 'make'),
    'model': ('model', 'model number', 'part number'),
    'description': ('description', 'item', 'name', 'equipment', 'item name'),
    'serial_number': ('serial number', 'serial', 'serial no', 's/n', 'sn'),
    'quantity': ('quantity', 'qty', 'count', 'quantity in stock'),
    'location': ('location', 'venue', 'room', 'storage location'),
    'notes': ('notes', 'note', 'comments'),
}
PLACEHOLDERS = {'n/a', 'na', 'none', 'not applicable', '-'}


def norm(value):
    return re.sub(r'\s+', ' ', str(value or '').strip()).casefold()


def meaningful(value):
    return bool(norm(value)) and norm(value) not in PLACEHOLDERS


def original_records(payload):
    sheets = preview(dict(payload, sheets_only=True))['sheets'] if str(payload.get('filename','')).lower().endswith('.xlsx') else ['']
    records, sheet_errors = [], []
    for sheet in sheets:
        try:
            data = preview(dict(payload, sheet=sheet, auto_header=True))
        except ValueError as exc:
            sheet_errors.append({'sheet': sheet, 'error': str(exc)})
            continue
        headers = [re.sub(r'[_-]+', ' ', h.lower()).strip() for h in data['headers']]
        indexes = {field: next((headers.index(alias) for alias in aliases if alias in headers), None) for field, aliases in ALIASES.items()}
        locations = [index for index, header in enumerate(headers) if header == 'location']
        # The original workbook uses the first LOCATION for shelf position and
        # the second LOCATION for the room. Tools also stores drawer positions.
        if len(locations) > 1:
            indexes['location'] = locations[-1]
        for values, number in zip(data['rows'], data['row_numbers']):
            row = {field: values[index] if index is not None else '' for field, index in indexes.items()}
            if not any(meaningful(row[field]) for field in ('brand','model','description','serial_number','quantity')):
                continue
            details = {}
            for index, header in enumerate(headers):
                if values[index] and header in ('storage position','condition','unit','source sheet','source row','notes2'):
                    details[header] = values[index]
            if len(locations) > 1:
                details['storage position'] = values[locations[0]]
            elif sheet.casefold() == 'tools' and row['location']:
                details['storage position'] = row['location']
                row['location'] = sheet
            if not row['location']:
                row['location'] = sheet
            for field in ('model','serial_number'):
                if norm(row[field]) in PLACEHOLDERS:
                    row[field] = ''
            raw_quantity = row['quantity']
            row['quantity'] = int(raw_quantity) if re.fullmatch(r'\d+', raw_quantity or '') else None
            issues = [f'Missing {field.replace("_", " ")}' for field in ('brand','model','serial_number','quantity','location') if row[field] is None or row[field] == '']
            if raw_quantity and row['quantity'] is None:
                issues.append(f'Non-numeric original quantity: {raw_quantity}')
            if re.search(r'[|;,\n]', row['serial_number']):
                issues.append('Multiple serial numbers in one source row')
            if re.search(r'\bsee\b.*invent|separate inventory', ' '.join(str(v) for v in row.values()), re.I):
                issues.append('Reference to another inventory; not an itemized stock entry')
            records.append({'sheet':sheet, 'row_number':number, 'record':row, 'details':details, 'issues':issues})
            if len(records) > 10000:
                raise ValueError('Cross-check supports up to 10,000 source rows across all sheets.')
    return records, sheet_errors


def reconcile(payload, inventory):
    sources, sheet_errors = original_records(payload)
    serial_counts = Counter(norm(entry['record']['serial_number']) for entry in sources if entry['record']['serial_number'])
    used, results = set(), []
    for entry in sources:
        source = entry['record']
        serial = norm(source['serial_number'])
        candidates = []
        basis = 'serial number' if serial else 'model/item and brand'
        if serial:
            candidates = [item for item in inventory if norm(item['serial_number']) == serial]
        else:
            candidates = [item for item in inventory if
                          (not source['brand'] or norm(item['brand']) == norm(source['brand'])) and
                          (not source['model'] or norm(item['model']) == norm(source['model'])) and
                          (not source['description'] or norm(item['description']) == norm(source['description']))]
            local = [item for item in candidates if norm(item['location']) == norm(source['location'])]
            if local:
                candidates = local
        status, differences, match = 'missing', [], None
        if serial and serial_counts[serial] > 1:
            status = 'ambiguous'
            entry['issues'].append('Repeated source serial; one saved record cannot prove all source rows are present')
        elif len(candidates) > 1:
            status = 'ambiguous'
        elif len(candidates) == 1 and candidates[0]['id'] in used:
            status = 'ambiguous'
            entry['issues'].append('Saved record already matched to another source row; check separate stock entries or combined quantities')
        elif len(candidates) == 1:
            match = candidates[0]
            used.add(match['id'])
            for field in ('brand','model','description','serial_number','location','quantity'):
                original = source[field]
                if original is None or original == '':
                    continue
                equal = original == match[field] if field == 'quantity' else norm(original) == norm(match[field])
                if not equal:
                    differences.append({'field':field, 'original':original, 'saved':match[field]})
            for field, value in {'notes':source['notes'], **entry['details']}.items():
                if value and field not in ('source sheet','source row') and norm(value) not in norm(match['notes']):
                    differences.append({'field':field, 'original':value, 'saved':match['notes']})
            status = 'different' if differences else 'needs_review' if entry['issues'] else 'matched'
        results.append({**entry, 'status':status, 'basis':basis, 'saved_id': match['id'] if match else None,
                        'candidate_ids':[item['id'] for item in candidates], 'differences':differences})
    summary = dict(Counter(row['status'] for row in results))
    for status in ('matched','needs_review','different','missing','ambiguous'):
        summary.setdefault(status, 0)
    return {'filename':payload['filename'], 'source_rows':len(sources), 'saved_rows':len(inventory),
            'summary':summary, 'rows':results, 'sheet_errors':sheet_errors,
            'extra_records':[item for item in inventory if item['id'] not in used],
            'complete':bool(sources) and not sheet_errors and all(row['status']=='matched' for row in results)}
