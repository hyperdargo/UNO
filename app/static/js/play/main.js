import { COLORS, DARK_COLORS } from "../lib/cards.js";
import { $, h, toast } from "../lib/dom.js";
import { motionReduced, saveSettings, settings } from "../lib/settings.js";
import { sound, speak } from "../lib/sound.js";
import { fitHand, renderTable, resetTable, setTimer } from "./table.js";

const me = document.querySelector('meta[name="username"]').content;
const MODE_NAMES = { normal: "Normal", no_mercy: "No Mercy", flip: "Flip" };
const COLOR_LABELS = {
  red: "Red", yellow: "Yellow", green: "Green", blue: "Blue",
  pink: "Pink", teal: "Teal", orange: "Orange", purple: "Purple",
};
const CHAT = [
  ["hello", "Hello!"], ["gg", "Good game!"], ["nice", "Nice one."], ["oops", "Oops!"],
  ["haha", "Ha ha!"], ["hurry", "Your move!"], ["revenge", "I'll remember that."], ["mercy", "No mercy!"],
];

const views = { lobby: $("#view-lobby"), waiting: $("#view-waiting"), table: $("#view-table") };
let room = null;
let deadline = 0;
let resultsShownFor = null;

// ---------------------------------------------------------------- socket
if (typeof window.io !== "function") {
  $("#booting").textContent = "Couldn't load the game client. Refresh the page to try again.";
  throw new Error("socket.io client missing");
}

// No transport list: start on HTTP polling and upgrade to WebSocket only if
// the network in front of us allows it. Panel proxies often don't.
const socket = window.io({ withCredentials: true });

// If the connection never comes up, say something more useful than "connecting".
const bootTimer = setTimeout(() => {
  if (!socket.connected) {
    $("#booting").textContent = "Still trying to reach the table server. Check your connection, then refresh.";
  }
}, 8000);
const emit = (event, data) => {
  sound.unlock();
  socket.emit(event, data || {});
};

socket.on("connect", () => {
  clearTimeout(bootTimer);
  $("#conn-banner").hidden = true;
  $("#booting").hidden = true;
});
socket.on("disconnect", () => {
  $("#conn-banner").hidden = false;
});
socket.on("connect_error", () => {
  // A refused connection usually means the session ended.
  fetch("/api/me", { credentials: "same-origin" })
    .then((res) => {
      if (res.status === 401 || res.redirected) window.location.assign("/login");
    })
    .catch(() => {
      $("#conn-banner").hidden = false;
    });
});

socket.on("toast", (data) => {
  if (!data || typeof data.message !== "string") return;
  if (data.kind === "error") sound.bad();
  toast(data.message, data.kind);
});

socket.on("stats", (stats) => {
  const el = $("#stats");
  if (!stats) {
    el.textContent = "No ranked games yet";
    return;
  }
  const wins = `${stats.wins} ranked ${stats.wins === 1 ? "win" : "wins"}`;
  el.textContent = stats.bot_games ? `${wins}, ${stats.bot_wins} vs bots` : wins;
});

socket.on("lobby", renderLobby);
socket.on("room", (payload) => {
  room = payload;
  route();
});
socket.on("room_closed", (data) => {
  room = null;
  closeDialogs();
  toast(data && data.name ? `You left ${data.name}.` : "You left the table.");
  route();
});
socket.on("chat", (data) => {
  if (!data || !room) return;
  const seat = document.querySelector(`[data-seat="${CSS.escape(data.player)}"]`);
  speak(data.text);
  sound.pop();
  if (seat) {
    const bubble = h("span", { class: "seat__bubble", text: data.text });
    seat.append(bubble);
    setTimeout(() => bubble.remove(), 2600);
  } else {
    toast(data.player === me ? `You: ${data.text}` : `${data.player}: ${data.text}`);
  }
});

// ---------------------------------------------------------------- routing
function showView(name) {
  for (const [key, el] of Object.entries(views)) el.hidden = key !== name;
  document.title = { lobby: "Lobby · UNO", waiting: "Waiting for players · UNO", table: "At the table · UNO" }[name];
}

function route() {
  $("#booting").hidden = true;
  if (!room) {
    resetTable();
    resultsShownFor = null;
    showView("lobby");
    return;
  }
  if (room.status === "waiting") {
    resetTable();
    closeDialog("results-dialog");
    showView("waiting");
    renderWaiting();
    return;
  }
  showView("table");
  renderTable(room, tableHandlers);
  deadline = performance.now() + room.turn_remaining * 1000;
  maybePrompt();
  if (room.status === "finished" && resultsShownFor !== room.game_no) {
    resultsShownFor = room.game_no;
    setTimeout(showResults, motionReduced() ? 200 : 1300);
  }
  if (room.status === "finished") updateResultsButtons();
}

// ----------------------------------------------------------------- lobby
function formValue(form, name) {
  const field = form.elements[name];
  return field ? field.value : undefined;
}

function renderLobby(tables) {
  const list = $("#table-list");
  const items = Array.isArray(tables) ? tables : [];
  list.replaceChildren(
    ...items.map((t) =>
      h("li", {},
        h("h3", { text: t.name }),
        h("button", { class: "btn btn--small", type: "button", onclick: () => emit("room:join", { id: t.id }), text: "Join", "aria-label": `Join ${t.name}` }),
        h("p", {},
          h("span", { class: `badge${t.mode === "no_mercy" ? " badge--nomercy" : ""}`, text: MODE_NAMES[t.mode] }),
          h("span", { text: `${t.players} of ${t.max} seats, hosted by ${t.host}` }),
          h("span", { text: `${t.turn_seconds}s turns` }),
        ),
      ),
    ),
  );
  $("#table-empty").hidden = items.length > 0;
}

$("#quick-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  emit("room:quick", { mode: formValue(form, "mode"), bots: Number(formValue(form, "bots")) });
});

$("#create-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  emit("room:create", {
    name: formValue(form, "name").trim(),
    mode: formValue(form, "mode"),
    turn_seconds: Number(formValue(form, "turn_seconds")),
    private: form.elements.private.checked,
  });
});

$("#code-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const code = $("#code-input").value.trim();
  if (!/^[A-Za-z0-9_-]{6,16}$/.test(code)) {
    toast("Table codes are 8 letters and numbers.", "error");
    return;
  }
  emit("room:join", { id: code });
});

// Invite links look like /play#join=CODE.
function joinFromHash() {
  const match = /^#join=([A-Za-z0-9_-]{6,16})$/.exec(window.location.hash);
  if (!match) return;
  history.replaceState(null, "", window.location.pathname);
  socket.once("lobby", () => emit("room:join", { id: match[1] }));
}
joinFromHash();

// --------------------------------------------------------------- waiting
function renderWaiting() {
  const isHost = room.host === me;
  $("#waiting-title").textContent = room.name;
  const badge = $("#waiting-mode");
  badge.textContent = MODE_NAMES[room.mode];
  badge.className = `badge${room.mode === "no_mercy" ? " badge--nomercy" : ""}`;
  $("#waiting-meta").textContent = `${room.seats.length} of 10 seats taken. ${room.turn_seconds} second turns.${room.private ? " Private table." : ""}`;
  $("#waiting-code").textContent = room.id;

  $("#seat-list").replaceChildren(
    ...room.seats.map((seat) =>
      h("li", {},
        h("span", { class: `avatar${seat.bot ? " avatar--bot" : ""}`, text: seat.name.replace(/^Bot /, "").slice(0, 1) }),
        h("span", { class: "seat-list__name", text: seat.name === me ? `${seat.name} (you)` : seat.name }),
        h("span", { class: "seat-list__tag", text: seat.name === room.host ? "Host" : seat.bot ? "Bot" : seat.connected ? "" : "Reconnecting" }),
        isHost && seat.name !== me && h("button", {
          class: "btn btn--ghost btn--small", type: "button", text: "Remove", "aria-label": `Remove ${seat.name}`,
          onclick: () => emit("room:kick", { target: seat.name }),
        }),
      ),
    ),
  );

  $("#add-bot").hidden = !isHost || room.seats.length >= 10;
  $("#start-game").hidden = !isHost;
  $("#start-game").disabled = room.seats.length < 2;
  $("#waiting-hint").textContent = isHost
    ? room.seats.length < 2 ? "Add a bot or wait for a friend to join before you start." : ""
    : `Waiting for ${room.host} to start the game.`;
}

$("#add-bot").addEventListener("click", () => emit("room:add_bot"));
$("#start-game").addEventListener("click", () => emit("room:start"));
$("#leave-waiting").addEventListener("click", () => emit("room:leave"));
$("#copy-code").addEventListener("click", async () => {
  const link = `${window.location.origin}/play#join=${room.id}`;
  try {
    await navigator.clipboard.writeText(link);
    toast("Invite link copied.");
  } catch {
    toast(`Share this link: ${link}`, "info", 8000);
  }
});

// ---------------------------------------------------------------- dialogs
function openDialog(id) {
  const dialog = document.getElementById(id);
  if (dialog && !dialog.open) dialog.showModal();
  return dialog;
}
function closeDialog(id) {
  const dialog = document.getElementById(id);
  if (dialog && dialog.open) dialog.close("dismissed");
}
function closeDialogs() {
  document.querySelectorAll("dialog[open]").forEach((d) => d.close("dismissed"));
}

function askColor(title, lede, colors = COLORS) {
  return new Promise((resolve) => {
    $("#color-title").textContent = title;
    $("#color-lede").textContent = lede;
    $("#swatches").replaceChildren(
      ...colors.map((color) => h("button", { class: `swatch swatch--${color}`, value: color, text: COLOR_LABELS[color] })),
    );
    const dialog = openDialog("color-dialog");
    dialog.returnValue = "";
    dialog.addEventListener("close", () => resolve(colors.includes(dialog.returnValue) ? dialog.returnValue : null), { once: true });
  });
}

// The colors currently in play, and the ones on the far side of a Flip deck.
const sideColors = (game) => (game.side === "dark" ? DARK_COLORS : COLORS);
const otherSideColors = (game) => (game.side === "dark" ? COLORS : DARK_COLORS);

function askTarget() {
  return new Promise((resolve) => {
    const others = room.game.seats.filter((s) => s.status === "playing" && s.name !== me);
    $("#targets").replaceChildren(
      ...others.map((s) => h("button", { class: "btn", value: s.name },
        h("span", { text: s.name }), h("span", { text: `${s.cards} ${s.cards === 1 ? "card" : "cards"}` }))),
    );
    const dialog = openDialog("target-dialog");
    dialog.returnValue = "";
    dialog.addEventListener("close", () => {
      const value = dialog.returnValue;
      resolve(others.some((s) => s.name === value) ? value : null);
    }, { once: true });
  });
}

function confirmAction(title, lede, ok) {
  return new Promise((resolve) => {
    $("#confirm-title").textContent = title;
    $("#confirm-lede").textContent = lede;
    $("#confirm-ok").textContent = ok;
    const dialog = openDialog("confirm-dialog");
    dialog.returnValue = "";
    dialog.addEventListener("close", () => resolve(dialog.returnValue === "ok"), { once: true });
  });
}

document.querySelectorAll("[data-open]").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.open === "leaderboard-dialog") loadLeaderboard();
    if (btn.dataset.open === "settings-dialog") syncSettingsForm();
    openDialog(btn.dataset.open);
  });
});

// ------------------------------------------------------------------ table
let prompting = false;

const tableHandlers = {
  async playCard(card) {
    if (prompting) return;
    const game = room.game;
    let color = null;
    let target = null;
    prompting = true;
    try {
      if (card.color === "wild") {
        let lede = "This becomes the color in play.";
        if (card.value === "wild_roulette") lede = "This becomes the color in play. The next player spins for their own color.";
        if (card.value === "wild_draw_color") lede = "The next player draws until this color turns up, then loses their turn.";
        color = await askColor("Pick a color", lede, sideColors(game));
        if (!color) return;
      } else if (game.mode === "flip" && card.value === "flip" && game.under_card && game.under_card.color === "wild") {
        // Turning the pile over reveals the card underneath — and it's a wild.
        color = await askColor(
          "The pile turns over",
          "A wild is waiting underneath. Name the color play continues with.",
          otherSideColors(game),
        );
        if (!color) return;
      }
      const others = game.seats.filter((s) => s.status === "playing" && s.name !== me);
      if (game.mode === "no_mercy" && card.value === "7" && others.length > 1) {
        target = await askTarget();
        if (!target) return;
      }
    } finally {
      prompting = false;
    }
    emit("game:action", { action: "play", card_id: card.id, color, target });
  },
  catchUno(name) {
    emit("game:action", { action: "catch_uno", target: name });
  },
  async kick(name) {
    if (await confirmAction(`Remove ${name}?`, "Their cards go back into the deck and the game carries on without them.", "Remove")) {
      emit("room:kick", { target: name });
    }
  },
};

async function maybePrompt() {
  const game = room && room.game;
  if (!game || prompting) return;
  if (game.phase === "roulette" && game.current === me && room.status === "playing" && !room.paused) {
    prompting = true;
    const color = await askColor(
      "Color Roulette",
      "Name a color. You'll flip cards until it shows up and keep everything you flip.",
      sideColors(game),
    );
    prompting = false;
    if (color && room.game.phase === "roulette" && room.game.current === me) emit("game:action", { action: "roulette", color });
    else if (room.game.phase === "roulette" && room.game.current === me) setTimeout(maybePrompt, 50);
  }
}

$("#draw-pile").addEventListener("click", () => emit("game:action", { action: "draw" }));
$("#btn-draw").addEventListener("click", () => emit("game:action", { action: "draw" }));
$("#btn-pass").addEventListener("click", () => emit("game:action", { action: "pass" }));
$("#btn-uno").addEventListener("click", () => emit("game:action", { action: "call_uno" }));
$("#pause-game").addEventListener("click", () => emit("room:pause"));
$("#leave-game").addEventListener("click", async () => {
  const playing = room && room.status === "playing" && !room.game.spectating;
  if (!playing || (await confirmAction("Leave this game?", "You'll forfeit and your cards go back into the deck.", "Leave game"))) {
    emit("room:leave");
  }
});

const logPanel = $("#log-panel");
$("#log-toggle").addEventListener("click", (event) => {
  const open = !logPanel.classList.contains("is-open");
  logPanel.classList.toggle("is-open", open);
  event.currentTarget.setAttribute("aria-expanded", String(open));
});

const chatMenu = $("#chat-menu");
chatMenu.append(...CHAT.map(([id, text]) => h("button", {
  class: "btn btn--small", type: "button", text,
  onclick: () => {
    emit("chat", { phrase: id });
    toggleChat(false);
  },
})));
function toggleChat(open) {
  chatMenu.hidden = !open;
  $("#chat-toggle").setAttribute("aria-expanded", String(open));
  if (open) chatMenu.firstElementChild.focus();
}
$("#chat-toggle").addEventListener("click", () => toggleChat(chatMenu.hidden));
document.addEventListener("click", (event) => {
  if (!chatMenu.hidden && !chatMenu.contains(event.target) && event.target.id !== "chat-toggle") toggleChat(false);
});

// Turn timer ring.
setInterval(() => {
  if (!room || room.status !== "playing" || !room.game) return;
  const remaining = room.paused ? room.turn_remaining : Math.max(0, (deadline - performance.now()) / 1000);
  setTimer(room.game.current, remaining / room.turn_seconds);
  const mine = room.game.current === me && !room.paused;
  const status = $("#status");
  status.dataset.remaining = mine ? String(Math.ceil(remaining)) : "";
  if (mine && remaining <= 5 && remaining > 0) status.setAttribute("data-urgent", "");
  else status.removeAttribute("data-urgent");
}, 200);

window.addEventListener("resize", () => {
  if (room && room.game) fitHand();
}, { passive: true });

// Keyboard shortcuts.
document.addEventListener("keydown", (event) => {
  if (!settings.shortcuts || !room || room.status !== "playing" || event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.target.closest("input, select, textarea, dialog")) return;
  const key = event.key.toLowerCase();
  const button = { d: "#btn-draw", p: "#btn-pass", u: "#btn-uno" }[key];
  if (button && !$(button).hidden) {
    event.preventDefault();
    $(button).click();
  }
  if (event.key === "Escape" && !chatMenu.hidden) toggleChat(false);
});

// ---------------------------------------------------------------- results
const OUTCOME = { winner: "Winner", finished: "Cards left", knocked_out: "Knocked out", left: "Left the game" };

function showResults() {
  if (!room || room.status !== "finished" || !room.game) return;
  const game = room.game;
  const won = game.winner === me;
  $("#results-mode").textContent = MODE_NAMES[game.mode];
  $("#results-title").textContent = won ? "You won." : `${game.winner} won.`;
  $("#results-lede").textContent = `${game.points} points from the cards left in play.`;
  $("#results").replaceChildren(
    ...game.results.map((r) => {
      const cls = r.outcome === "winner" ? "outcome outcome--win" : r.outcome === "knocked_out" ? "outcome outcome--out" : "outcome";
      const detail = r.outcome === "finished" ? `${r.cards_left} ${r.cards_left === 1 ? "card" : "cards"} left` : OUTCOME[r.outcome];
      return h("li", { class: r.name === me ? "is-you" : "" }, h("span", { text: r.name === me ? `${r.name} (you)` : r.name }), h("span", { class: cls, text: detail }));
    }),
  );
  updateResultsButtons();
  openDialog("results-dialog");
}

function updateResultsButtons() {
  const isHost = room && room.host === me;
  $("#results-rematch").hidden = !isHost;
  $("#results-wait").textContent = isHost ? "" : `Waiting for ${room ? room.host : "the host"} to start another game.`;
}

$("#results-rematch").addEventListener("click", () => {
  closeDialog("results-dialog");
  emit("room:rematch");
});
$("#results-leave").addEventListener("click", () => {
  closeDialog("results-dialog");
  emit("room:leave");
});
$("#results-view").addEventListener("click", () => closeDialog("results-dialog"));

// ------------------------------------------------------------ leaderboard
async function loadLeaderboard() {
  const box = $("#leaderboard");
  box.replaceChildren(h("p", { class: "empty", text: "Loading…" }));
  try {
    const res = await fetch("/api/leaderboard", { credentials: "same-origin" });
    if (!res.ok) throw new Error(String(res.status));
    const rows = await res.json();
    if (!rows.length) {
      box.replaceChildren(h("p", { class: "empty", text: "No ranked games have finished yet. Open a table with a friend to get on the board." }));
      return;
    }
    box.replaceChildren(
      h("table", {},
        h("thead", {}, h("tr", {}, ...["#", "Player", "Wins", "Games", "No Mercy wins", "Points"].map((t) => h("th", { scope: "col", text: t })))),
        h("tbody", {}, ...rows.map((r, i) => h("tr", { class: r.username === me ? "is-you" : "" },
          h("td", { text: i + 1 }), h("td", { text: r.username }), h("td", { text: r.wins }),
          h("td", { text: r.games }), h("td", { text: r.wins_no_mercy }), h("td", { text: r.points })))),
      ),
    );
  } catch {
    box.replaceChildren(h("p", { class: "empty", text: "Couldn't load the leaderboard. Try again in a moment." }));
  }
}

// --------------------------------------------------------------- settings
const volume = $("#set-volume");
function syncSettingsForm() {
  volume.value = settings.volume;
  $("#set-volume-out").textContent = `${settings.volume}%`;
  $("#set-voice").checked = settings.voice;
  $("#set-motion").checked = settings.reduceMotion;
  $("#set-shortcuts").checked = settings.shortcuts;
}
volume.addEventListener("input", () => {
  saveSettings({ volume: Number(volume.value) });
  $("#set-volume-out").textContent = `${settings.volume}%`;
});
volume.addEventListener("change", () => sound.card());
$("#set-voice").addEventListener("change", (e) => saveSettings({ voice: e.target.checked }));
$("#set-shortcuts").addEventListener("change", (e) => saveSettings({ shortcuts: e.target.checked }));
$("#set-motion").addEventListener("change", (e) => {
  saveSettings({ reduceMotion: e.target.checked });
  document.documentElement.classList.toggle("reduce-motion", motionReduced());
});
document.documentElement.classList.toggle("reduce-motion", motionReduced());
