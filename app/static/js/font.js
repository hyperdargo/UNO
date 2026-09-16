// Loads the display font after first paint. If the request is slow or blocked,
// the page still renders immediately in the fallback stack.
(function () {
  var link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&display=swap";
  link.crossOrigin = "anonymous";
  document.head.appendChild(link);
})();
