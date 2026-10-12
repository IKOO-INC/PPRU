(() => {
  const tabs = Array.from(document.querySelectorAll("[data-admin-tab]"));
  const panels = Array.from(document.querySelectorAll("[data-admin-panel]"));
  if (tabs.length && panels.length) {
    const showPanel = (id, updateHash = true) => {
      const panelExists = panels.some((panel) => panel.dataset.adminPanel === id);
      const selected = panelExists ? id : "brand";
      tabs.forEach((tab) => {
        const active = tab.dataset.adminTab === selected;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-current", active ? "page" : "false");
      });
      panels.forEach((panel) => { panel.hidden = panel.dataset.adminPanel !== selected; });
      if (updateHash) history.replaceState(null, "", `#${selected}`);
    };

    tabs.forEach((tab) => tab.addEventListener("click", () => showPanel(tab.dataset.adminTab)));
    const initialHash = window.location.hash.slice(1);
    showPanel(initialHash || document.querySelector("[data-admin-tab].is-active")?.dataset.adminTab || "brand", false);
  }

  document.querySelectorAll("[data-image-input]").forEach((input) => {
    input.addEventListener("input", () => {
      const preview = input.closest(".admin-asset-field")?.querySelector("[data-image-preview]");
      if (preview) preview.src = input.value.trim() || "/static/images/mark.svg";
    });
  });
})();
