(() => {
  const chooser = document.querySelector("#hafalan-chooser");
  const panels = {
    nadzom: document.querySelector("#nadzom-panel"),
    quran: document.querySelector("#quran-panel"),
  };
  const choiceButtons = [...document.querySelectorAll("[data-hafalan-choice]")];
  if (!chooser || !panels.nadzom || !panels.quran) return;

  const showChooser = () => {
    const activeKey = Object.entries(panels).find(([, panel]) => !panel.hidden)?.[0];
    chooser.hidden = false;
    Object.values(panels).forEach((panel) => { panel.hidden = true; });
    choiceButtons.forEach((button) => button.setAttribute("aria-expanded", "false"));
    chooser.scrollIntoView({ behavior: "smooth", block: "start" });
    const focusTarget = choiceButtons.find((button) => button.dataset.hafalanChoice === activeKey);
    focusTarget?.focus({ preventScroll: true });
  };

  choiceButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const selected = panels[button.dataset.hafalanChoice];
      if (!selected) return;
      chooser.hidden = true;
      Object.entries(panels).forEach(([key, panel]) => { panel.hidden = panel !== selected; });
      choiceButtons.forEach((choice) => choice.setAttribute("aria-expanded", String(choice === button)));
      selected.dispatchEvent(new Event("hafalan:open"));
      selected.scrollIntoView({ behavior: "smooth", block: "start" });
      selected.querySelector("[data-hafalan-back]")?.focus({ preventScroll: true });
    });
  });

  document.querySelectorAll("[data-hafalan-back]").forEach((button) => {
    button.addEventListener("click", showChooser);
  });
})();
