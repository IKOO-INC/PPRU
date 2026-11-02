(() => {
  const panel = document.querySelector("[data-hafalan-recap]");
  if (!panel) return;

  const body = panel.querySelector("[data-hafalan-ranking-body]");
  const trackFilter = panel.querySelector("[data-hafalan-track-filter]");
  const sortControl = panel.querySelector("[data-hafalan-sort]");
  const searchControl = panel.querySelector("[data-hafalan-search]");
  const emptyMessage = panel.querySelector("[data-hafalan-empty]");
  if (!body || !trackFilter || !sortControl || !searchControl) return;

  const rows = Array.from(body.querySelectorAll("[data-hafalan-ranking-row]"));
  const collator = new Intl.Collator("id", { sensitivity: "base", numeric: true });
  const number = (row, attribute) => Number(row.dataset[attribute] || 0);
  const compareByScore = (left, right) => (
    number(right, "score") - number(left, "score")
    || number(right, "correct") - number(left, "correct")
    || number(right, "total") - number(left, "total")
    || number(right, "attempts") - number(left, "attempts")
    || collator.compare(left.dataset.name || "", right.dataset.name || "")
  );

  const render = () => {
    const track = trackFilter.value;
    const query = searchControl.value.trim().toLocaleLowerCase("id");
    const visibleRows = rows.filter((row) => (
      (track === "all" || row.dataset.track === track)
      && (!query || (row.dataset.name || "").toLocaleLowerCase("id").includes(query))
    ));

    visibleRows.sort((left, right) => {
      if (sortControl.value === "name") {
        return collator.compare(left.dataset.name || "", right.dataset.name || "") || compareByScore(left, right);
      }
      if (sortControl.value === "recent") {
        return (Date.parse(right.dataset.latest || "") || 0) - (Date.parse(left.dataset.latest || "") || 0)
          || compareByScore(left, right);
      }
      if (sortControl.value === "attempts") {
        return number(right, "attempts") - number(left, "attempts") || compareByScore(left, right);
      }
      return compareByScore(left, right);
    });

    const fragment = document.createDocumentFragment();
    visibleRows.forEach((row, index) => {
      row.querySelector("[data-ranking-position]").textContent = String(index + 1);
      fragment.append(row);
    });
    rows.filter((row) => !visibleRows.includes(row)).forEach((row) => {
      row.hidden = true;
      fragment.append(row);
    });
    body.append(fragment);
    visibleRows.forEach((row) => { row.hidden = false; });
    if (emptyMessage) emptyMessage.hidden = visibleRows.length > 0;
  };

  trackFilter.addEventListener("change", render);
  sortControl.addEventListener("change", render);
  searchControl.addEventListener("input", render);
  render();
})();
