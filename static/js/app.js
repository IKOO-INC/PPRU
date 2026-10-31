(() => {
  const toggle = document.querySelector(".nav-toggle");
  const navigation = document.querySelector("#site-navigation");

  if (toggle && navigation) {
    const closeMenu = () => {
      toggle.setAttribute("aria-expanded", "false");
      toggle.setAttribute("aria-label", "Buka menu");
      navigation.classList.remove("is-open");
    };

    toggle.addEventListener("click", () => {
      const opening = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(opening));
      toggle.setAttribute("aria-label", opening ? "Tutup menu" : "Buka menu");
      navigation.classList.toggle("is-open", opening);
    });

    navigation.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenu();
    });
    window.addEventListener("resize", () => {
      if (window.innerWidth > 740) closeMenu();
    });
  }

  const navDropdowns = Array.from(document.querySelectorAll("[data-nav-dropdown]"));
  const closeNavDropdown = (dropdown) => {
    dropdown.classList.remove("is-open");
    dropdown.querySelector("[data-nav-dropdown-toggle]")?.setAttribute("aria-expanded", "false");
  };
  navDropdowns.forEach((dropdown) => {
    const dropdownToggle = dropdown.querySelector("[data-nav-dropdown-toggle]");
    if (!dropdownToggle) return;
    dropdownToggle.addEventListener("click", () => {
      const opening = dropdownToggle.getAttribute("aria-expanded") !== "true";
      navDropdowns.forEach((otherDropdown) => {
        if (otherDropdown !== dropdown) closeNavDropdown(otherDropdown);
      });
      dropdown.classList.toggle("is-open", opening);
      dropdownToggle.setAttribute("aria-expanded", String(opening));
    });
    document.addEventListener("click", (event) => {
      if (!dropdown.contains(event.target)) closeNavDropdown(dropdown);
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") navDropdowns.forEach(closeNavDropdown);
  });

  const newsCards = Array.from(document.querySelectorAll("[data-news-card]"));
  const searchInput = document.querySelector("#news-search");
  const categoryButtons = Array.from(document.querySelectorAll("[data-news-filter]"));
  const tagButtons = Array.from(document.querySelectorAll("[data-news-tag]"));
  const emptyState = document.querySelector(".empty-state");
  let activeCategory = "all";
  let activeQuery = "";

  const filterNews = () => {
    if (!newsCards.length) return;
    let visibleCount = 0;
    newsCards.forEach((card) => {
      const category = (card.dataset.category || "").toLowerCase();
      const searchText = (card.dataset.search || card.textContent).toLowerCase();
      const matchesCategory = activeCategory === "all" || category === activeCategory;
      const matchesQuery = !activeQuery || searchText.includes(activeQuery);
      const isVisible = matchesCategory && matchesQuery;
      card.hidden = !isVisible;
      if (isVisible) visibleCount += 1;
    });
    if (emptyState) emptyState.hidden = visibleCount !== 0;
  };

  searchInput?.addEventListener("input", () => {
    activeQuery = searchInput.value.trim().toLowerCase();
    filterNews();
  });
  categoryButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activeCategory = button.dataset.newsFilter || "all";
      categoryButtons.forEach((item) => item.classList.toggle("is-active", item === button));
      filterNews();
    });
  });
  tagButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activeQuery = (button.dataset.newsTag || "").toLowerCase();
      if (searchInput) searchInput.value = button.textContent.trim();
      filterNews();
    });
  });

  const galleryCards = Array.from(document.querySelectorAll("[data-gallery-card]"));
  document.querySelectorAll("[data-gallery-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      const category = button.dataset.galleryFilter || "all";
      document.querySelectorAll("[data-gallery-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
      galleryCards.forEach((card) => {
        card.hidden = category !== "all" && card.dataset.category !== category;
      });
    });
  });

  const galleryLightbox = document.querySelector("#gallery-lightbox");
  if (galleryLightbox) {
    const lightboxImage = document.querySelector("#gallery-lightbox-image");
    const lightboxTitle = document.querySelector("#gallery-lightbox-title");
    const lightboxCaption = document.querySelector("#gallery-lightbox-caption");
    const downloadLink = document.querySelector("#gallery-lightbox-download");
    const shareButton = document.querySelector("#gallery-lightbox-share");
    const lightboxStatus = document.querySelector("#gallery-lightbox-status");
    const closeButton = document.querySelector("#gallery-lightbox-close");
    let activeGalleryPhoto = null;

    const attachmentUrl = (imageUrl) => {
      const parsed = new URL(imageUrl, window.location.href);
      if (parsed.hostname !== "res.cloudinary.com") return parsed.href;
      const marker = "/image/upload/";
      const [prefix, suffix] = parsed.pathname.split(marker);
      if (suffix === undefined) return parsed.href;
      const segments = suffix.split("/");
      const versionIndex = segments.findIndex((segment) => /^v\d+$/.test(segment));
      segments.splice(versionIndex < 0 ? 0 : versionIndex, 0, "f_jpg,q_auto:good,fl_attachment");
      parsed.pathname = `${prefix}${marker}${segments.join("/")}`;
      return parsed.href;
    };

    const fileName = (title) => {
      const safeTitle = (title || "foto-galeri")
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .toLowerCase();
      return `${safeTitle || "foto-galeri"}.jpg`;
    };

    document.querySelectorAll("[data-gallery-open]").forEach((button) => {
      button.addEventListener("click", () => {
        activeGalleryPhoto = {
          url: button.dataset.galleryUrl || button.querySelector("img")?.src || "",
          title: button.dataset.galleryTitle || "Foto galeri",
          caption: button.dataset.galleryCaption || "",
        };
        if (!activeGalleryPhoto.url) return;
        lightboxImage.src = activeGalleryPhoto.url;
        lightboxImage.alt = activeGalleryPhoto.title;
        lightboxTitle.textContent = activeGalleryPhoto.title;
        lightboxCaption.textContent = activeGalleryPhoto.caption;
        lightboxCaption.hidden = !activeGalleryPhoto.caption;
        lightboxStatus.textContent = "";
        downloadLink.href = attachmentUrl(activeGalleryPhoto.url);
        downloadLink.download = fileName(activeGalleryPhoto.title);
        galleryLightbox.showModal();
        closeButton.focus();
      });
    });

    closeButton.addEventListener("click", () => galleryLightbox.close());
    galleryLightbox.addEventListener("click", (event) => {
      if (event.target === galleryLightbox) galleryLightbox.close();
    });
    galleryLightbox.addEventListener("close", () => {
      lightboxImage.removeAttribute("src");
      activeGalleryPhoto = null;
    });

    shareButton.addEventListener("click", async () => {
      if (!activeGalleryPhoto) return;
      const shareData = {
        title: activeGalleryPhoto.title,
        text: activeGalleryPhoto.caption || activeGalleryPhoto.title,
        url: activeGalleryPhoto.url,
      };
      try {
        if (navigator.share) {
          await navigator.share(shareData);
          lightboxStatus.textContent = "Foto siap dibagikan.";
        } else if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(activeGalleryPhoto.url);
          lightboxStatus.textContent = "Tautan foto berhasil disalin.";
        } else {
          const temporaryInput = document.createElement("textarea");
          temporaryInput.value = activeGalleryPhoto.url;
          temporaryInput.setAttribute("readonly", "");
          temporaryInput.style.position = "fixed";
          temporaryInput.style.opacity = "0";
          document.body.append(temporaryInput);
          temporaryInput.select();
          const copied = document.execCommand("copy");
          temporaryInput.remove();
          lightboxStatus.textContent = copied ? "Tautan foto berhasil disalin." : activeGalleryPhoto.url;
        }
      } catch (error) {
        if (error.name !== "AbortError") lightboxStatus.textContent = "Tautan foto belum dapat dibagikan. Silakan coba lagi.";
      }
    });
  }

  document.querySelectorAll("form[data-confirm-delete]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm("Hapus berita ini? Tindakan ini tidak dapat dibatalkan.")) event.preventDefault();
    });
  });

  document.querySelectorAll("form[data-demo-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const status = form.querySelector(".form-status") || form.parentElement.querySelector(".form-status");
      if (status) status.textContent = "Terima kasih. Formulir contoh ini belum terhubung ke backend.";
      form.reset();
    });
  });

})();
