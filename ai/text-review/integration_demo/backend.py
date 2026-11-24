"""Live Spring/MariaDB adapter. Never replace a failed DB with embedded prices."""
import json
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from urllib.parse import urlsplit


class MenuBackend:
    def __init__(self,base):
        parsed=urlsplit(base)
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError('Spring 서버 기본 주소를 확인해주세요.')
        self.base=base.rstrip('/');self.opener=build_opener(ProxyHandler({}))
    def request(self,path,body=None):
        data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
        req=Request(self.base+path,data=data,headers={'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=10) as r:return json.load(r)
        except HTTPError as exc:
            detail=exc.read(4000).decode('utf-8',errors='replace')
            try:detail=json.loads(detail).get('message') or detail
            except ValueError:pass
            raise RuntimeError('Spring 주문 검증 실패: '+str(detail)) from exc
        except OSError as exc:raise RuntimeError('Spring/MariaDB 연결 실패: '+str(exc)) from exc
    def catalog(self):
        rows=self.request('/api/menu-options')
        if not isinstance(rows,list) or not rows:raise ValueError('Spring 메뉴 응답이 비어 있습니다.')
        seen=set()
        for row in rows:
            if (not isinstance(row,dict) or not isinstance(row.get('menu_id'),str) or row['menu_id'] in seen
                or not isinstance(row.get('name'),str) or type(row.get('price')) is not int or row['price']<0
                or not isinstance(row.get('temperatures'),list) or not isinstance(row.get('sizes'),list)):
                raise ValueError('Spring 메뉴 ID·가격·옵션 형식을 확인해주세요.')
            seen.add(row['menu_id'])
        return rows
    def quote(self,items):return self.request('/api/demo/quote',{'items':items})
    def confirm(self,items,place,key):
        return self.request('/api/demo/orders',{'items':items,'service_type':place,'request_key':key})
