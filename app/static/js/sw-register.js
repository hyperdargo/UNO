if ("serviceWorker" in navigator) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () {
      // Offline caching is a nice-to-have; the game works without it.
    });
  });
}
