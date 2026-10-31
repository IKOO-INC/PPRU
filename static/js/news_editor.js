(() => {
  const editor = document.querySelector("#article-editor");
  const hiddenBody = document.querySelector("#article-body-html");
  const form = document.querySelector("#news-editor-form");
  if (!editor || !hiddenBody || !form) return;

  const buttons = Array.from(document.querySelectorAll("[data-editor-command]"));
  const summaryPreview = document.querySelector("[data-news-summary-preview]");
  const summaryWidget = document.querySelector("[data-news-summary]");
  const imageButton = document.querySelector("[data-editor-insert-image]");
  const imageInput = document.querySelector("[data-editor-image-file]");
  const imageStatus = document.querySelector("[data-editor-image-status]");
  const csrfToken = form.querySelector('input[name="csrf_token"]')?.value || "";
  const maxImageSize = 10 * 1024 * 1024;
  let savedRange = null;

  const currentSelection = () => window.getSelection?.();
  const nodeInsideEditor = (node) => Boolean(node && (node === editor || editor.contains(node)));

  const rememberSelection = () => {
    const selection = currentSelection();
    if (!selection?.rangeCount) return;
    const range = selection.getRangeAt(0);
    if (nodeInsideEditor(range.commonAncestorContainer)) savedRange = range.cloneRange();
  };

  const restoreSelection = () => {
    editor.focus();
    const selection = currentSelection();
    if (!selection) return;
    if (savedRange && nodeInsideEditor(savedRange.commonAncestorContainer)) {
      selection.removeAllRanges();
      selection.addRange(savedRange);
    } else if (!nodeInsideEditor(selection.anchorNode)) {
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
      selection.removeAllRanges();
      selection.addRange(range);
      savedRange = range.cloneRange();
    }
  };

  const closestTag = (tagNames) => {
    const selection = currentSelection();
    if (!selection?.rangeCount || !nodeInsideEditor(selection.anchorNode)) return null;
    let node = selection.anchorNode.nodeType === 1 ? selection.anchorNode : selection.anchorNode.parentElement;
    while (node && node !== editor) {
      if (tagNames.includes(node.tagName)) return node;
      node = node.parentElement;
    }
    return null;
  };

  const commandIsActive = (button) => {
    const command = button.dataset.editorCommand;
    const value = (button.dataset.editorValue || "").toLowerCase();
    if (command === "formatBlock") {
      if (value === "blockquote") return Boolean(closestTag(["BLOCKQUOTE"]));
      const block = closestTag(["P", "H2", "H3", "H4", "BLOCKQUOTE"]);
      return Boolean(block && block.tagName.toLowerCase() === value);
    }
    if (command === "createLink") return Boolean(closestTag(["A"]));
    if (command === "insertUnorderedList") return Boolean(closestTag(["UL"]));
    if (command === "insertOrderedList") return Boolean(closestTag(["OL"]));
    try {
      return Boolean(document.queryCommandState(command));
    } catch (_error) {
      return false;
    }
  };

  const updateToolbar = () => {
    buttons.forEach((button) => {
      const active = commandIsActive(button);
      button.classList.toggle("is-active", active);
      if (button.hasAttribute("data-editor-toggle")) {
        button.setAttribute("aria-pressed", String(active));
      }
    });
  };

  const updateSummaryPreview = () => {
    if (!summaryPreview) return;
    const rawText = editor.innerText || editor.textContent || "";
    const text = rawText.replace(/\s+/g, " ").trim();
    const maxChars = Number.parseInt(summaryWidget?.dataset.maxChars || "160", 10) || 160;
    if (text.length <= maxChars) {
      summaryPreview.textContent = text || "Ringkasan akan dibuat dari isi berita.";
      return;
    }
    let excerpt = text.slice(0, maxChars - 3);
    if (excerpt.includes(" ")) excerpt = excerpt.slice(0, excerpt.lastIndexOf(" "));
    summaryPreview.textContent = `${excerpt.replace(/[ ,;:-]+$/, "")}...`;
  };

  const syncEditorFields = () => {
    hiddenBody.value = editor.innerHTML;
    updateSummaryPreview();
    rememberSelection();
    updateToolbar();
  };

  const activeBlock = () => closestTag(["P", "H2", "H3", "H4", "BLOCKQUOTE"]);

  const unwrapBlockquote = (quote) => {
    if (!quote?.parentNode) return;
    const children = Array.from(quote.childNodes);
    if (!children.length) {
      const paragraph = document.createElement("p");
      paragraph.innerHTML = "<br>";
      quote.replaceWith(paragraph);
    } else {
      quote.replaceWith(...children);
    }
  };

  const removeCurrentFormatting = () => {
    const quote = closestTag(["BLOCKQUOTE"]);
    if (quote) unwrapBlockquote(quote);
    const block = activeBlock();
    if (block && ["H2", "H3", "H4", "BLOCKQUOTE"].includes(block.tagName)) {
      document.execCommand("formatBlock", false, "p");
    }
    if (closestTag(["UL"])) document.execCommand("insertUnorderedList", false, null);
    if (closestTag(["OL"])) document.execCommand("insertOrderedList", false, null);
    document.execCommand("removeFormat", false, null);
  };

  const runCommand = (button) => {
    restoreSelection();
    const command = button.dataset.editorCommand;
    const value = button.dataset.editorValue || null;

    if (command === "createLink") {
      if (closestTag(["A"])) {
        document.execCommand("unlink", false, null);
      } else {
        const url = window.prompt("Masukkan URL tautan (https://...)");
        if (url?.trim()) document.execCommand("createLink", false, url.trim());
      }
    } else if (command === "formatBlock") {
      const target = String(value || "p").toLowerCase();
      if (target === "blockquote" || target === "p") {
        const quote = closestTag(["BLOCKQUOTE"]);
        if (quote) unwrapBlockquote(quote);
        else document.execCommand("formatBlock", false, target);
      } else {
        const block = activeBlock();
        const isSameBlock = block?.tagName.toLowerCase() === target;
        const nextBlock = isSameBlock && target !== "p" ? "p" : target;
        document.execCommand("formatBlock", false, nextBlock);
      }
    } else if (command === "removeFormat") {
      removeCurrentFormatting();
    } else {
      document.execCommand(command, false, value);
    }

    syncEditorFields();
  };

  buttons.forEach((button) => {
    button.addEventListener("mousedown", (event) => event.preventDefault());
    button.addEventListener("click", () => runCommand(button));
  });

  ["input", "keyup", "mouseup", "focus"].forEach((eventName) => {
    editor.addEventListener(eventName, syncEditorFields);
  });
  document.addEventListener("selectionchange", () => {
    rememberSelection();
    updateToolbar();
  });

  const escapeHtml = (value) => {
    const element = document.createElement("span");
    element.textContent = value;
    return element.innerHTML;
  };

  const insertImage = (src, alt) => {
    restoreSelection();
    const imageHtml = `<p class="article-image"><img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy"></p><p><br></p>`;
    document.execCommand("insertHTML", false, imageHtml);
    syncEditorFields();
  };

  imageButton?.addEventListener("mousedown", (event) => event.preventDefault());
  imageButton?.addEventListener("click", () => {
    rememberSelection();
    imageInput?.click();
  });

  imageInput?.addEventListener("change", async () => {
    const file = imageInput.files?.[0];
    if (!file) return;
    if (file.size > maxImageSize) {
      if (imageStatus) imageStatus.textContent = "Ukuran file maksimal 10 MB.";
      imageInput.value = "";
      return;
    }
    if (!csrfToken) {
      if (imageStatus) imageStatus.textContent = "Sesi formulir tidak valid. Muat ulang halaman lalu coba lagi.";
      imageInput.value = "";
      return;
    }

    const payload = new FormData();
    payload.append("csrf_token", csrfToken);
    payload.append("folder", "news");
    payload.append("image_file", file);
    imageButton.disabled = true;
    if (imageStatus) imageStatus.textContent = "Mengunggah gambar ke Cloudinary…";

    try {
      const response = await fetch("/admin/upload-image", {
        method: "POST",
        body: payload,
        credentials: "same-origin",
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result.url) throw new Error(result.error || "Upload gambar gagal.");

      const defaultAlt = file.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
      const alt = window.prompt("Teks alternatif untuk gambar (opsional):", defaultAlt);
      insertImage(result.url, alt === null ? "" : alt.trim());
      if (imageStatus) imageStatus.textContent = "Gambar berhasil disisipkan. Simpan berita untuk menerapkan perubahan.";
    } catch (error) {
      if (imageStatus) imageStatus.textContent = error.message || "Upload gambar gagal.";
    } finally {
      imageButton.disabled = false;
      imageInput.value = "";
    }
  });

  form.addEventListener("submit", () => {
    hiddenBody.value = editor.innerHTML;
  });

  syncEditorFields();
})();
