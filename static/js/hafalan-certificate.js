(() => {
  const certificate = document.querySelector("#hafalan-certificate");
  const frame = document.querySelector("#hafalan-certificate-frame");
  if (!certificate || !frame) return;

  let renderPromise = null;
  const waitForPaint = () => new Promise((resolve) => window.requestAnimationFrame(() => window.requestAnimationFrame(resolve)));

  const activeStatus = (button) => button.closest(".hafalan-results")?.querySelector("[data-certificate-status]");
  const setStatus = (button, message) => {
    const status = activeStatus(button);
    if (status) status.textContent = message;
  };
  const participantSlug = () => {
    const name = document.querySelector("#certificate-name")?.textContent || "peserta";
    return name.normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "peserta";
  };
  const downloadBlob = (blob, extension) => {
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = `sertifikat-hafalan-${participantSlug()}.${extension}`;
    link.hidden = true;
    document.body.append(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  };
  const canvasBlob = (canvas, mimeType) => new Promise((resolve, reject) => {
    if (typeof canvas.toBlob === "function") {
      canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("Berkas gambar sertifikat belum dapat dibuat.")), mimeType, 0.94);
      return;
    }
    try {
      const dataUrl = canvas.toDataURL(mimeType, 0.94);
      const binary = atob(dataUrl.split(",")[1]);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      resolve(new Blob([bytes], { type: mimeType }));
    } catch (error) {
      reject(error);
    }
  });

  const renderCertificate = async () => {
    if (renderPromise) return renderPromise;
    if (typeof window.html2canvas !== "function") throw new Error("Fitur gambar sertifikat belum termuat. Muat ulang halaman dan coba lagi.");
    certificate.classList.add("is-exporting");
    certificate.setAttribute("aria-hidden", "false");
    renderPromise = (async () => {
      try {
        if (document.fonts?.ready) await document.fonts.ready;
        const logo = frame.querySelector("img");
        if (logo?.decode) await logo.decode().catch(() => {});
        await waitForPaint();
        return await window.html2canvas(frame, {
          backgroundColor: "#fcfdfb",
          scale: 2,
          useCORS: true,
          allowTaint: false,
          logging: false,
          windowWidth: Math.max(window.innerWidth, frame.offsetWidth + 36),
          windowHeight: Math.max(window.innerHeight, frame.offsetHeight + 36),
          scrollX: 0,
          scrollY: 0,
        });
      } finally {
        certificate.classList.remove("is-exporting");
        certificate.setAttribute("aria-hidden", "true");
        renderPromise = null;
      }
    })();
    return renderPromise;
  };

  const printCertificate = () => {
    certificate.classList.add("is-printing");
    certificate.setAttribute("aria-hidden", "false");
    let finished = false;
    const finishPrint = () => {
      if (finished) return;
      finished = true;
      certificate.classList.remove("is-printing");
      certificate.setAttribute("aria-hidden", "true");
      window.removeEventListener("afterprint", finishPrint);
    };
    window.addEventListener("afterprint", finishPrint, { once: true });
    window.print();
    window.setTimeout(finishPrint, 5000);
  };

  const exportImage = async (button, extension) => {
    const canvas = await renderCertificate();
    const mimeType = extension === "jpg" ? "image/jpeg" : "image/png";
    const blob = await canvasBlob(canvas, mimeType);
    downloadBlob(blob, extension);
    setStatus(button, `Sertifikat ${extension.toUpperCase()} berhasil diunduh.`);
  };

  const shareCertificate = async (button) => {
    const canvas = await renderCertificate();
    const blob = await canvasBlob(canvas, "image/png");
    const file = typeof File === "function"
      ? new File([blob], `sertifikat-hafalan-${participantSlug()}.png`, { type: "image/png" })
      : null;
    const shareData = {
      files: file ? [file] : [],
      title: document.querySelector("#certificate-subtitle")?.textContent || "Sertifikat hafalan",
      text: `Sertifikat tantangan hafalan atas nama ${document.querySelector("#certificate-name")?.textContent || "peserta"}.`,
    };
    if (file && navigator.share && (!navigator.canShare || navigator.canShare({ files: [file] }))) {
      try {
        await navigator.share(shareData);
        setStatus(button, "Sertifikat berhasil dibagikan.");
      } catch (error) {
        if (error?.name === "AbortError") {
          setStatus(button, "Berbagi dibatalkan.");
          return;
        }
        downloadBlob(blob, "png");
        setStatus(button, "Berbagi langsung tidak tersedia. Sertifikat PNG diunduh agar dapat dibagikan.");
      }
      return;
    }
    downloadBlob(blob, "png");
    setStatus(button, "Perangkat ini belum mendukung berbagi berkas langsung. Sertifikat PNG diunduh agar dapat dibagikan.");
  };

  document.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-certificate-action]");
    if (!button) return;
    event.preventDefault();
    const action = button.dataset.certificateAction;
    if (action === "print") {
      printCertificate();
      return;
    }
    if (button.disabled) return;
    button.disabled = true;
    setStatus(button, action === "share" ? "Menyiapkan sertifikat untuk dibagikan…" : "Menyiapkan gambar sertifikat…");
    try {
      if (action === "png" || action === "jpg") await exportImage(button, action);
      else if (action === "share") await shareCertificate(button);
    } catch (error) {
      setStatus(button, error?.message || "Sertifikat belum dapat diekspor. Silakan coba lagi.");
    } finally {
      button.disabled = false;
    }
  });
})();
