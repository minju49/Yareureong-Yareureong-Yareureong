'use strict';
// Adapt the team's interface; all committed cart state and prices come back
// from the Python order session after live Spring/MariaDB validation.
let serverState=null,serverInfo=null,serverBusy=false,dbCatalog=[],lastVoice=null,noiseMode='off';
let guidePlayer=new Audio(),lastGuideUrl='';
const escapeBom=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const originalDraw=draw,originalReset=reset,originalGo=go;
const capture=new BomCapture(bins=>{app.querySelectorAll('.wave i').forEach((bar,i)=>{const p=1+i*4;bar.style.height=(6+Math.max(0,(bins[p]||0)-24)*.29)+'px';});},()=>{if(mic.state==='active')void finishListening();});
function banner(message,error=false){const el=document.querySelector('#connection-status');el.textContent=message;el.style.color=error?'#8b251b':'#22513e';}
async function remote(path,body){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),180000);try{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});const value=await r.json();if(!r.ok)throw Error(value.error||'요청 실패');return value;}catch(e){if(e.name==='AbortError')throw Error('처리가 오래 걸립니다. 실행 창을 확인해주세요.');throw e;}finally{clearTimeout(timer);}}
function requestData(extra){if(!serverState)throw Error('먼저 메뉴 서버 연결을 확인해주세요.');return {session_id:serverState.session_id,revision:serverState.revision,request_id:crypto.randomUUID(),...extra};}
function applyState(state){serverState=state;const oldPage=s.page;
  s.cart=state.cart.map(x=>{const i=dbCatalog.findIndex(m=>m.menu_id===x.menu_id);if(i<0)throw Error('주문 메뉴가 현재 DB 목록에 없습니다.');menus[i][1]=x.unit_price;return {i,q:x.quantity,t:x.temperature==='ice'?'차갑게':x.temperature==='hot'?'따뜻하게':'',cream:x.whipped_cream};});
  s.pending=state.pending?{kind:'server'}:null;s.msg=state.message;
  if(state.phase==='review')s.page=3;if(state.phase==='complete'){s.page=5;s.number=state.receipt.order_id.slice(0,8);s.receipt='MariaDB에 시연 주문이 저장됐어요. 실제 결제는 진행되지 않습니다.';}
  if(state.diagnostics?.input_text)lastVoice=state.diagnostics;
  guidePlayer.pause();lastGuideUrl=state.guide_audio?.audio_url||'';
  if(lastGuideUrl){guidePlayer.src=lastGuideUrl;guidePlayer.play().catch(()=>{});}
  draw();if(state.pending)document.querySelector('#question')?.scrollIntoView({block:'center'});
  if(oldPage!==s.page)window.scrollTo(0,0);
  void refreshRuntimeInfo();
}
async function action(value,text=false){if(serverBusy)return;serverBusy=true;voice.state='busy';draw();try{const result=await remote(text?'/api/integration/text':'/api/integration/action',requestData(value));voice.state='idle';applyState(result);return result;}catch(e){voice.state='idle';s.msg=e.message;banner(e.message,true);draw();}finally{serverBusy=false;voice.state='idle';draw();}}
draw=function(){originalDraw();if(serverBusy)app.querySelectorAll('button').forEach(b=>{b.disabled=true;});};
go=async function(page){if(serverBusy)return;if(page===2&&s.place&&serverState){await action({action:'place',place:s.place.includes('포장')?'takeaway':'dine_in'});}originalGo(page);};
reset=async function(){if(serverBusy)return;originalReset();if(serverState)await action({action:'reset'});};
ask=function(i){if(serverBusy||s.pending)return;openOptions(i);};
addOptions=async function(){if(serverBusy)return;const menu=dbCatalog[opt.i];const cream=menu.menu_id==='cafe_mocha'?(opt.cream||'normal'):null;
  const item={menu_id:menu.menu_id,quantity:opt.q,temperature:opt.t==='차갑게'?'ice':opt.t==='따뜻하게'?'hot':null,size:'regular',whipped_cream:cream,custom_note:''};
  if(menu.temperatures.length&&!item.temperature){dlg.querySelector('#opt-error').textContent='온도를 선택해주세요.';return;}
  if(menu.menu_id==='cafe_mocha'&&!opt.cream){dlg.querySelector('#opt-error').textContent='휘핑 선택을 눌러주세요.';return;}
  const result=await action({action:opt.j===undefined?'add':'edit',index:opt.j,item});if(result)dlg.close();};
const originalPaintOptions=paintOptions;
paintOptions=function(){originalPaintOptions();if(dbCatalog[opt.i]?.menu_id==='cafe_mocha'){
  const choices=[['normal','일반'],['extra','많이'],['light','적게'],['none','빼기']];const box=document.createElement('div');box.innerHTML='<h3>휘핑</h3><div class="row">'+choices.map(([value,label])=>btn(label,`opt.cream='${value}';paintOptions()`,'',`aria-pressed="${opt.cream===value}"`)).join('')+'</div>';dlg.querySelector('.option-body').append(box);
}};
question=function(){const p=serverState?.pending;if(!p)return '';const title=escapeBom(p.question);return `<section id="question" class="panel question-card"><h2>${title}</h2><div class="row">${p.choices.map(x=>btn(escapeBom(x.label),`answerServer(${JSON.stringify(x.value).replace(/"/g,'&quot;')})`,'primary')).join('')}${btn('이 선택 취소','cancel()')}</div></section>`;};
window.answerServer=value=>action({action:'answer',value});
cancel=()=>action({action:'cancel_pending'});
window.changeQuantity=(index,delta)=>action({action:'quantity',index,delta});
removeAsk=function(index,q){modal('음료를 뺄까요?',`${name(s.cart[index])} ${q}${unit(s.cart[index].i)}을 뺄까요?`,btn('네, 빼 주세요',`dlg.close();removeFromServer(${index},${q})`,'primary'));};
window.removeFromServer=(index,quantity)=>action({action:'remove',index,quantity});
pay=async function(fail){if(fail){s.pay='fail';draw();return;}s.pay='busy';draw();const result=await action({action:'confirm'});if(!result){s.pay='fail';draw();}};
runVoice=function(k){if(k<0){s.msg='이 연결본에서는 실제 입력 결과를 확인합니다. 마이크 또는 주문 문장을 사용해주세요.';draw();return;}action({text:speech[k][0]},true);};
voicePanel=function(){if(!lastVoice)return '';const stt=lastVoice.stt;const raw=lastVoice.input_text;const reviewed=lastVoice.review?.reviewed_text;return `<div class="voice-result"><p><strong>${stt?'SenseVoice 인식':'입력 문장'}</strong>: ${escapeBom(raw)}</p>${reviewed&&reviewed!==raw?`<p>재점검: ${escapeBom(reviewed)}</p>`:''}<p>${escapeBom(s.msg)}</p><details><summary>실제 실행 정보</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px">${escapeBom(JSON.stringify(lastVoice,null,2))}</pre></details></div>`;};
micPanel=function(){return `<div class="mic-box mic-${mic.state}"><h3>말로 주문하기</h3><p role="status" class="mic-state">${escapeBom(mic.message||'버튼을 누르고 말씀해 주세요.')}</p><div class="wave" aria-hidden="true">${'<i></i>'.repeat(24)}</div><div class="row">${mic.state==='active'?btn('말하기 끝내기','finishListening()','primary'):mic.state==='processing'?'':btn('마이크 켜고 말하기','startMic()','primary')}</div><p><small>현재 음성 주문: 아메리카노·카페라떼·바닐라라떼·딸기라떼·망고스무디·카페모카. 다른 메뉴는 화면에서 골라주세요.</small></p><label>잡음 처리 <select onchange="noiseMode=this.value" ${mic.state==='idle'?'':'disabled'}><option value="off" ${noiseMode==='off'?'selected':''}>기본 · 별도 모델 끄기</option><option value="zipenhancer" ${noiseMode==='zipenhancer'?'selected':''}>ZipEnhancer</option><option value="mossgan" ${noiseMode==='mossgan'?'selected':''}>MossFormerGAN</option><option value="mossformer2_zip" ${noiseMode==='mossformer2_zip'?'selected':''}>화자 분리 → ZipEnhancer</option></select></label><small>녹음은 이 PC에서 인식하고, 주문 문장은 학교 서버로 보냅니다.</small></div>`;};
startMic=async function(){if(serverBusy||mic.state!=='idle')return;guidePlayer.pause();mic.state='waiting';mic.message='마이크 사용을 허용해주세요.';draw();try{await capture.start();mic.state='active';mic.message='듣고 있어요. 말씀을 마치면 끝내기를 눌러주세요.';draw();}catch(e){mic.state='idle';mic.message=e.message;draw();}};
stopMic=function(refresh=true){void capture.cancel();mic.state='idle';if(refresh){mic.message='마이크를 껐어요.';draw();}};
finishListening=async function(){if(mic.state!=='active')return;mic.state='processing';mic.message='말씀하신 주문을 확인하고 있어요.';serverBusy=true;voice.state='busy';draw();try{const audio=await capture.stop();const result=await remote('/api/integration/speech',requestData({...audio,noise_mode:noiseMode}));voice.state='idle';applyState(result);mic.message=result.message;}catch(e){mic.message=e.message;s.msg=e.message;banner(e.message,true);}finally{mic.state='idle';voice.state='idle';serverBusy=false;draw();}};
window.sendWavOrder=async()=>{
  if(serverBusy||mic.state!=='idle')return;
  guidePlayer.pause();serverBusy=true;mic.state='processing';mic.message='WAV 주문을 확인하고 있어요.';draw();
  try{
    const file=document.querySelector('#wav-order').files[0];
    const audio=await BomCapture.fromWav(file);
    const result=await remote('/api/integration/speech',requestData({...audio,noise_mode:noiseMode}));
    applyState(result);mic.message=result.message;
    document.querySelector('#wav-result').textContent='SenseVoice 인식 · '+result.speech.stt.text+' / '+result.message;
  }catch(e){document.querySelector('#wav-result').textContent=e.message;mic.message=e.message;}
  finally{mic.state='idle';serverBusy=false;draw();}
};
window.sendTypedOrder=()=>{const el=document.querySelector('#typed-order');const text=el.value.trim();if(text)action({text},true);};
window.replayGuide=()=>{if(lastGuideUrl){guidePlayer.currentTime=0;guidePlayer.play().catch(()=>banner('브라우저의 소리 재생 권한을 확인해주세요.',true));}};
window.saveConnections=async()=>{try{const value=await remote('/api/integration/settings',{spring_base_url:document.querySelector('#spring-address').value,noise_base_url:document.querySelector('#noise-address').value});banner(`메뉴 서버 연결 확인 · ${value.menu_count}개 메뉴. 화면을 다시 준비합니다.`);await boot();}catch(e){banner(e.message,true);}};
async function refreshRuntimeInfo(){try{const value=await(await fetch('/api/integration/info')).json();document.querySelector('#runtime-info').textContent=JSON.stringify(value,null,2);}catch{}}
async function boot(){try{serverInfo=await (await fetch('/api/integration/info')).json();document.querySelector('#spring-address').value=serverInfo.spring_base_url;document.querySelector('#noise-address').value=serverInfo.noise.base_url;document.querySelector('#runtime-info').textContent=JSON.stringify(serverInfo,null,2);
  const state=await remote('/api/integration/session',{});dbCatalog=await (await fetch('/api/integration/catalog')).json();if(!Array.isArray(dbCatalog))throw Error(dbCatalog.error||'메뉴를 불러오지 못했어요.');
  const originals=menus.map((x,i)=>({name:x[0],photo:photos[i],group:group[i]}));menus.splice(0,menus.length,...dbCatalog.map(x=>[x.name,x.price,x.menu_id]));cold.splice(0,cold.length,...dbCatalog.flatMap((m,i)=>m.temperatures.length===1&&m.temperatures[0]==='ice'?[i]:[]));hot.splice(0,hot.length,...dbCatalog.flatMap((m,i)=>m.temperatures.length===1&&m.temperatures[0]==='hot'?[i]:[]));
  for(let i=0;i<dbCatalog.length;i++){const match=originals.find(x=>x.name===dbCatalog[i].name);if(match){photos[i]=match.photo;group[i]=match.group;}}
  originalReset();applyState(state);banner(`연결본 ${serverInfo.version} · MariaDB 메뉴 ${dbCatalog.length}개 불러옴 · 음성 주문 6개 메뉴 · 실제 결제 없음`);
}catch(e){banner(e.message+' · 담당자 연결 설정에서 Spring 주소를 확인해주세요.',true);app.innerHTML='<section class="panel"><h1>메뉴 서버에 연결해주세요</h1><p>위 담당자 연결 설정에 Spring 서버 주소를 입력하고 연결 확인을 눌러주세요.</p></section>';}}
void boot();
