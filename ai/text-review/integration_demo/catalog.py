"""Explicit bridge from the frozen six-menu AI experiment to the team catalog."""
import copy
from review import POLICY,exact_mentions,quantity_info,temperature_flags

# The previous experiment used a shorter strawberry name. This is a catalog
# mapping, not a claim that 61-menu voice recognition was evaluated.
BRIDGE={'strawberry_latte':'strawberry_fruit_latte'}
REVERSE={v:k for k,v in BRIDGE.items()}


def db_id(ident):return BRIDGE.get(ident,ident)
def lab_id(ident):return REVERSE.get(ident,ident)


def to_backend(item):
    out={k:copy.deepcopy(item.get(k)) for k in ('menu_id','quantity','temperature','size','whipped_cream','custom_note')}
    out['menu_id']=db_id(out['menu_id']);out['custom_note']=out['custom_note'] or '';return out


def cart_item(item):
    return {k:copy.deepcopy(item.get(k)) for k in ('menu_id','quantity','temperature','size','whipped_cream','custom_note')}


def supported(catalog):
    indexed={r['menu_id']:r for r in catalog}
    return [{'lab_menu_id':m['id'],**indexed[db_id(m['id'])]} for m in POLICY['menus'] if db_id(m['id']) in indexed]
