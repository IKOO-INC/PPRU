(() => {
  const sharePanel = document.querySelector("[data-article-share]");
  if (!sharePanel) return;

  const title = sharePanel.dataset.articleTitle || document.title;
  const url = sharePanel.dataset.articleUrl || window.location.href;
  const status = sharePanel.querySelector("[data-share-status]");
  const whatsappLink = sharePanel.querySelector("[data-share-whatsapp]");
  const instagramButton = sharePanel.querySelector("[data-share-instagram]");
  const copyButton = sharePanel.querySelector("[data-copy-article-link]");

  if (whatsappLink) {
    whatsappLink.href = `https://wa.me/?text=${encodeURIComponent(`${title} ${url}`)}`;
  }

  const announce = (message) => {
    if (status) status.textContent = message;
  };

  const copyText = async (value) => {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(value);
        return true;
      } catch (_error) {
        // Fall through to the selection-based copy for browsers without clipboard permission.
      }
    }

    const field = document.createElement("textarea");
    field.value = value;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (_error) {
      copied = false;
    }
    field.remove();
    return copied;
  };

  copyButton?.addEventListener("click", async () => {
    announce(await copyText(url) ? "Tautan artikel disalin." : "Tidak dapat menyalin tautan otomatis.");
  });

  instagramButton?.addEventListener("click", async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title, text: title, url });
        announce("Menu berbagi terbuka. Pilih Instagram untuk melanjutkan.");
        return;
      } catch (error) {
        if (error?.name === "AbortError") return;
      }
    }
    announce(await copyText(url)
      ? "Tautan disalin. Tempelkan di Instagram untuk membagikan artikel."
      : "Salin tautan dari bilah alamat lalu bagikan di Instagram.");
  });
})();
