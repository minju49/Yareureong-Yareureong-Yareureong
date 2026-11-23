"""Join only whitespace inside explicitly registered option/action words.

No characters, numbers or option values are inferred. Span offsets refer to
the supplied NFC text. Unknown expressions and existing boundaries survive.
"""
import re

VERSION = 'bom-option-spacing-0.1'
TERMS = ('따뜻하게','따뜻한','뜨겁게','뜨거운','차갑게','차가운','아이스',
         '휘핑','빼주세요','빼줘','빼고','빼기','말고','아니','취소','추가')
SUFFIXES = ('은','는','을','를','도','만','요','으로','로','해주세요','해줘','주세요','해주쇼','주쇼','주세유')


def repair_option_spacing(text):
    spans=[]
    for term in sorted(TERMS,key=len,reverse=True):
        pattern=r'(?<![가-힣A-Za-z0-9])'+r'\s*'.join(map(re.escape,term))
        for match in re.finditer(pattern,text):
            if match.group()==term: continue
            tail=text[match.end():]
            if tail and tail[0].isalpha() and not tail.startswith(SUFFIXES): continue
            if any(match.start()<s['end'] and s['start']<match.end() for s in spans): continue
            spans.append({'start':match.start(),'end':match.end(),'from':match.group(),'to':term,
                'kind':'option_spacing','coordinate_frame':'unicode_normalized_original',
                'reason':'등록된 온도·옵션·정정 표현 내부의 공백만 정리. 문자·수량·옵션 값을 추가하지 않음.'})
    output=text
    for span in sorted(spans,key=lambda s:s['start'],reverse=True):
        output=output[:span['start']]+span['to']+output[span['end']:]
    return output, sorted(spans,key=lambda s:s['start'])
