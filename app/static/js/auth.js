(function () {
  "use strict";

  var form = document.getElementById("auth-form");
  var title = document.getElementById("auth-title");
  var submit = document.getElementById("auth-submit");
  var error = document.getElementById("auth-error");
  var username = document.getElementById("username");
  var password = document.getElementById("password");
  var csrf = document.querySelector('meta[name="csrf-token"]').content;

  var COPY = {
    login: { title: "Welcome back", submit: "Sign in", autocomplete: "current-password", url: "/api/auth/login" },
    signup: { title: "Create your account", submit: "Create account", autocomplete: "new-password", url: "/api/auth/signup" }
  };

  function mode() { return form.dataset.mode; }

  function setMode(next) {
    form.dataset.mode = next;
    title.textContent = COPY[next].title;
    submit.textContent = COPY[next].submit;
    password.autocomplete = COPY[next].autocomplete;
    error.textContent = "";
    history.replaceState(null, "", next === "signup" ? "?mode=signup" : location.pathname);
  }

  document.querySelectorAll('input[name="auth-mode"]').forEach(function (radio) {
    radio.addEventListener("change", function () { setMode(radio.value); });
  });

  function validate() {
    var name = username.value.trim();
    var problems = [];
    username.removeAttribute("aria-invalid");
    password.removeAttribute("aria-invalid");
    if (!/^[A-Za-z0-9_]{3,20}$/.test(name)) {
      username.setAttribute("aria-invalid", "true");
      problems.push(mode() === "signup" ? "Usernames are 3–20 letters, numbers or underscores." : "Enter your username.");
    }
    if (password.value.length < (mode() === "signup" ? 8 : 1)) {
      password.setAttribute("aria-invalid", "true");
      problems.push(mode() === "signup" ? "Passwords need at least 8 characters." : "Enter your password.");
    }
    return problems;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var problems = validate();
    if (problems.length) {
      error.textContent = problems[0];
      (username.hasAttribute("aria-invalid") ? username : password).focus();
      return;
    }
    submit.disabled = true;
    submit.textContent = mode() === "signup" ? "Creating account…" : "Signing in…";
    error.textContent = "";

    fetch(COPY[mode()].url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ username: username.value.trim(), password: password.value })
    })
      .then(function (res) {
        return res.json().catch(function () { return { ok: false, message: "Unexpected response from the server." }; });
      })
      .then(function (data) {
        if (data.ok) {
          window.location.assign(data.redirect || "/play");
          return;
        }
        error.textContent = data.message || "Something went wrong. Try again.";
        submit.disabled = false;
        submit.textContent = COPY[mode()].submit;
      })
      .catch(function () {
        error.textContent = "Can't reach the server. Check your connection and try again.";
        submit.disabled = false;
        submit.textContent = COPY[mode()].submit;
      });
  });
})();
