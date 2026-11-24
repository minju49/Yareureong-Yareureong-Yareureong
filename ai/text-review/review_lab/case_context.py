"""Validate explicit pending-question input, independently of reference labels."""
import copy
from review import MENUS,POLICY

KEYS={'menu_id','quantity','temperature','awaiting','previous_question','previous_user_text'}


def resolve_context(case,presets):
    name=case.get('context')
    if name!='custom':
        if not isinstance(name,str) or name not in presets or 'context_data' in case:
            raise ValueError('문맥 이름 또는 context_data를 확인해주세요: '+str(case.get('id','')))
        return copy.deepcopy(presets[name])
    value=case.get('context_data')
    if not isinstance(value,dict) or set(value)!=KEYS:
        raise ValueError('custom 문맥에는 메뉴·수량·온도·직전 질문 정보를 명시해주세요.')
    if value['menu_id'] not in MENUS: raise ValueError('문맥의 메뉴 ID가 등록되어 있지 않습니다.')
    menu=MENUS[value['menu_id']]
    q=value['quantity'];temp=value['temperature'];field=value['awaiting']
    if q is not None and (type(q) is not int or not POLICY['quantity_min']<=q<=POLICY['quantity_max']):
        raise ValueError('문맥의 수량은 1~9 정수 또는 null이어야 합니다.')
    if temp is not None and temp not in menu['temperatures']:
        raise ValueError('문맥의 이미 확인한 온도가 메뉴와 맞지 않습니다.')
    if field not in ('quantity','temperature','whipped_cream'):raise ValueError('질문 중인 필드가 잘못되었습니다.')
    if field=='quantity' and q is not None:raise ValueError('수량 질문의 미확정 수량을 정답으로 미리 채우지 않습니다.')
    if field=='temperature' and (temp is not None or q is None or len(menu['temperatures'])==1):
        raise ValueError('온도 질문은 수량이 알려지고 온도가 미정인 양쪽 온도 메뉴여야 합니다.')
    if field=='whipped_cream' and (not menu['ask_whip'] or q is None or temp is None):
        raise ValueError('휘핑 질문은 해당 메뉴의 수량·온도가 알려져야 합니다.')
    for key,limit in (('previous_question',300),('previous_user_text',500)):
        if not isinstance(value[key],str) or not value[key].strip() or len(value[key])>limit:
            raise ValueError('직전 질문/발화 내용을 확인해주세요.')
    return copy.deepcopy(value)
