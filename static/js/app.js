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

  document.querySelectorAll("form[data-demo-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const status = form.querySelector(".form-status") || form.parentElement.querySelector(".form-status");
      if (status) status.textContent = "Terima kasih. Formulir contoh ini belum terhubung ke backend.";
      form.reset();
    });
  });

  const hafalanForm = document.querySelector("#hafalan-form");
  hafalanForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const start = Number(document.querySelector("#start-juz")?.value || 1);
    const end = Number(document.querySelector("#end-juz")?.value || 30);
    const status = document.querySelector("#hafalan-status");
    if (start > end) {
      if (status) status.textContent = "Juz awal harus lebih kecil atau sama dengan juz akhir.";
      return;
    }
    if (status) status.textContent = "Pengaturan latihan tersimpan. Fitur ujian akan dihubungkan ke backend pada tahap berikutnya.";
  });
})();
