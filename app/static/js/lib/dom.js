// Tiny DOM helpers. Text is always set through textContent, never innerHTML,
// so player names and room names can't inject markup.

export const $ = (selector, root = document) => root.querySelector(selector);

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, String(value));
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

const SVG_NS = "http://www.w3.org/2000/svg";

export function glyph(name, viewBox = true) {
  const svg = document.createElementNS(SVG_NS, "svg");
  if (viewBox) svg.setAttribute("viewBox", "0 0 32 32");
  const use = document.createElementNS(SVG_NS, "use");
  use.setAttribute("href", `#g-${name}`);
  svg.append(use);
  return svg;
}

export function toast(message, kind = "info", ms = 3200) {
  const box = document.getElementById("toasts");
  if (!box) return;
  const el = h("div", { class: `toast${kind === "error" ? " toast--error" : ""}`, role: kind === "error" ? "alert" : "status", text: message });
  box.append(el);
  while (box.children.length > 3) box.firstElementChild.remove();
  setTimeout(() => el.remove(), ms);
}

export function show(el, visible) {
  el.hidden = !visible;
}
