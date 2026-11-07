"""Small validated defaults for document workspaces; no document/customer data."""
import copy,math

NUMBERS=dict(scan_dpi=(50,9600),copies=(1,100),margin=(0,100),paper_width=(50,1000),paper_height=(50,1000),
             scale=(5,400),brightness=(0,3),contrast=(0,3),sharpness=(0,3),quality=(0,2),
             card_width=(10,250),card_height=(10,250),spacing=(0,100),top=(0,250),pairs_per_sheet=(1,10))
ENUMS=dict(color=('color','gray','mono'),scale_mode=('actual','fit','custom'),align=('left','center','right'))

def validate_settings(value):
    if not isinstance(value,dict):raise ValueError('Expected workspace settings')
    result={}
    for key,v in value.items():
        if key in NUMBERS:
            low,high=NUMBERS[key]
            if type(v) not in (float,int) or not math.isfinite(v) or not low<=v<=high:raise ValueError('Invalid '+key)
            if key in ('scan_dpi','copies','pairs_per_sheet','quality') and int(v)!=v:raise ValueError('Expected whole '+key)
        elif key in ENUMS:
            if v not in ENUMS[key]:raise ValueError('Invalid '+key)
        elif key in ('landscape','center','actual_card'):
            if type(v) is not bool:raise ValueError('Expected boolean '+key)
        elif key=='paper':
            if not isinstance(v,str) or not v.strip() or len(v)>128 or '\x00' in v:raise ValueError('Invalid paper')
        elif key=='paper_mm':
            if not isinstance(v,(list,tuple)) or len(v)!=2 or any(type(x) not in (float,int) or not math.isfinite(x) or not 50<=x<=1000 for x in v):raise ValueError('Invalid paper size')
        else:continue
        result[key]=copy.deepcopy(v)
    return result

def validate_defaults(value):
    if not isinstance(value,dict):raise ValueError('Expected workspace defaults')
    result={};invalid=False
    for key,settings in value.items():
        try:
            if key not in ('copy','nid'):raise ValueError('Unknown workspace')
            result[key]=validate_settings(settings)
        except (ValueError,TypeError):invalid=True
    return result,'invalid workspace defaults ignored' if invalid else None
