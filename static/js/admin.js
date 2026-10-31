(() => {
  const tabs = Array.from(document.querySelectorAll("[data-admin-tab]"));
  const panels = Array.from(document.querySelectorAll("[data-admin-panel]"));
  const previewFrame = document.querySelector("[data-live-preview-frame]");
  const previewLink = document.querySelector("[data-preview-open]");
  const previewStatus = document.querySelector("[data-preview-status]");
  const mobileLayout = window.matchMedia("(max-width: 760px)");
  const sidebar = document.querySelector("[data-admin-sidebar]");
  const sidebarToggle = document.querySelector("[data-admin-sidebar-toggle]");
  const sidebarClose = document.querySelector("[data-admin-sidebar-close]");
  const sidebarBackdrop = document.querySelector("[data-admin-sidebar-backdrop]");
  let previewTimer;
  let previewSequence = 0;

  const setMobileSidebarOpen = (open, restoreFocus = false) => {
    if (!sidebar || !sidebarToggle) return;
    const mobile = mobileLayout.matches;
    const isOpen = mobile && Boolean(open);
    document.body.classList.toggle("admin-mobile-sidebar-open", isOpen);
    sidebarToggle.setAttribute("aria-expanded", String(isOpen));
    sidebar.inert = mobile && !isOpen;
    if (mobile) sidebar.setAttribute("aria-hidden", String(!isOpen));
    else sidebar.removeAttribute("aria-hidden");
    if (isOpen) sidebarClose?.focus();
    else if (restoreFocus && mobile) sidebarToggle.focus();
  };

  if (sidebar && sidebarToggle) {
    sidebarToggle.addEventListener("click", () => setMobileSidebarOpen(true));
    sidebarClose?.addEventListener("click", () => setMobileSidebarOpen(false, true));
    sidebarBackdrop?.addEventListener("click", () => setMobileSidebarOpen(false, true));
    setMobileSidebarOpen(false);

    document.addEventListener("keydown", (event) => {
      if (!mobileLayout.matches || !document.body.classList.contains("admin-mobile-sidebar-open")) return;
      if (event.key === "Escape") {
        setMobileSidebarOpen(false, true);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(sidebar.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'))
        .filter((element) => !element.hidden && element.getAttribute("aria-hidden") !== "true");
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    const onLayoutChange = () => setMobileSidebarOpen(false);
    if (typeof mobileLayout.addEventListener === "function") mobileLayout.addEventListener("change", onLayoutChange);
    else mobileLayout.addListener(onLayoutChange);
  }

  const setPreviewPage = (panel) => {
    if (!previewFrame || !panel || mobileLayout.matches) return;
    window.clearTimeout(previewTimer);
    previewSequence += 1;
    const path = panel.dataset.previewPath || "/";
    previewFrame.removeAttribute("srcdoc");
    previewFrame.src = path;
    if (previewLink) previewLink.href = path;
    if (previewStatus) previewStatus.textContent = "Perubahan formulir akan tampil di sini sebelum disimpan.";
  };

  const syncPreviewLayout = (event) => {
    if (!previewFrame) return;
    if (event.matches) {
      window.clearTimeout(previewTimer);
      previewSequence += 1;
      previewFrame.removeAttribute("srcdoc");
      previewFrame.src = "about:blank";
      return;
    }
    const selected = document.querySelector("[data-admin-tab].is-active")?.dataset.adminTab || "brand";
    setPreviewPage(panels.find((panel) => panel.dataset.adminPanel === selected));
  };
  if (previewFrame) {
    if (mobileLayout.matches) syncPreviewLayout({ matches: true });
    if (typeof mobileLayout.addEventListener === "function") mobileLayout.addEventListener("change", syncPreviewLayout);
    else mobileLayout.addListener(syncPreviewLayout);
  }

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

    tabs.forEach((tab) => tab.addEventListener("click", () => {
      showPanel(tab.dataset.adminTab);
      setMobileSidebarOpen(false, true);
    }));
    const initialHash = window.location.hash.slice(1);
    const hashIsPanel = panels.some((panel) => panel.dataset.adminPanel === initialHash);
    const serverSelected = document.querySelector("[data-admin-tab].is-active")?.dataset.adminTab || "brand";
    showPanel(hashIsPanel ? initialHash : serverSelected, false);
  }

  const queueLivePreview = (form, panel) => {
    if (!previewFrame || mobileLayout.matches || !panel || panel.hidden) return;
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
