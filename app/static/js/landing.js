// Signature section: scroll position builds a No Mercy draw stack, then fills
// the victim's hand to the 25-card knockout. Every visual is a pure function of
// scroll progress, so it scrubs backwards exactly as it plays forwards.
(function () {
  "use strict";

  var section = document.getElementById("stack");
  if (!section) return;

  var cards = Array.prototype.slice.call(section.querySelectorAll(".stack__card"));
  var steps = Array.prototype.slice.call(section.querySelectorAll(".stack__steps li"));
  var slots = Array.prototype.slice.call(section.querySelectorAll(".stack__slots i"));
  var countEl = document.getElementById("stack-count");
  var handEl = document.getElementById("hand-count");

  var VALUES = [2, 4, 6, 10];
  var REST = [-9, 6, -4, 10]; // resting rotation of each card on the pile
  var START_HAND = 3;
  var LIMIT = 25;

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
  function ease(t) { return 1 - Math.pow(1 - t, 3); }

  function render(p) {
    // 0.00-0.60: four cards land one after another.
    var total = 0;
    var started = 0;
    cards.forEach(function (card, i) {
      var start = 0.04 + i * 0.14;
      var t = clamp((p - start) / 0.11, 0, 1);
      var e = ease(t);
      var y = (1 - e) * -115; // vh above the pile
      var x = (1 - e) * (i % 2 ? 40 : -40);
      var r = REST[i] + (1 - e) * (i % 2 ? 40 : -40);
      card.style.transform = "translate3d(" + x + "px," + y + "vh,0) rotate(" + r + "deg)";
      card.style.visibility = t > 0 ? "visible" : "hidden";
      if (t > 0) { started = i + 1; total += Math.round(VALUES[i] * e); }
    });

    // 0.66-0.88: the stack is taken, the hand fills to 25.
    var take = clamp((p - 0.66) / 0.22, 0, 1);
    var hand = START_HAND + Math.round(take * (LIMIT - START_HAND));
    countEl.textContent = String(total);
    section.classList.toggle("is-taken", take > 0);
    handEl.textContent = String(hand);
    slots.forEach(function (slot, i) {
      slot.classList.toggle("is-filled", i < START_HAND);
      slot.classList.toggle("is-new", i >= START_HAND && i < hand);
    });

    var out = p >= 0.9;
    section.classList.toggle("is-out", out);

    // The caption follows the card currently landing; the last line belongs to the knockout.
    var step = out ? 4 : Math.max(0, started - 1);
    steps.forEach(function (li, i) {
      li.classList.toggle("is-on", i < step);
      li.classList.toggle("is-now", i === step);
    });
  }

  function progress() {
    var rect = section.getBoundingClientRect();
    var travel = rect.height - window.innerHeight;
    return travel > 0 ? clamp(-rect.top / travel, 0, 1) : 1;
  }

  var ticking = false;
  function onScroll() {
    if (ticking) return;
    ticking = true;
    window.requestAnimationFrame(function () {
      ticking = false;
      render(progress());
    });
  }

  function setMode() {
    if (reduced.matches) {
      section.classList.add("stack--static");
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      render(1);
    } else {
      section.classList.remove("stack--static");
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll, { passive: true });
      render(progress());
    }
  }

  if (reduced.addEventListener) reduced.addEventListener("change", setMode);
  setMode();
})();
