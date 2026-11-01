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

  const installRevealAnimations = () => {
    const main = document.querySelector("main#main");
    const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (!main || prefersReducedMotion || typeof window.IntersectionObserver !== "function") return;

    const targets = new Set();
    const addTargets = (elements) => elements.forEach((element) => targets.add(element));
    const adminPage = main.querySelector(".admin-page");

    if (adminPage) {
      main.querySelectorAll(".admin-panel, .academic-admin-panel").forEach((panel) => {
        const entries = panel.querySelectorAll(
          ".academic-admin-item, .academic-admin-event-item, .admin-news-row, .admin-gallery-row, .admin-repeat-card, .admin-madrasah-card, .admin-user-card"
        );
        if (entries.length) addTargets(entries);
        else targets.add(panel);
      });
      addTargets(main.querySelectorAll(
        ".admin-page-heading, .admin-alert, .admin-academic-form-wrap, .admin-sidebar, .admin-live-preview, .admin-news-form-card, .admin-gallery-form-card, .admin-login-card, .storage-notice-card"
      ));
    } else {
      Array.from(main.children)
        .filter((element) => element.tagName === "SECTION")
        .forEach((section) => {
          const cards = section.querySelectorAll("article, .sidebar-box");
          if (cards.length) addTargets(cards);
          else targets.add(section);
        });
    }

    if (!targets.size) return;
    root.classList.add("motion-reveal-enabled");
    const observer = new window.IntersectionObserver((entries, activeObserver) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const target = entry.target;
        target.classList.remove("motion-reveal-pending");
        target.classList.add("motion-revealed");
        const delay = Number.parseInt(target.style.getPropertyValue("--motion-reveal-delay"), 10) || 0;
        window.setTimeout(() => target.style.removeProperty("--motion-reveal-delay"), 850 + delay);
        activeObserver.unobserve(target);
      });
    }, { threshold: 0.08, rootMargin: "0px 0px -36px 0px" });

    Array.from(targets).forEach((target, index) => {
      target.dataset.motionReveal = "";
      target.classList.add("motion-reveal", "motion-reveal-pending");
      target.style.setProperty("--motion-reveal-delay", `${(index % 5) * 45}ms`);
      observer.observe(target);
    });
  };

  installRevealAnimations();
})();
