// Flush the last partial buffer BEFORE the stop acknowledgement.
class VoiceRecorder extends AudioWorkletProcessor {
  constructor(options){super();this.buffer=new Float32Array(2048);this.offset=0;this.frames=0;this.active=true;this.limit=options?.processorOptions?.maxFrames||sampleRate*30;this.port.onmessage=({data})=>{if(data.type==='stop'){this.flush();this.active=false;this.port.postMessage({type:'stopped'});}};}
  flush(){if(!this.offset)return;const samples=this.buffer.slice(0,this.offset);this.port.postMessage({type:'samples',samples},[samples.buffer]);this.offset=0;}
  process(inputs){const channels=inputs[0];if(this.active&&channels?.length){for(let i=0;i<channels[0].length;i++){if(this.frames>=this.limit){this.flush();this.active=false;this.port.postMessage({type:'limit'});break;}let v=0;for(const channel of channels)v+=channel[i]/channels.length;this.buffer[this.offset++]=v;this.frames++;if(this.offset===this.buffer.length)this.flush();}}return true;}
}
registerProcessor('bom-voice-recorder',VoiceRecorder);
