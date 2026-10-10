"""Inventory-specific columns, filters and bounded custom record values."""
import re

BASE_FIELDS = ('description','brand','model','serial_number','quantity','location','notes')
LABELS = {'description':'Item','brand':'Brand','model':'Model','serial_number':'Serial number','quantity':'Quantity','location':'Location','notes':'Notes'}
DEFAULT_PROFILE = {'columns':[{'key':key,'label':LABELS[key],'type':'text','important':key!='notes','filter':'buttons' if key=='location' else 'none','options':[]} for key in BASE_FIELDS], 'primary_search':'serial_number', 'identifier':''}
SCALA_PROFILE = {'columns':[
    {'key':'asset_id','label':'ID','type':'text','important':True,'filter':'none','options':[]},
    {'key':'location','label':'Location','type':'text','important':True,'filter':'none','options':[]},
    {'key':'monitor_model','label':'Monitor model','type':'text','important':True,'filter':'dropdown','options':[]},
    {'key':'orientation','label':'Orientation','type':'select','important':True,'filter':'dropdown','options':['Vertical','Horizontal']},
    {'key':'notes','label':'Notes','type':'text','important':False,'filter':'none','options':[]}], 'primary_search':'asset_id', 'identifier':'asset_id'}


def validate_profile(value):
    if not isinstance(value,dict) or not isinstance(value.get('columns'),list) or not 1 <= len(value['columns']) <= 16:
        raise ValueError('Choose between 1 and 16 inventory columns.')
    columns, keys, labels = [], set(), set()
    for col in value['columns']:
        if not isinstance(col,dict):
            raise ValueError('Each column needs a name and settings.')
        key,label = col.get('key'),col.get('label')
        if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}',key) or key in ('id','inventory_id','custom_values','item_confirmed','data_checked','updated_at') or key in keys:
            raise ValueError('Column keys must be distinct, valid names.')
        if not isinstance(label,str) or not label.strip() or len(label.strip())>120 or label.strip().casefold() in labels:
            raise ValueError('Give each column a different name, from 1 to 120 characters.')
        kind, filtering, options = col.get('type','text'), col.get('filter','none'),col.get('options',[])
        if kind not in ('text','select','checkbox','buttons') or filtering not in ('none','dropdown','buttons') or type(col.get('important',False)) is not bool:
            raise ValueError('Choose valid column types, importance and filters.')
        if not isinstance(options,list) or len(options)>30 or any(not isinstance(opt,str) or not opt.strip() or len(opt)>120 for opt in options):
            raise ValueError('Choose up to 30 valid choices for a column.')
        options=[opt.strip() for opt in options]
        if len({opt.casefold() for opt in options})!=len(options) or (kind in ('select','buttons') and not options):
            raise ValueError('Choice columns need distinct nonempty choices.')
        if key in BASE_FIELDS and kind!='text':
            raise ValueError('Built-in fields use text inputs; add a custom column for choices.')
        columns.append(dict(key=key,label=label.strip(),type=kind,important=col.get('important',False),filter=filtering,options=options))
        keys.add(key);labels.add(label.strip().casefold())
    primary,identifier=value.get('primary_search',columns[0]['key']),value.get('identifier','')
    if primary not in keys or (identifier and identifier not in keys):
        raise ValueError('Choose search and identifier columns from this inventory.')
    if identifier in ('location','quantity','notes'):
        raise ValueError('Choose an item ID or serial number as the identifier.')
    return dict(columns=columns,primary_search=primary,identifier=identifier)


def custom_values(value,profile):
    if value is None:value={}
    if not isinstance(value,dict) or len(value)>32:
        raise ValueError('Custom column values must be an object.')
    definitions={col['key']:col for col in profile['columns'] if col['key'] not in BASE_FIELDS}
    # Retain values for columns hidden/removed from the layout, preventing data loss.
    result={}
    for key,raw in value.items():
        if not isinstance(key,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}',key) or key in BASE_FIELDS or key in ('id','inventory_id','custom_values','item_confirmed','data_checked','updated_at'):
            raise ValueError('Invalid custom column key.')
        if raw is None:raw=''
        if not isinstance(raw,str) or len(raw.strip())>2000:
            raise ValueError('Custom values must be text, up to 2,000 characters.')
        raw=raw.strip();col=definitions.get(key)
        if col and col['type']=='checkbox' and raw:
            choices={'yes':'Yes','true':'Yes','1':'Yes','checked':'Yes','no':'No','false':'No','0':'No','unchecked':'No'}
            if raw.casefold() not in choices:
                raise ValueError(f'{col["label"]}: use Yes or No, or leave blank.')
            raw=choices[raw.casefold()]
        if col and col['type'] in ('select','buttons') and raw:
            choices={opt.casefold():opt for opt in col['options']}
            if key=='orientation':
                raw={'portrait':'Vertical','landscape':'Horizontal'}.get(raw.casefold(),raw)
            if raw.casefold() not in choices:
                raise ValueError(f'{col["label"]}: choose one of {", ".join(col["options"])} or leave blank.')
            raw=choices[raw.casefold()]
        result[key]=raw
    return result


def column_value(row,key):
    return row.get(key,'') if key in BASE_FIELDS else row.get('custom_values',{}).get(key,'')


def profile_identifier(row,profile):
    value=column_value(row,profile['identifier']) if profile.get('identifier') else ''
    return str(value).strip().casefold() if value not in ('',None) else None
