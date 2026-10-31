(() => {
  const editor = document.querySelector("[data-madrasah-class-editor]");
  if (!editor) return;

  const grid = editor.querySelector("[data-class-grid]");
  const addButton = editor.querySelector("[data-add-class]");
  const cardTemplate = document.querySelector("#madrasah-class-card-template");
  const emptyState = editor.querySelector("[data-class-empty]");
  const countLabel = document.querySelector("[data-class-count]");
  const maxClasses = Number(editor.dataset.maxClasses) || 30;
  if (!grid || !addButton || !cardTemplate) return;

  const cards = () => [...grid.querySelectorAll("[data-class-card]")];

  const refreshCards = () => {
    const currentCards = cards();
    currentCards.forEach((card, index) => {
      const number = String(index + 1).padStart(2, "0");
      const nameField = card.querySelector("[data-class-name]");
      const numberLabel = card.querySelector("[data-class-number]");
      const titleLabel = card.querySelector("[data-class-title]");
      const removeButton = card.querySelector("[data-remove-class]");
      if (numberLabel) numberLabel.textContent = number;
      if (titleLabel) titleLabel.textContent = nameField?.value.trim() || "Kelas baru";
      if (removeButton) {
        removeButton.setAttribute(
          "aria-label",
          `Hapus kelas ${nameField?.value.trim() || number}`,
        );
      }
    });

    if (countLabel) countLabel.textContent = String(currentCards.length);
    if (emptyState) emptyState.hidden = currentCards.length > 0;
    addButton.disabled = currentCards.length >= maxClasses;
    addButton.setAttribute(
      "aria-label",
      currentCards.length >= maxClasses
        ? `Batas ${maxClasses} kelas sudah tercapai`
        : "Tambah kelas baru",
    );
  };

  addButton.addEventListener("click", () => {
    if (cards().length >= maxClasses) return;
    const fragment = cardTemplate.content.cloneNode(true);
    const card = fragment.querySelector("[data-class-card]");
    grid.appendChild(fragment);
    refreshCards();
    card?.querySelector("[data-class-name]")?.focus();
  });

  grid.addEventListener("input", (event) => {
    if (event.target.matches("[data-class-name]")) refreshCards();
  });

  grid.addEventListener("click", (event) => {
    const removeButton = event.target.closest("[data-remove-class]");
    if (!removeButton) return;
    removeButton.closest("[data-class-card]")?.remove();
    refreshCards();
    addButton.focus();
  });

  refreshCards();
})();
