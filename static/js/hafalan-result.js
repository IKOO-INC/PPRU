(() => {
  const saveResult = async (payload, statusElement) => {
    if (!statusElement) return false;
    statusElement.textContent = "Menyimpan hasil tantangan…";
    try {
      const response = await fetch("/hafalan/hasil", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || result.saved !== true) throw new Error("Hasil belum dapat dicatat.");
      statusElement.textContent = result.temporary === true
        ? "Hasil tersimpan sementara dan mungkin belum tersedia."
        : "Hasil berhasil disimpan.";
      return true;
    } catch (_error) {
      statusElement.textContent = "Hasil belum tercatat di rekap. Kamu tetap dapat melihat hasil dan mengunduh sertifikat.";
      return false;
    }
  };

  window.PPRUHafalanResult = Object.freeze({ save: saveResult });
})();
