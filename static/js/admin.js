(() => {
  const tabs = Array.from(document.querySelectorAll("[data-admin-tab]"));
  const panels = Array.from(document.querySelectorAll("[data-admin-panel]"));
  const previewFrame = document.querySelector("[data-live-preview-frame]");
  const previewLink = document.querySelector("[data-preview-open]");
  const previewStatus = document.querySelector("[data-preview-status]");
  let previewTimer;
  let previewSequence = 0;

  const setPreviewPage = (panel) => {
    if (!previewFrame || !panel) return;
    window.clearTimeout(previewTimer);
    previewSequence += 1;
    const path = panel.dataset.previewPath || "/";
    previewFrame.removeAttribute("srcdoc");
    previewFrame.src = path;
    if (previewLink) previewLink.href = path;
    if (previewStatus) previewStatus.textContent = "Perubahan formulir akan tampil di sini sebelum disimpan.";
  };

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
      setPreviewPage(panels.find((panel) => panel.dataset.adminPanel === selected));
      if (updateHash) history.replaceState(null, "", `#${selected}`);
    };

    tabs.forEach((tab) => tab.addEventListener("click", () => showPanel(tab.dataset.adminTab)));
    const initialHash = window.location.hash.slice(1);
    const hashIsPanel = panels.some((panel) => panel.dataset.adminPanel === initialHash);
    const serverSelected = document.querySelector("[data-admin-tab].is-active")?.dataset.adminTab || "brand";
    showPanel(hashIsPanel ? initialHash : serverSelected, false);
  }

  const queueLivePreview = (form, panel) => {
    if (!previewFrame || !panel || panel.hidden) return;
    window.clearTimeout(previewTimer);
    previewTimer = window.setTimeout(async () => {
      const sequence = ++previewSequence;
      const formData = new FormData();
      new FormData(form).forEach((value, key) => {
        if (!(value instanceof File)) formData.append(key, value);
      });
      formData.set("component", panel.dataset.adminPanel || "");
      if (previewStatus) previewStatus.textContent = "Memperbarui live preview…";

      try {
        const response = await fetch("/admin/live-preview", {
          method: "POST",
          body: formData,
          headers: { "X-Requested-With": "XMLHttpRequest" },
          credentials: "same-origin",
        });
        if (!response.ok) throw new Error("Preview belum dapat diperbarui.");
        const renderedPage = await response.text();
        if (sequence !== previewSequence) return;
        previewFrame.srcdoc = renderedPage;
        if (previewLink) previewLink.href = panel.dataset.previewPath || "/";
        if (previewStatus) previewStatus.textContent = "Live preview · perubahan ini belum disimpan.";
      } catch (_error) {
        if (sequence !== previewSequence) return;
        if (previewStatus) previewStatus.textContent = "Preview tidak tersedia. Formulir tetap bisa disimpan setelah koneksi pulih.";
      }
    }, 350);
  };

  panels.forEach((panel) => {
    const form = panel.querySelector('form[action="/admin/save"]');
    if (!form) return;
    form.addEventListener("input", () => queueLivePreview(form, panel));
    form.addEventListener("change", () => queueLivePreview(form, panel));
  });

  const storageNotice = document.querySelector("[data-storage-notice]");
  if (storageNotice) {
    const closeNotice = () => storageNotice.remove();
    storageNotice.querySelectorAll("[data-storage-notice-close]").forEach((button) => {
      button.addEventListener("click", closeNotice);
    });
    storageNotice.addEventListener("click", (event) => {
      if (event.target === storageNotice) closeNotice();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeNotice();
    });
    storageNotice.querySelector("button")?.focus();
  }
})();
