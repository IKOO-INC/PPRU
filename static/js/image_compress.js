(() => {
  const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
  const COMPRESSION_STEPS = [
    { maxSide: 2400, quality: 0.84 },
    { maxSide: 2200, quality: 0.78 },
    { maxSide: 1920, quality: 0.72 },
    { maxSide: 1680, quality: 0.66 },
    { maxSide: 1440, quality: 0.59 },
    { maxSide: 1200, quality: 0.51 },
    { maxSide: 1000, quality: 0.43 },
    { maxSide: 820, quality: 0.35 },
  ];

  const decodeImage = async (file) => {
    if (typeof createImageBitmap === "function") {
      try {
        return await createImageBitmap(file, { imageOrientation: "from-image" });
      } catch (_error) {
        try {
          return await createImageBitmap(file);
        } catch (_fallbackError) {
          // Fall back to an image element for browsers with partial ImageBitmap support.
        }
      }
    }

    if (typeof Image !== "function" || typeof URL === "undefined" || typeof URL.createObjectURL !== "function") {
      throw new Error("Foto ini belum dapat diproses di perangkat ini. Coba simpan ulang sebagai JPG atau PNG.");
    }

    return new Promise((resolve, reject) => {
      const image = new Image();
      const objectUrl = URL.createObjectURL(file);
      const releaseUrl = () => URL.revokeObjectURL(objectUrl);
      image.onload = () => {
        releaseUrl();
        resolve({
          image,
          width: image.naturalWidth,
          height: image.naturalHeight,
          close() {},
        });
      };
      image.onerror = () => {
        releaseUrl();
        reject(new Error("Foto ini belum dapat dibaca. Coba simpan ulang sebagai JPG, PNG, atau WebP."));
      };
      image.src = objectUrl;
    });
  };

  const encodeCanvas = (canvas, mimeType, quality) => new Promise((resolve, reject) => {
    if (typeof canvas.toBlob === "function") {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("Foto belum dapat dikompres. Silakan coba format gambar lain."));
      }, mimeType, quality);
      return;
    }

    try {
      const dataUrl = canvas.toDataURL(mimeType, quality);
      const [header, encoded] = dataUrl.split(",");
      const actualMimeType = header.match(/^data:([^;]+)/)?.[1] || mimeType;
      const binary = atob(encoded);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      resolve(new Blob([bytes], { type: actualMimeType }));
    } catch (error) {
      reject(error);
    }
  });

  const filenameForBlob = (filename, blob) => {
    const baseName = (filename || "foto").replace(/\.[^.]+$/, "").slice(0, 100) || "foto";
    const extension = blob.type === "image/jpeg" ? ".jpg" : blob.type === "image/png" ? ".png" : ".webp";
    return `${baseName}-kompres${extension}`;
  };

  window.compressPhotoForUpload = async (file) => {
    if (!file || file.size <= MAX_UPLOAD_BYTES) return file;
    if (file.type && !file.type.toLowerCase().startsWith("image/")) {
      throw new Error("Pilih file foto JPG, PNG, GIF, atau WebP.");
    }

    let image;
    try {
      image = await decodeImage(file);
    } catch (error) {
      if (error instanceof Error && error.message) throw error;
      throw new Error("Foto belum dapat diproses. Coba simpan ulang sebagai JPG, PNG, atau WebP.");
    }

    try {
      const source = image.image || image;
      const sourceWidth = Number(image.width || source.naturalWidth || source.width);
      const sourceHeight = Number(image.height || source.naturalHeight || source.height);
      if (!sourceWidth || !sourceHeight) {
        throw new Error("Ukuran foto tidak dapat dibaca. Coba simpan ulang sebagai JPG, PNG, atau WebP.");
      }

      let smallestBlob = null;
      for (const step of COMPRESSION_STEPS) {
        const scale = Math.min(1, step.maxSide / Math.max(sourceWidth, sourceHeight));
        const width = Math.max(1, Math.round(sourceWidth * scale));
        const height = Math.max(1, Math.round(sourceHeight * scale));
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext("2d");
        if (!context) throw new Error("Foto belum dapat diproses di perangkat ini. Coba simpan ulang sebagai JPG atau PNG.");
        context.drawImage(source, 0, 0, width, height);

        let blob = await encodeCanvas(canvas, "image/webp", step.quality);
        if (blob.type !== "image/webp") {
          context.clearRect(0, 0, width, height);
          context.fillStyle = "#ffffff";
          context.fillRect(0, 0, width, height);
          context.drawImage(source, 0, 0, width, height);
          blob = await encodeCanvas(canvas, "image/jpeg", step.quality);
        }
        if (!smallestBlob || blob.size < smallestBlob.size) smallestBlob = blob;
        if (blob.size <= MAX_UPLOAD_BYTES) {
          return new File([blob], filenameForBlob(file.name, blob), {
            type: blob.type || "image/webp",
            lastModified: file.lastModified || Date.now(),
          });
        }
      }

      if (smallestBlob && smallestBlob.size <= MAX_UPLOAD_BYTES) {
        return new File([smallestBlob], filenameForBlob(file.name, smallestBlob), {
          type: smallestBlob.type || "image/webp",
          lastModified: file.lastModified || Date.now(),
        });
      }
      throw new Error("Foto masih terlalu besar setelah dikompres. Coba pilih foto lain atau simpan ulang dengan ukuran lebih kecil.");
    } finally {
      if (typeof image.close === "function") image.close();
    }
  };
})();
