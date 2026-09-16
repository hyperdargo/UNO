// Renders the game table from the server's room payload and animates the
// events that happened since the last payload. The server is authoritative:
// this module only draws what it's told and reports clicks.
import { backEl, cardEl, cardName } from "../lib/cards.js";
import { $, h } from "../lib/dom.js";
import { motionReduced } from "../lib/settings.js";
import { sound, speak } from "../lib/sound.js";

const COLOR_VARS = { red: "var(--red)", yellow: "var(--yellow)", green: "var(--green)", blue: "var(--blue)" };
const SEAT_TONES = ["#8a3b36", "#806321", "#2f6b4c", "#34518f", "#6b4a86", "#35706f"];
const SYMBOLS = {
  skip: "Skip", reverse: "Reverse", draw2: "+2", draw4: "+4", skip_all: "Skip Everyone", discard_all: "Discard All",
};

const els = {
  root: $("#view-table"),
  seats: $("#seats"),
  drawPile: $("#draw-pile"),
  drawCount: $("#draw-count"),
  ring: $("#color-ring"),
  stack: $("#discard-stack"),
  discardLabel: $("#discard-label"),
  pending: $("#pending"),
  pendingValue: $("#pending-value"),
  status: $("#status"),
  callout: $("#callout"),
  hand: $("#hand"),
  draw: $("#btn-draw"),
  pass: $("#btn-pass"),
  uno: $("#btn-uno"),
  log: $("#log"),
  paused: $("#paused-banner"),
  pause: $("#pause-game"),
  dealer: $("#dealer"),
};

let lastSeq = 0;
let lastGameKey = null;
let lastTurnCounter = -1;
let discardHistory = [];

function tone(name) {
  let hash = 0;
  for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return SEAT_TONES[hash % SEAT_TONES.length];
}

function initials(name) {
  const clean = name.replace(/^Bot /, "");
  return clean.slice(0, 1);
}

// ------------------------------------------------------------------ seats
function renderSeats(room, game, handlers) {
  const me = room.you;
  const online = new Map(room.seats.map((s) => [s.name, s]));
  els.seats.replaceChildren(
    ...game.seats
      .filter((seat) => seat.name !== me)
      .map((seat) => {
        const info = online.get(seat.name);
        const isBot = info ? info.bot : seat.name.startsWith("Bot ");
        const connected = info ? info.connected : false;
        const out = seat.status !== "playing";
        const avatar = h("span", { class: `avatar seat__avatar${isBot ? " avatar--bot" : ""}`, text: initials(seat.name) }, h("span", { class: "seat__timer" }));
        if (!isBot) avatar.style.setProperty("--seat", tone(seat.name));

        const statusText = out
          ? { knocked_out: "Knocked out", left: "Left", finished: "Finished" }[seat.status] || "Out"
          : `${seat.cards} ${seat.cards === 1 ? "card" : "cards"}`;
        const meta = h("span", { class: "seat__meta" },
          !isBot && h("span", { class: `dot${connected ? "" : " dot--off"}`, title: connected ? "Online" : "Offline" }),
          h("span", { text: statusText }),
          isBot && h("span", { text: "bot" }),
        );

        const el = h("div", {
          class: `seat${game.current === seat.name ? " is-current" : ""}${out ? " is-out" : ""}${seat.uno_safe || (seat.cards === 1 && !out) ? " is-uno" : ""}`,
          role: "listitem",
          dataset: { seat: seat.name },
          "aria-label": `${seat.name}${isBot ? " (bot)" : ""}, ${statusText}${game.current === seat.name ? ", taking their turn" : ""}`,
        }, avatar, h("span", { class: "seat__name", text: seat.name }), meta);

        if (seat.uno_vulnerable && !game.spectating && game.phase !== "over") {
          el.append(h("button", {
            class: "btn btn--small seat__catch", type: "button",
            onclick: () => handlers.catchUno(seat.name),
            text: "Catch!",
            "aria-label": `Catch ${seat.name} for not calling UNO`,
          }));
        }
        if (room.host === me && !out && game.phase !== "over") {
          el.append(h("button", {
            class: "btn btn--ghost btn--small seat__kick", type: "button",
            onclick: () => handlers.kick(seat.name),
            text: "×",
            title: `Remove ${seat.name}`,
            "aria-label": `Remove ${seat.name} from the table`,
          }));
        }
        return el;
      }),
  );
}

// ------------------------------------------------------------------ piles
function renderPiles(game, myTurn) {
  els.drawCount.textContent = `${game.draw_count} left`;
  els.drawPile.disabled = !game.can_draw;
  els.drawPile.classList.toggle("is-hot", game.can_draw && game.playable.length === 0);
  els.drawPile.setAttribute("aria-label", game.pending_draw && myTurn ? `Take ${game.pending_draw} cards` : "Draw a card");

  const top = game.top_card;
  const known = discardHistory[discardHistory.length - 1];
  if (!known || known.id !== top.id) {
    discardHistory.push({ ...top, tilt: Math.round((Math.random() - 0.5) * 24) });
    discardHistory = discardHistory.slice(-4);
  }
  els.stack.replaceChildren(
    ...discardHistory.map((card, i) => {
      const el = cardEl(card, "l");
      el.style.transform = `rotate(${card.tilt}deg)`;
      el.dataset.id = card.id;
      if (i < discardHistory.length - 1) el.style.filter = "brightness(0.8)";
      return el;
    }),
  );
  els.ring.style.setProperty("--ring", COLOR_VARS[game.active_color] || "transparent");
  els.discardLabel.textContent = `Top card: ${cardName(top)}. Color in play: ${game.active_color}.`;

  els.pending.hidden = !game.pending_draw;
  els.pendingValue.textContent = `+${game.pending_draw}`;
}

// ------------------------------------------------------------------- hand
function renderHand(game, myTurn, handlers) {
  const playable = new Set(game.playable);
  const cards = game.hand.map((card) => {
    const canPlay = myTurn && playable.has(card.id);
    const btn = h("button", {
      class: `hand__card${canPlay ? " is-playable" : ""}${card.id === game.drawn_card_id ? " is-drawn" : ""}`,
      type: "button",
      role: "listitem",
      dataset: { id: card.id },
      "aria-label": `${cardName(card)}${canPlay ? ", playable" : ""}`,
      "aria-disabled": canPlay ? "false" : "true",
      onclick: () => canPlay && handlers.playCard(card),
    }, cardEl(card, "l"));
    return btn;
  });
  els.hand.replaceChildren(...cards);
  els.hand.classList.toggle("is-turn", myTurn);
  fitHand();
}

export function fitHand() {
  const count = els.hand.children.length;
  if (!count) return;
  const first = els.hand.firstElementChild;
  const cardWidth = first.getBoundingClientRect().width || 124;
  const available = els.hand.clientWidth - 16;
  const natural = cardWidth + 6;
  const needed = count * natural;
  let overlap = 6;
  if (needed > available) overlap = Math.max(-cardWidth * 0.72, (available - cardWidth) / Math.max(1, count - 1) - cardWidth);
  els.hand.style.setProperty("--overlap", `${Math.round(overlap)}px`);
}

// ----------------------------------------------------------------- status
function describeTurn(room, game) {
  const me = room.you;
  if (game.phase === "over") return game.winner === me ? "You won this round." : `${game.winner} won this round.`;
  if (room.paused) return "Paused by the host.";
  if (game.spectating) return `You're out. Watching ${game.current} play.`;
  if (game.current !== me) {
    return game.pending_draw ? `${game.current} must stack or take ${game.pending_draw}.` : `${game.current} is playing.`;
  }
  if (game.phase === "roulette") return "Color Roulette: name a color to flip for.";
  if (game.pending_draw) {
    return game.playable.length
      ? `Stack a +${game.pending_min} or bigger, or take ${game.pending_draw}.`
      : `Nothing to stack. Take the ${game.pending_draw} cards.`;
  }
  if (game.drawn_card_id) {
    return game.can_pass ? "You drew a card that fits. Play it or keep it." : "Play the card you drew.";
  }
  if (!game.playable.length) return game.mode === "no_mercy" ? "Nothing fits. Draw until something does." : "Nothing fits. Draw a card.";
  const top = game.top_card;
  const symbol = top.color === "wild" ? "" : ` or ${SYMBOLS[top.value] || top.value}`;
  return `Your turn. Match ${game.active_color}${symbol}.`;
}

function renderLog(game) {
  els.log.replaceChildren(...game.log.map((entry) => h("li", { text: entry.text })));
  els.log.scrollTop = els.log.scrollHeight;
}

// ------------------------------------------------------------- animation
function seatRect(name, me) {
  if (name === me) return els.hand.getBoundingClientRect();
  const seat = els.seats.querySelector(`[data-seat="${CSS.escape(name)}"]`);
  return seat ? seat.getBoundingClientRect() : null;
}

function capture(me) {
  const hand = new Map();
  for (const btn of els.hand.children) hand.set(btn.dataset.id, btn.getBoundingClientRect());
  const seats = new Map();
  for (const seat of els.seats.children) seats.set(seat.dataset.seat, seat.getBoundingClientRect());
  seats.set(me, els.hand.getBoundingClientRect());
  return { hand, seats, draw: els.drawPile.getBoundingClientRect() };
}

function fly(node, from, to, { duration = 420, delay = 0, rotate = 0 } = {}) {
  if (!from || !to) return Promise.resolve();
  const clone = h("div", { class: "flying", "aria-hidden": "true" }, node);
  node.style.setProperty("--w", `${Math.round(to.width)}px`);
  Object.assign(clone.style, {
    position: "fixed", left: `${to.left}px`, top: `${to.top}px`, width: `${to.width}px`, height: `${to.height}px`,
    zIndex: 40, pointerEvents: "none",
  });
  document.body.append(clone);
  const dx = from.left + from.width / 2 - (to.left + to.width / 2);
  const dy = from.top + from.height / 2 - (to.top + to.height / 2);
  const scale = Math.max(0.35, Math.min(1.2, from.width / to.width));
  const anim = clone.animate(
    [
      { transform: `translate(${dx}px, ${dy}px) scale(${scale}) rotate(${rotate}deg)`, opacity: delay ? 0 : 1, offset: 0 },
      { opacity: 1, offset: 0.1 },
      { transform: "translate(0, 0) scale(1) rotate(0deg)", opacity: 1, offset: 1 },
    ],
    { duration, delay, easing: "cubic-bezier(0.22, 1, 0.36, 1)", fill: "backwards" },
  );
  return anim.finished.catch(() => {}).then(() => clone.remove());
}

let calloutAnim = null;
function callout(text, danger = false) {
  els.callout.textContent = text;
  els.callout.classList.toggle("is-danger", danger);
  if (calloutAnim) calloutAnim.cancel();
  if (motionReduced()) {
    calloutAnim = els.callout.animate([{ opacity: 1 }, { opacity: 1, offset: 0.85 }, { opacity: 0 }], { duration: 1200 });
    return;
  }
  calloutAnim = els.callout.animate(
    [
      { opacity: 0, transform: "translate(-50%, -50%) scale(0.7)" },
      { opacity: 1, transform: "translate(-50%, -50%) scale(1.05)", offset: 0.18 },
      { opacity: 1, transform: "translate(-50%, -50%) scale(1)", offset: 0.75 },
      { opacity: 0, transform: "translate(-50%, -60%) scale(1)" },
    ],
    { duration: 1300, easing: "ease-out" },
  );
}

function animate(events, before, room, game) {
  const me = room.you;
  const reduced = motionReduced();
  let label = null;

  for (const event of events) {
    switch (event.type) {
      case "play": {
        sound.card();
        if (reduced) break;
        const from = event.player === me ? before.hand.get(event.card.id) : before.seats.get(event.player);
        const target = els.stack.querySelector(`[data-id="${CSS.escape(event.card.id)}"]`);
        if (target && from) {
          const to = target.getBoundingClientRect();
          target.style.visibility = "hidden";
          fly(cardEl(event.card, "l"), from, to, { rotate: event.player === me ? 0 : -20 }).then(() => {
            target.style.visibility = "";
          });
        }
        break;
      }
      case "draw": {
        sound.draw();
        if (event.count >= 4) label = { text: `${event.player === me ? "You" : event.player} +${event.count}`, danger: true };
        if (reduced) break;
        const to = event.player === me ? els.hand.getBoundingClientRect() : seatRect(event.player, me);
        if (!to) break;
        const target = { left: to.left + to.width / 2 - 30, top: to.top + to.height / 2 - 45, width: 60, height: 90 };
        const n = Math.min(event.count, 6);
        for (let i = 0; i < n; i++) fly(backEl("s"), before.draw, target, { delay: i * 70, duration: 380 });
        break;
      }
      case "stack":
        sound.stack();
        label = { text: `+${event.total}`, danger: true };
        break;
      case "skip":
        label = { text: event.player === me ? "You're skipped" : "Skipped" };
        break;
      case "skip_all":
        label = { text: "Everyone skipped" };
        break;
      case "reverse":
        label = { text: "Reversed" };
        break;
      case "discard_all":
        label = { text: `Discard all ${event.count + 1}` };
        break;
      case "swap":
        label = { text: event.target === me || event.player === me ? "Hands swapped" : "Swap" };
        break;
      case "rotate":
        label = { text: "Pass your hands" };
        break;
      case "roulette":
        label = { text: "Color Roulette" };
        break;
      case "uno":
        sound.uno();
        speak(`${event.player.replace(/^Bot /, "")} says UNO`);
        label = { text: "UNO!" };
        break;
      case "caught":
        sound.bad();
        speak(`${event.player.replace(/^Bot /, "")} forgot to say UNO`);
        label = { text: `${event.player === me ? "You were" : `${event.player} was`} caught`, danger: true };
        break;
      case "knockout":
        sound.bad();
        label = { text: event.player === me ? "You're knocked out" : "Knocked out", danger: true };
        break;
      case "win":
        sound.win();
        label = { text: event.player === me ? "You win!" : `${event.player} wins` };
        break;
      default:
        break;
    }
  }
  if (label) callout(label.text, label.danger);
}

function dealIn() {
  if (motionReduced()) return;
  [...els.hand.children].forEach((btn, i) => {
    btn.animate(
      [{ transform: "translateY(120px) rotate(8deg)", opacity: 0 }, { transform: "none", opacity: 1 }],
      { duration: 460, delay: 120 + i * 60, easing: "cubic-bezier(0.22, 1, 0.36, 1)", fill: "backwards" },
    );
  });
  els.dealer.animate(
    [
      { opacity: 0, transform: "translateX(60px)" },
      { opacity: 1, transform: "none", offset: 0.2 },
      { opacity: 1, transform: "none", offset: 0.8 },
      { opacity: 0, transform: "translateX(60px)" },
    ],
    { duration: 2600, easing: "ease-in-out" },
  );
}

// ------------------------------------------------------------------ entry
export function renderTable(room, handlers) {
  const game = room.game;
  const me = room.you;
  const myTurn = game.current === me && game.phase !== "over" && !room.paused;
  const gameKey = `${room.id}:${room.game_no}`;
  const fresh = gameKey !== lastGameKey;
  if (fresh) {
    lastGameKey = gameKey;
    discardHistory = [];
    lastTurnCounter = -1;
  }

  const before = capture(me);
  const newEvents = game.events.filter((e) => e.seq > lastSeq);

  els.root.classList.toggle("is-my-turn", myTurn);
  renderSeats(room, game, handlers);
  renderPiles(game, myTurn);
  renderHand(game, myTurn, handlers);
  renderLog(game);
  els.status.textContent = describeTurn(room, game);
  els.paused.hidden = !room.paused;
  els.pause.hidden = room.host !== me || game.phase === "over";
  els.pause.textContent = room.paused ? "Resume" : "Pause";

  els.draw.hidden = !game.can_draw;
  els.draw.firstChild.textContent = game.pending_draw ? `Take ${game.pending_draw} ` : "Draw ";
  els.draw.classList.toggle("is-hot", game.can_draw && game.playable.length === 0);
  els.pass.hidden = !game.can_pass;
  els.uno.hidden = !game.can_call_uno;

  if (fresh) dealIn();
  else if (newEvents.length) animate(newEvents, before, room, game);
  if (game.events.length) lastSeq = game.events[game.events.length - 1].seq;

  if (myTurn && game.turn_counter !== lastTurnCounter && !fresh) sound.turn();
  lastTurnCounter = game.turn_counter;
}

export function resetTable() {
  lastSeq = 0;
  lastGameKey = null;
  lastTurnCounter = -1;
  discardHistory = [];
}

export function setTimer(name, fraction) {
  for (const seat of els.seats.children) {
    seat.style.setProperty("--t", seat.dataset.seat === name ? String(fraction) : "1");
  }
}
