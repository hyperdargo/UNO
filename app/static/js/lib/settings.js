// Per-device preferences. Storage can be unavailable (private mode), so every
// access is guarded and sensible defaults always apply.
const KEY = "uno.settings.v1";
const DEFAULTS = { volume: 70, voice: false, reduceMotion: false, shortcuts: true };

function read() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || "{}") };
  } catch {
    return { ...DEFAULTS };
  }
}

export const settings = read();

export function saveSettings(patch) {
  Object.assign(settings, patch);
  try {
    localStorage.setItem(KEY, JSON.stringify(settings));
  } catch {
    /* not persisted; still applies for this visit */
  }
}

const systemReduced = window.matchMedia("(prefers-reduced-motion: reduce)");
export const motionReduced = () => settings.reduceMotion || systemReduced.matches;
