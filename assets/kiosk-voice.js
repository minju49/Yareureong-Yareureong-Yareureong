const kioskVoiceEnabled = location.pathname.endsWith('/kiosk/');
let kioskDenoiseMode = 'off';
const kioskModes = {off:'OFF · 전처리만',zipenhancer:'ON · ZipEnhancer',auto:'AUTO · 자동 선택',
  parallel:'두 모델 병렬',moss_to_zip:'MossFormerGAN → ZipEnhancer',zip_to_moss:'ZipEnhancer → MossFormerGAN'};
const escapeVoiceText = value => String(value).replace(/[&<>"']/g, char => ({
  '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
})[char]);

function kioskMicControls() {
  if (!kioskVoiceEnabled) return '<small>음성은 저장하거나 전송하지 않아요.</small>';
  const modes = Object.entries(kioskModes).map(([value, label]) =>
    `<option value="${value}" ${value === kioskDenoiseMode ? 'selected' : ''}>${label}</option>`).join('');
  return `<label>잡음 제거 <select aria-label="잡음 제거" onchange="kioskDenoiseMode=this.value" ${mic.state === 'idle' ? '' : 'disabled'}>${modes}</select></label>
    <p><small>녹음은 이 PC의 음성 서버에서 처리해요.</small></p>`;
}

async function attachKioskRecorder(context, source, token) {
  await context.audioWorklet.addModule('./assets/recorder-worklet.js');
  if (token !== mic.token) return;
  const recorder = new AudioWorkletNode(context, 'maeum-recorder', {numberOfOutputs:0});
  mic.recorder = recorder;
  mic.chunks = [];
  recorder.port.onmessage = ({data}) => {
    if (token !== mic.token) return;
    if (data.type === 'samples') mic.chunks.push(data.samples);
    if (data.type === 'stopped') mic.flush?.();
  };
  source.connect(recorder);
}

function encodeKioskWav(chunks, rate) {
  const frames = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  if (!frames) throw new Error('녹음된 음성이 없어요. 다시 말해 주세요.');
  const data = new DataView(new ArrayBuffer(44 + 2 * frames));
  const tag = (offset, str) => [...str].forEach((char, i) => data.setUint8(offset + i, char.charCodeAt(0)));
  tag(0,'RIFF'); data.setUint32(4, data.byteLength - 8, true); tag(8,'WAVE'); tag(12,'fmt ');
  data.setUint32(16,16,true); data.setUint16(20,1,true); data.setUint16(22,1,true);
  data.setUint32(24,rate,true); data.setUint32(28,rate*2,true);
  data.setUint16(32,2,true); data.setUint16(34,16,true);
  tag(36,'data'); data.setUint32(40,2*frames,true);
  let offset = 44;
  for (const chunk of chunks) for (const sample of chunk) {
    const value = Math.max(-1, Math.min(1, sample));
    data.setInt16(offset, value * (value < 0 ? 32768 : 32767), true);
    offset += 2;
  }
  return new Blob([data.buffer], {type:'audio/wav'});
}

async function submitKioskRecording() {
  if (mic.state !== 'active' || !mic.recorder) return;
  const token = mic.token;
  const controller = mic.request = new AbortController();
  const rate = mic.ctx.sampleRate;
  const mode = kioskDenoiseMode;
  clearTimeout(mic.maxRecording);
  mic.state = 'processing';
  mic.message = '녹음을 처리하고 있어요.';
  draw();
  const timeout = setTimeout(() => controller.abort(), 75000);
  try {
    await new Promise((resolve, reject) => {
      const flushTimeout = setTimeout(() => reject(new Error('녹음을 마치지 못했어요. 다시 말해 주세요.')), 2000);
      mic.flush = () => { clearTimeout(flushTimeout); resolve(); };
      mic.recorder.port.postMessage({type:'stop'});
    });
    if (token !== mic.token) return;
    const clip = encodeKioskWav(mic.chunks, rate);
    stopKioskCapture();
    const form = new FormData();
    form.append('file', clip, 'order.wav');
    form.append('mode', mode);
    const response = await fetch('./api/speech', {method:'POST', body:form, signal:controller.signal});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '음성을 처리하지 못했어요.');
    if (token !== mic.token) return;
    const route = result.selected === 'off' ? 'OFF · 전처리만' : kioskModes[result.selected];
    mic.message = result.text ? `이렇게 들었어요: ${result.text}` : '말씀을 듣지 못했어요. 다시 말해 주세요.';
    mic.route = `${route} · 잡음 제거 ${result.processing_seconds.toFixed(2)}초`;
  } catch (error) {
    if (token !== mic.token) return;
    mic.message = error.name === 'AbortError' ? '처리 시간이 길어졌어요. 다시 말해 주세요.' : error.message;
  } finally {
    clearTimeout(timeout);
    if (token === mic.token) {
      stopKioskCapture();
      mic.request = null;
      mic.state = 'idle';
      draw();
    }
  }
}

function stopKioskCapture() {
  clearTimeout(mic.maxRecording);
  cancelAnimationFrame(mic.frame);
  mic.flush?.();
  mic.flush = null;
  mic.recorder?.port.close();
  mic.recorder?.disconnect();
  mic.recorder = null;
  mic.chunks = null;
  mic.stream?.getTracks().forEach(track => track.stop());
  mic.ctx?.close().catch(() => {});
  mic.stream = null;
  mic.ctx = null;
}
