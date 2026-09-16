// Client-side card rendering. Mirrors templates/partials/card.html.
import { glyph, h } from "./dom.js";

const GLYPHS = new Set(["skip", "reverse", "skip_all", "discard_all", "wild", "wild_roulette"]);
const TEXT = { draw2: "+2", draw4: "+4", wild_draw4: "+4", wild_reverse_draw4: "+4", wild_draw6: "+6", wild_draw10: "+10" };
const NAMES = {
  skip: "Skip", reverse: "Reverse", draw2: "Draw 2", draw4: "Draw 4", skip_all: "Skip Everyone",
  discard_all: "Discard All", wild: "Wild", wild_draw4: "Wild Draw 4", wild_reverse_draw4: "Wild Reverse Draw 4",
  wild_draw6: "Wild Draw 6", wild_draw10: "Wild Draw 10", wild_roulette: "Color Roulette",
};

export function cardName(card) {
  const name = NAMES[card.value] || card.value;
  return card.color === "wild" ? name : `${card.color} ${name}`;
}

export function cardEl(card, size = "l") {
  const color = ["red", "yellow", "green", "blue"].includes(card.color) ? card.color : "wild";
  const el = h("div", { class: `card card--${color} card--${size}`, "aria-hidden": "true" });
  if (GLYPHS.has(card.value)) {
    el.append(
      h("span", { class: "card__corner" }, glyph(card.value)),
      h("span", { class: "card__face" }, glyph(card.value)),
      h("span", { class: "card__corner card__corner--end" }, glyph(card.value)),
    );
  } else {
    const text = TEXT[card.value] || String(card.value);
    const face = h("span", { class: `card__face${text.length > 1 ? " card__face--text" : ""}` });
    if (card.value === "wild_reverse_draw4") face.append(glyph("reverse"));
    else face.textContent = text;
    el.append(
      h("span", { class: "card__corner", text }),
      face,
      h("span", { class: "card__corner card__corner--end", text }),
    );
  }
  return el;
}

export function backEl(size = "l") {
  return h("div", { class: `card card--back card--${size}`, "aria-hidden": "true" }, h("span", { class: "card__mark", text: "UNO" }));
}
