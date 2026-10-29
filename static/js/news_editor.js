(() => {
  const editor = document.querySelector("#article-editor");
  const hiddenBody = document.querySelector("#article-body-html");
  const form = document.querySelector("#news-editor-form");
  if (!editor || !hiddenBody || !form) return;

  const buttons = Array.from(document.querySelectorAll("[data-editor-command]"));
  buttons.forEach((button) => {
    button.addEventListener("mousedown", (event) => event.preventDefault());
    button.addEventListener("click", () => {
      editor.focus();
      const command = button.dataset.editorCommand;
      const value = button.dataset.editorValue || null;
      if (command === "createLink") {
        const url = window.prompt("Masukkan URL tautan (https://...)");
        if (url) document.execCommand(command, false, url);
      } else {
        document.execCommand(command, false, value);
      }
      hiddenBody.value = editor.innerHTML;
    });
  });

  form.addEventListener("submit", () => {
    hiddenBody.value = editor.innerHTML;
  });
})();
