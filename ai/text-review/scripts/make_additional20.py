"""Write hand-authored additional development references, without model calls.

These cases were designed AFTER inspecting the school development errors.
They are not a blind or independent final test set.
"""
from pathlib import Path
import hashlib
import html
import json

ROOT=Path(__file__).resolve().parent.parent
TARGET=ROOT/'review_lab'/'additional20_cases.json'
KIND='additional_development_after_school_error_analysis'


def context(menu,q,temp,field,previous):
    questions={'quantity':'몇 잔 드릴까요?','temperature':'따뜻하게 드릴까요, 차갑게 드릴까요?',
               'whipped_cream':'휘핑은 일반, 많이, 적게, 빼기 중 어떻게 드릴까요?'}
    return dict(menu_id=menu,quantity=q,temperature=temp,awaiting=field,
                previous_question=questions[field],previous_user_text=previous)


def reference(menu,q,temp,whip=None,missing=None):
    return {'intent':'clarify' if missing else 'add','items':[{'menu_id':menu,'quantity':q,
        'temperature':temp,'size':'regular','whipped_cream':whip,'custom_note':''}],
        'needs_clarification':bool(missing),'question_required':bool(missing)}


def main():
    rows=[]
    def add(text,category,answer,goal,ctx=None,must_block=False,tokens=()):
        rows.append({'id':f'D{len(rows)+1:02}','category':category,'text':text,
            'context':'custom' if ctx else 'none',**({'context_data':ctx} if ctx else {}),
            'source_kind':KIND,'expected_model':answer,'must_block':must_block,
            'question_goal':goal,'note':'학교의 기존 결과를 본 후에 설계한 추가 개발 점검.',
            'preserve_tokens':list(tokens)})
    add('두 잔이요','다른 메뉴 수량 답변',reference('vanilla_latte',2,'ice'),'아이스 바닐라라떼 2잔. 추가 질문 없음.',context('vanilla_latte',None,'ice','quantity','아바라 주세요'),tokens=('두',))
    add('세 개만요','다른 메뉴 수량 답변',reference('strawberry_latte',3,'ice'),'딸기라떼 3잔. 온도 재질문 없음.',context('strawberry_latte',None,'ice','quantity','딸기라떼 주세요'),tokens=('세',))
    add('하나로 주세요','다른 메뉴 수량 답변',reference('mango_smoothie',1,'ice'),'망고스무디 1잔. 온도 재질문 없음.',context('mango_smoothie',None,'ice','quantity','망고스무디 부탁해요'),tokens=('하나',))
    add('네 잔으로 할게요','다른 메뉴 수량 답변',reference('cafe_latte',4,'hot'),'따뜻한 카페라떼 4잔.',context('cafe_latte',None,'hot','quantity','따뜻한 카페라떼 부탁해요'),tokens=('네',))
    add('차가운 걸로 주세요','다른 메뉴 온도 답변',reference('americano',2,'ice'),'아메리카노 2잔을 차갑게.',context('americano',2,None,'temperature','아메리카노 두 잔 준비해주세요'))
    add('따뜻하게 해주세요','다른 메뉴 온도 답변',reference('vanilla_latte',1,'hot'),'바닐라라떼 1잔을 따뜻하게.',context('vanilla_latte',1,None,'temperature','바닐라라떼 한 잔 부탁해요'))
    add('아이스로 해주세요','다른 메뉴 온도 답변',reference('cafe_latte',3,'ice'),'카페라떼 3잔을 차갑게.',context('cafe_latte',3,None,'temperature','카페라떼 세 잔 부탁해요'))
    add('뜨거운 걸로요','다른 메뉴 온도 답변',reference('americano',1,'hot'),'아메리카노 1잔을 따뜻하게.',context('americano',1,None,'temperature','아메리카노 한 잔 부탁해요'))
    add('빼주세요','휘핑 짧은 답변',reference('cafe_mocha',2,'hot','none'),'따뜻한 카페모카 2잔, 휘핑 빼기.',context('cafe_mocha',2,'hot','whipped_cream','따뜻한 카페모카 두 잔 준비해주세요'),tokens=('빼',))
    add('보통으로요','휘핑 짧은 답변',reference('cafe_mocha',1,'hot','normal'),'따뜻한 카페모카 1잔, 휘핑 일반.',context('cafe_mocha',1,'hot','whipped_cream','따뜻한 카페모카 한 잔 부탁해요'))
    add('많이 올려주세요','휘핑 짧은 답변',reference('cafe_mocha',2,'ice','extra'),'아이스 카페모카 2잔, 휘핑 많이.',context('cafe_mocha',2,'ice','whipped_cream','아이스 카페모카 두 잔 부탁해요'))
    add('조금만 올려줘요','휘핑 짧은 답변',reference('cafe_mocha',1,'ice','light'),'아이스 카페모카 1잔, 휘핑 적게.',context('cafe_mocha',1,'ice','whipped_cream','아이스 카페모카 한 잔 준비해주세요'))
    add('차가운 바닐라라떼로 할게요','누락 수량',reference('vanilla_latte',None,'ice',missing='quantity'),'수량만 질문. 임의로 1잔을 넣지 않음.',must_block=True)
    add('아메리카노 두 잔 준비해주세요','누락 온도',reference('americano',2,None,missing='temperature'),'온도만 질문. 수량 재질문 없음.',must_block=True,tokens=('두',))
    add('딸기라떼 세 잔 부탁해요','Only Ice',reference('strawberry_latte',3,'ice'),'딸기라떼 3잔. 온도 재질문 없음.',tokens=('세',))
    add('아이스 카페모카 한 잔 부탁해요','누락 휘핑',reference('cafe_mocha',1,'ice',missing='whipped_cream'),'휘핑만 질문. 수량·온도 재질문 없음.',must_block=True,tokens=('한',))
    add('라떼 종류는 아무거나 한 잔이요','모호한 메뉴',None,'어떤 라떼인지 질문. 메뉴를 임의 선택하지 않음. 정확한 JSON 하나로 채점하지 않고 보류 여부와 질문을 직접 검토.',must_block=True,tokens=('한',))
    add('따뜻한 망고스무디 한 잔 주세요','판매 불가 온도',None,'망고스무디는 차갑게만 제공한다고 안내하고 확인. 따뜻한 스무디를 확정하지 않음.',must_block=True,tokens=('한',))
    add('그 음료 하나만 빼주세요','대상 불명확',None,'빈 문맥이므로 어떤 메뉴인지 확인. 임의 삭제·추가 금지.',must_block=True,tokens=('하나','빼'))
    add('아아 한 잔 말고 아바라 두 잔으로 바꿔줘','복합 정정 보존',None,'정정·수량을 보존하고 별도 확인. 이번 단일 추가 주문 검증 범위에서는 보류. 실제 장바구니 수정 성공으로 집계하지 않음.',must_block=True,tokens=('한','말고','두','바꿔'))
    data={'version':'bom-additional20-draft-1.0','source_kind':KIND,
        'annotation_status':'사용자 정책으로 먼저 작성한 추가 개발 정답 초안. 팀원의 독립 검수 전.',
        'scope':'기존 학교 오답을 본 후 설계. 미사용 최종 시험셋이 아니다. 16개 슬롯·질문 유무 채점, 4개는 보류 여부와 질문 내용 수동 검토. 문맥은 선택한 직전 질문의 확정 사실이며 정답을 미리 채우지 않는다.',
        'case_count':len(rows),'cases':rows}
    TARGET.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    sha=hashlib.sha256(TARGET.read_bytes()).hexdigest()
    names={'americano':'아메리카노','cafe_latte':'카페라떼','vanilla_latte':'바닐라라떼','strawberry_latte':'딸기라떼','mango_smoothie':'망고스무디','cafe_mocha':'카페모카'}
    body=[]
    for c in rows:
        x=c.get('context_data');before='새 주문 · 직전 질문 없음'
        if x:
            before=f"{names[x['menu_id']]} / 수량 {x['quantity'] or '미정'} / 온도 {x['temperature'] or '미정'} / 직전 질문: {x['previous_question']}"
        body.append('<tr><td>'+c['id']+'</td><td>'+html.escape(before)+'</td><td><strong>'+html.escape(c['text'])+'</strong></td><td>'+html.escape(c['question_goal'])+'</td></tr>')
    page='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>새 20문장 · 먼저 정답 확인</title><style>body{font:19px/1.65 system-ui,sans-serif;color:#222;background:#fff;margin:30px auto;max-width:1200px;padding:0 22px}h1{font-size:30px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;padding:13px;text-align:left;vertical-align:top}th{background:#eee}small{word-break:break-all}button{font:inherit;padding:10px 20px}@media print{button{display:none}tr{break-inside:avoid}body{font-size:12px}}</style><h1>새 20문장 — 실행 전에 정답부터 확인</h1><p>학교에서 나온 오답을 바탕으로 추가한 개발 점검입니다. 독립 최종 평가가 아닙니다. 아래 정답은 팀원 검수 전 초안입니다.</p><p><b>먼저 할 일:</b> 팀원이 문장과 정답을 읽고 이상한 부분을 표시하세요. 수정한 경우 모델 결과를 보기 전에 새 정답표로 저장하세요. 첫 12개는 <b>화면에 적힌 직전 질문을 받은 상황에서 하는 짧은 답변</b>입니다.</p><p>문장 보정 알고리즘과 Qwen 프롬프트는 기존 0.5 그대로입니다. 16개는 메뉴·수량·온도·휘핑·의도·질문 유무를 비교합니다. 마지막 4개는 정해진 JSON 하나로 채점하지 않고 보류 여부와 질문을 사람이 확인합니다.</p><button onclick="print()">인쇄 / PDF 저장</button><table><thead><tr><th>ID</th><th>주어진 문맥</th><th>입력할 문장</th><th>먼저 정한 기대 결과</th></tr></thead><tbody>'''+''.join(body)+f'</tbody></table><p>입력 정답표 SHA256: <small>{sha}</small></p><p>자동 20문장 비교는 마이크를 쓰지 않습니다. 실제 음성은 별도 마이크 시험에서 녹음합니다. 장바구니·TTS·결제는 이번 점검 범위에 없습니다.</p></html>'
    (ROOT/'새20문장_정답먼저보기.html').write_text(page,encoding='utf-8')
    print(str(TARGET));print('SHA256: '+sha)


if __name__=='__main__':main()
