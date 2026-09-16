// Synthesized sound effects: no audio files to download. One shared AudioContext,
// created lazily after the first user gesture as browsers require.
import { settings } from "./settings.js";

let ctx = null;

function context() {
  if (!ctx) {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return null;
    ctx = new Ctor();
  }
  if (ctx.state === "suspended") ctx.resume().catch(() => {});
  return ctx;
}

function envelope(ac, peak, attack, decay) {
  const gain = ac.createGain();
  const t = ac.currentTime;
  gain.gain.setValueAtTime(0.0001, t);
  gain.gain.exponentialRampToValueAtTime(Math.max(0.0002, peak), t + attack);
  gain.gain.exponentialRampToValueAtTime(0.0001, t + attack + decay);
  gain.connect(ac.destination);
  return gain;
}

function tone(freq, { type = "sine", attack = 0.005, decay = 0.12, peak = 0.3, slideTo = null, delay = 0 } = {}) {
  const ac = context();
  if (!ac) return;
  const start = () => {
    const volume = settings.volume / 100;
    if (volume <= 0) return;
    const osc = ac.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, ac.currentTime);
    if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, ac.currentTime + attack + decay);
    osc.connect(envelope(ac, peak * volume, attack, decay));
    osc.start();
    osc.stop(ac.currentTime + attack + decay + 0.02);
  };
  delay ? setTimeout(start, delay) : start();
}

function noise({ decay = 0.09, peak = 0.35, freq = 2400 } = {}) {
  const ac = context();
  const volume = settings.volume / 100;
  if (!ac || volume <= 0) return;
  const length = Math.floor(ac.sampleRate * (decay + 0.02));
  const buffer = ac.createBuffer(1, length, ac.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < length; i++) data[i] = Math.random() * 2 - 1;
  const src = ac.createBufferSource();
  src.buffer = buffer;
  const filter = ac.createBiquadFilter();
  filter.type = "bandpass";
  filter.frequency.value = freq;
  src.connect(filter);
  filter.connect(envelope(ac, peak * volume, 0.004, decay));
  src.start();
}

export const sound = {
  unlock: context,
  card: () => noise({ decay: 0.08, freq: 2800 }),
  draw: () => noise({ decay: 0.06, peak: 0.2, freq: 1600 }),
  turn: () => { tone(660, { decay: 0.1, peak: 0.18 }); tone(880, { decay: 0.14, peak: 0.18, delay: 90 }); },
  uno: () => { tone(520, { type: "triangle", decay: 0.12 }); tone(780, { type: "triangle", decay: 0.2, delay: 110 }); },
  bad: () => tone(220, { type: "square", decay: 0.18, peak: 0.12, slideTo: 140 }),
  stack: () => tone(300, { type: "sawtooth", decay: 0.16, peak: 0.12, slideTo: 520 }),
  win: () => [523, 659, 784, 1046].forEach((f, i) => tone(f, { type: "triangle", decay: 0.22, peak: 0.2, delay: i * 120 })),
  pop: () => tone(600, { decay: 0.07, peak: 0.15, slideTo: 300 }),
};

export function speak(text) {
  if (!settings.voice || !("speechSynthesis" in window) || settings.volume <= 0) return;
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.volume = settings.volume / 100;
  window.speechSynthesis.speak(utterance);
}
