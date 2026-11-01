(() => {
  const storageKey = "ppru-theme";
  const root = document.documentElement;
  const button = document.querySelector("[data-theme-toggle]");
  const icon = button?.querySelector("[data-theme-icon]");
  const label = button?.querySelector("[data-theme-label]");
  let dark = root.dataset.theme === "dark";

  const applyTheme = (useDark, persist = false) => {
    dark = Boolean(useDark);
    if (dark) root.dataset.theme = "dark";
    else root.removeAttribute("data-theme");

    if (button) {
      const action = dark ? "Matikan mode gelap" : "Aktifkan mode gelap";
      button.setAttribute("aria-pressed", String(dark));
      button.setAttribute("aria-label", action);
      button.title = action;
      if (label) label.textContent = action;
      icon?.classList.toggle("fa-moon", !dark);
      icon?.classList.toggle("fa-sun", dark);
    }

    if (persist) {
      try {
        localStorage.setItem(storageKey, dark ? "dark" : "light");
      } catch (_error) {
        // Theme still applies to the current page when persistent storage is unavailable.
      }
    }
  };

  applyTheme(dark);
  button?.addEventListener("click", () => applyTheme(!dark, true));
  window.addEventListener("storage", (event) => {
    if (event.key === storageKey) applyTheme(event.newValue === "dark");
  });
})();
