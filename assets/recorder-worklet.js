class MaeumRecorder extends AudioWorkletProcessor {
  constructor() {
    super(); this.buffer = new Float32Array(4096); this.offset = 0; this.active = true;
    this.port.onmessage = ({data}) => {
      if (data.type === 'stop') { this.flush(); this.active = false; this.port.postMessage({type:'stopped'}); }
    };
  }
  flush() {
    if (!this.offset) return;
    const samples = this.buffer.slice(0, this.offset);
    this.port.postMessage({type:'samples',samples}, [samples.buffer]); this.offset = 0;
  }
  process(inputs) {
    const channels = inputs[0];
    if (this.active && channels?.length) {
      const length = channels[0].length;
      for (let i = 0; i < length; i++) {
        let sample = 0; for (const channel of channels) sample += channel[i] / channels.length;
        this.buffer[this.offset++] = sample;
        if (this.offset === this.buffer.length) this.flush();
      }
    }
    return true;
  }
}
registerProcessor('maeum-recorder', MaeumRecorder);
