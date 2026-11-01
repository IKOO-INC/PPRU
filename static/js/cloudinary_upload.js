(() => {
  const maxFileSize = 10 * 1024 * 1024;

  document.querySelectorAll("[data-image-input]").forEach((input) => {
    input.addEventListener("input", () => {
      const preview = input.closest(".admin-asset-field")?.querySelector("[data-image-preview]");
      if (!preview) return;
      const imageUrl = input.value.trim();
      if (imageUrl) {
        preview.src = imageUrl;
        preview.hidden = false;
      } else {
        preview.removeAttribute("src");
        preview.hidden = true;
      }
    });
  });

  document.querySelectorAll("[data-cloudinary-field]").forEach((field) => {
    const button = field.querySelector("[data-cloudinary-upload-button]");
    const fileInput = field.querySelector("[data-cloudinary-file]");
    const urlInput = field.querySelector("[data-image-input]");
    const csrfInput = field.querySelector("[data-cloudinary-csrf]");
    const status = field.querySelector("[data-cloudinary-status]");
    if (!button || !fileInput || !urlInput || !csrfInput) return;

    button.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files?.[0];
      if (!file) return;
      if (file.size > maxFileSize) {
        if (status) status.textContent = "Ukuran file maksimal 10 MB.";
        fileInput.value = "";
        return;
      }

      const formData = new FormData();
      formData.append("csrf_token", csrfInput.value);
      formData.append("folder", field.dataset.cloudinaryFolder || "site");
      formData.append("image_file", file);
      button.disabled = true;
      button.dataset.originalText = button.textContent;
      button.textContent = "Mengunggah…";
      if (status) status.textContent = "Mengunggah dan menyiapkan foto…";

      try {
        const response = await fetch("/admin/upload-image", {
          method: "POST",
          body: formData,
          credentials: "same-origin",
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(result.error || "Pengunggahan foto belum berhasil. Silakan coba lagi.");

        urlInput.value = result.url;
        urlInput.dispatchEvent(new Event("input", { bubbles: true }));
        if (status) status.textContent = "Foto berhasil diunggah. Simpan perubahan untuk menggunakannya.";
      } catch (error) {
        if (status) status.textContent = error instanceof TypeError
          ? "Koneksi terganggu. Periksa jaringan, lalu coba lagi."
          : error.message || "Pengunggahan foto belum berhasil. Silakan coba lagi.";
      } finally {
        button.disabled = false;
        button.textContent = button.dataset.originalText || "Unggah foto";
        fileInput.value = "";
      }
    });
  });
})();
