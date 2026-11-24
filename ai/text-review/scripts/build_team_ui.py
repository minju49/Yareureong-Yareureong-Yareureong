"""Apply API bindings to the team's exact UI, retaining layout and menu photos."""
from pathlib import Path
import argparse
import shutil

ROOT=Path(__file__).resolve().parent.parent


def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);args=p.parse_args()
    text=args.source.read_text(encoding='utf-8')
    if 'const menus=' not in text or 'reset();</script>' not in text:raise ValueError('팀 UI의 구조가 달라 자동 수정하지 않습니다.')
    text=text.replace('reset();</script>','</script>')
    text=text.replace('s.cart[${j}].q++;draw()','changeQuantity(${j},1)')
    text=text.replace('시연용: 예시로 주문을 연습할 수 있어요.','마이크로 말하거나 문장 예시를 학교 서버에 보내 주문할 수 있어요.')
    text=text.replace('예시로 주문 연습하기','문장 예시로 주문하기').replace('연습 메뉴 접기','문장 예시 접기')
    panel='''<section style="margin:16px auto;padding:18px;max-width:1250px;border:1px solid #cab79e;background:#fffaf0;border-radius:14px"><p id="connection-status" role="status">실제 메뉴 서버를 연결하고 있어요.</p><button onclick="replayGuide()">안내 다시 듣기</button><details><summary>담당자 연결 설정·실행 정보</summary><p>Spring 주소 <input id="spring-address" style="min-width:300px;font:inherit" placeholder="http://서버IP:8080"></p><p>잡음 서버 주소 <input id="noise-address" style="min-width:300px;font:inherit" placeholder="준비된 경우 http://서버IP:8058"></p><button onclick="saveConnections()">연결 확인·저장</button><p>문장으로 주문 <input id="typed-order" style="min-width:300px;font:inherit" placeholder="아아 한 잔 주세요"><button onclick="sendTypedOrder()">학교 Qwen에 보내기</button></p><pre id="runtime-info" style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px"></pre></details></section>'''
    wav_controls = '<p><label>WAV 녹음 주문 <input id="wav-order" type="file" accept=".wav,audio/wav"></label> <button onclick="sendWavOrder()">음성 주문 시험</button></p><p id="wav-result" role="status"></p>'
    panel = panel.replace('<pre id="runtime-info"', wav_controls + '<pre id="runtime-info"')
    # The original has no body tag; insert before its header.
    where=text.index('<header')
    text=text[:where]+panel+text[where:]
    text=text.replace('</html>','<script src="/capture.js"></script><script src="/adapter.js"></script></html>')
    text='\n'.join(line.rstrip() for line in text.splitlines())+'\n'
    target=ROOT/'integration_demo'/'static'/'index.html';target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
    shutil.copy2(ROOT/'voice_lab'/'static'/'recorder-worklet.js',target.parent/'recorder-worklet.js')
    print('Team UI API bindings written: '+str(target))


if __name__=='__main__':main()
