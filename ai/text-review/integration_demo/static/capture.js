'use strict';
// The stop acknowledgement follows all samples, including the final partial
// buffer. Duration is measured from captured frames, never a wall-clock timer.
class BomCapture {
  constructor(level,limit){this.level=level;this.limit=limit;this.rec=null;}
  async start(){
    if(this.rec)throw Error('이미 녹음 중입니다.');
    const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    const ctx=new AudioContext();await ctx.resume();let flushed;
    const rec={stream,ctx,rate:ctx.sampleRate,chunks:[],frames:0,stopping:false,flushed:new Promise(r=>{flushed=r;})};this.rec=rec;
    const track=stream.getAudioTracks()[0];rec.metadata={device_label:track.label,actual_settings:track.getSettings?.()||{},audio_context_sample_rate:ctx.sampleRate,separate_denoising_model:'selected on order screen'};
    try{
      rec.input=ctx.createMediaStreamSource(stream);rec.analyser=ctx.createAnalyser();rec.analyser.fftSize=512;
      const save=chunk=>{if(this.rec!==rec)return;const left=Math.max(0,Math.floor(rec.rate*30)-rec.frames);if(left){const x=new Float32Array(chunk.subarray(0,left));rec.chunks.push(x);rec.frames+=x.length;}if(rec.frames>=rec.rate*30&&!rec.stopping)this.limit?.();};
      try{await ctx.audioWorklet.addModule('/recorder-worklet.js');rec.node=new AudioWorkletNode(ctx,'bom-voice-recorder',{processorOptions:{maxFrames:rec.rate*30}});rec.node.port.onmessage=({data})=>{if(data.type==='samples')save(data.samples);if(data.type==='stopped')flushed();if(data.type==='limit')this.limit?.();};rec.worklet=true;}
      catch{rec.node=ctx.createScriptProcessor(4096,1,1);rec.node.onaudioprocess=e=>save(e.inputBuffer.getChannelData(0));}
      rec.mute=ctx.createGain();rec.mute.gain.value=0;rec.input.connect(rec.analyser);rec.input.connect(rec.node);rec.node.connect(rec.mute);rec.mute.connect(ctx.destination);
      const animate=()=>{if(this.rec!==rec||rec.stopping)return;const bins=new Uint8Array(rec.analyser.frequencyBinCount);rec.analyser.getByteFrequencyData(bins);this.level?.(bins);rec.frame=requestAnimationFrame(animate);};animate();
    }catch(e){await this.cancel();throw e;}
  }
  async release(rec){cancelAnimationFrame(rec.frame);rec.stream.getTracks().forEach(t=>t.stop());for(const key of ['input','node','mute'])try{rec[key]?.disconnect();}catch{}await rec.ctx.close().catch(()=>{});if(this.rec===rec)this.rec=null;}
  async cancel(){const rec=this.rec;if(rec){rec.stopping=true;await this.release(rec);}}
  async stop(){const rec=this.rec;if(!rec||rec.stopping)throw Error('진행 중인 녹음이 없습니다.');rec.stopping=true;
    try{if(rec.worklet){rec.node.port.postMessage({type:'stop'});await Promise.race([rec.flushed,new Promise((_,reject)=>setTimeout(()=>reject(Error('녹음 끝부분을 받지 못했습니다. 다시 녹음해주세요.')),2000))]);}}
    finally{await this.release(rec);}
    const duration=rec.frames/rec.rate;if(duration<.2)throw Error(`실제 저장 음성이 ${duration.toFixed(2)}초입니다. 마이크를 확인해주세요.`);
    const source=new Float32Array(rec.frames);let pos=0;for(const x of rec.chunks){source.set(x,pos);pos+=x.length;}
    let pcm=source;
    if(rec.rate!==16000){const render=new OfflineAudioContext(1,Math.ceil(source.length*16000/rec.rate),16000),buffer=render.createBuffer(1,source.length,rec.rate);buffer.copyToChannel(source,0);const node=render.createBufferSource();node.buffer=buffer;node.connect(render.destination);node.start();pcm=(await render.startRendering()).getChannelData(0);}
    return {wav_b64:await BomCapture.base64(BomCapture.wav(pcm,16000)),original_b64:await BomCapture.base64(BomCapture.wav(source,rec.rate)),capture_metadata:{...rec.metadata,actual_duration_s:duration,recorder:rec.worklet?'AudioWorklet':'ScriptProcessor'}};
  }
  static async fromWav(file){
    if(!file||file.size<44||file.size>8000000)throw Error('8MB 이하의 WAV 녹음 파일을 선택해주세요.');
    const bytes=await file.arrayBuffer();
    const header=new TextDecoder('ascii').decode(new Uint8Array(bytes,0,12));
    if(!header.startsWith('RIFF')||header.slice(8)!=='WAVE')throw Error('WAV 녹음 파일을 선택해주세요.');
    const decoder=new OfflineAudioContext(1,1,16000);
    const decoded=await decoder.decodeAudioData(bytes);
    if(decoded.duration<.2||decoded.duration>30)throw Error('0.2초에서 30초 사이의 WAV를 선택해주세요.');
    const mono=new Float32Array(decoded.length);
    for(let ch=0;ch<decoded.numberOfChannels;ch++){
      const data=decoded.getChannelData(ch);
      for(let i=0;i<mono.length;i++)mono[i]+=data[i]/decoded.numberOfChannels;
    }
    return {input_source:'wav',wav_b64:await BomCapture.base64(BomCapture.wav(mono,16000)),
      original_b64:await BomCapture.base64(file),capture_metadata:{file_name:file.name,actual_duration_s:decoded.duration}};
  }
  static wav(pcm,rate){const v=new DataView(new ArrayBuffer(44+pcm.length*2));const str=(p,s)=>{for(let i=0;i<s.length;i++)v.setUint8(p+i,s.charCodeAt(i));};str(0,'RIFF');v.setUint32(4,36+pcm.length*2,true);str(8,'WAVE');str(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,rate,true);v.setUint32(28,rate*2,true);v.setUint16(32,2,true);v.setUint16(34,16,true);str(36,'data');v.setUint32(40,pcm.length*2,true);for(let i=0;i<pcm.length;i++){const x=Math.max(-1,Math.min(1,pcm[i]));v.setInt16(44+i*2,Math.round(x*(x<0?32768:32767)),true);}return new Blob([v.buffer],{type:'audio/wav'});}
  static async base64(blob){const a=new Uint8Array(await blob.arrayBuffer());let s='';for(let i=0;i<a.length;i+=16384)s+=String.fromCharCode(...a.subarray(i,i+16384));return btoa(s);}
}
