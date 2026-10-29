(() => {
  const setupForm = document.querySelector("#hafalan-setup");
  if (!setupForm) return;

  const catalogElement = document.querySelector("#hafalan-book-catalog");
  let catalog;
  try {
    catalog = JSON.parse(catalogElement?.textContent || "[]");
  } catch (_error) {
    catalog = [];
  }
  const booksById = new Map(catalog.map((book) => [book.id, book]));
  const rowsByBook = new Map();
  const bookSelect = document.querySelector("#hafalan-book");
  const chapterStart = document.querySelector("#chapter-start");
  const chapterEnd = document.querySelector("#chapter-end");
  const questionCount = document.querySelector("#question-count");
  const rangeHint = document.querySelector("#range-hint");
  const status = document.querySelector("#hafalan-status");
  const startButton = document.querySelector("#hafalan-start");
  const quizView = document.querySelector("#hafalan-quiz");
  const resultsView = document.querySelector("#hafalan-results");
  const guide = document.querySelector(".hafalan-guide");
  const nextButton = document.querySelector("#quiz-next");
  const answerOptions = document.querySelector("#answer-options");
  const answerStatus = document.querySelector("#quiz-answer-status");
  const reviewButton = document.querySelector("#review-toggle");
  const reviewPanel = document.querySelector("#review-panel");
  const certificate = document.querySelector("#hafalan-certificate");
  let quiz = null;

  const shuffle = (items) => {
    const shuffled = [...items];
    for (let index = shuffled.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(Math.random() * (index + 1));
      [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
    }
    return shuffled;
  };

  const selectedBook = () => booksById.get(bookSelect.value);

  const updateRangeHint = () => {
    const book = selectedBook();
    if (!book) return;
    const startIndex = Number(chapterStart.value);
    const endIndex = Number(chapterEnd.value);
    if (!Number.isInteger(startIndex) || !Number.isInteger(endIndex) || endIndex < startIndex) return;
    const chapters = book.chapters.slice(startIndex, endIndex + 1);
    const available = chapters.reduce((sum, chapter) => sum + chapter.count, 0);
    questionCount.max = String(available);
    questionCount.min = "1";
    if (questionCount.value && Number(questionCount.value) > available) questionCount.value = String(available);
    const start = book.chapters[startIndex];
    const end = book.chapters[endIndex];
    rangeHint.textContent = `${available} bait tersedia dari “${start.label}” sampai “${end.label}”.`;
  };

  const populateChapters = () => {
    const book = selectedBook();
    chapterStart.replaceChildren();
    chapterEnd.replaceChildren();
    if (!book) return;

    book.chapters.forEach((chapter) => {
      const startOption = document.createElement("option");
      startOption.value = String(chapter.index);
      startOption.textContent = chapter.label;
      chapterStart.append(startOption);

      const endOption = document.createElement("option");
      endOption.value = String(chapter.index);
      endOption.textContent = chapter.label;
      chapterEnd.append(endOption);
    });
    chapterStart.value = "0";
    chapterEnd.value = "0";
    updateRangeHint();
  };

  const fetchBookRows = async (bookId) => {
    if (rowsByBook.has(bookId)) return rowsByBook.get(bookId);
    const response = await fetch(`/hafalan/data/${encodeURIComponent(bookId)}`, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Data kitab belum dapat dimuat. Coba muat ulang halaman.");
    const rows = await response.json();
    if (!Array.isArray(rows) || !rows.length) throw new Error("Data bait untuk kitab ini masih kosong.");
    rowsByBook.set(bookId, rows);
    return rows;
  };

  const renderQuestion = () => {
    const question = quiz.questions[quiz.questionIndex];
    const book = booksById.get(quiz.bookId);
    const progress = ((quiz.questionIndex + 1) / quiz.questions.length) * 100;

    document.querySelector("#quiz-book-label").textContent = book.title;
    document.querySelector("#quiz-counter").textContent = `Soal ${quiz.questionIndex + 1} dari ${quiz.questions.length}`;
    document.querySelector("#quiz-progress-bar").style.width = `${progress}%`;
    document.querySelector("#quiz-chapter").textContent = question.record.bab;
    document.querySelector("#nadzom-prompt").textContent = question.record.syathr1;
    answerOptions.replaceChildren();
    answerStatus.textContent = question.selectedAnswer ? "Jawaban tersimpan." : "";

    question.choices.forEach((choice, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "hafalan-answer";
      button.dir = "rtl";
      button.lang = "ar";
      button.setAttribute("aria-pressed", String(question.selectedAnswer === choice));
      if (question.selectedAnswer === choice) button.classList.add("is-selected");

      const letter = document.createElement("span");
      letter.className = "hafalan-answer-letter";
      letter.setAttribute("aria-hidden", "true");
      letter.textContent = String.fromCharCode(65 + index);
      const text = document.createElement("span");
      text.className = "hafalan-answer-text";
      text.textContent = choice;
      button.append(letter, text);
      button.addEventListener("click", () => {
        question.selectedAnswer = choice;
        answerOptions.querySelectorAll(".hafalan-answer").forEach((option) => {
          const selected = option === button;
          option.classList.toggle("is-selected", selected);
          option.setAttribute("aria-pressed", String(selected));
        });
        answerStatus.textContent = "Jawaban tersimpan. Hasil akan diketahui setelah semua soal selesai.";
        nextButton.disabled = false;
      });
      answerOptions.append(button);
    });

    nextButton.disabled = !question.selectedAnswer;
    nextButton.textContent = quiz.questionIndex === quiz.questions.length - 1 ? "Selesaikan ujian" : "Soal berikutnya";
  };

  const motivationFor = (score) => {
    if (score === 100) return "MasyaAllah, semua sambungan tepat! Pertahankan murajaah dan terus perdalam ilmu nahwu.";
    if (score >= 80) return "Hasil yang sangat baik. Sedikit pengulangan lagi akan membuat hafalan semakin kuat.";
    if (score >= 60) return "Usahamu sudah bagus. Tandai bait yang keliru, lalu ulangi perlahan sampai melekat.";
    return "Jangan berkecil hati. Setiap bait yang diulang adalah langkah menuju hafalan yang lebih kuat. Coba lagi dengan semangat.";
  };

  const appendReviewLine = (container, label, value, direction = "") => {
    const line = document.createElement("p");
    line.className = "hafalan-review-line";
    const title = document.createElement("strong");
    title.textContent = `${label}: `;
    const text = document.createElement("span");
    text.textContent = value || "(belum ada jawaban)";
    if (direction) {
      text.dir = direction;
      text.lang = "ar";
    }
    line.append(title, text);
    container.append(line);
  };

  const showResults = () => {
    const correctCount = quiz.questions.filter((question) => question.selectedAnswer === question.record.syathr2).length;
    const score = Math.round((correctCount / quiz.questions.length) * 100);
    const book = booksById.get(quiz.bookId);
    const start = book.chapters[quiz.startIndex];
    const end = book.chapters[quiz.endIndex];
    const rangeLabel = start.index === end.index ? start.label : `${start.label} — ${end.label}`;

    document.querySelector("#score-value").textContent = `${score}%`;
    document.querySelector("#score-summary").textContent = `${correctCount} dari ${quiz.questions.length} sambungan tepat`;
    document.querySelector("#result-book").textContent = book.title;
    document.querySelector("#result-range").textContent = `Bab: ${rangeLabel}`;
    document.querySelector("#motivation-message").textContent = motivationFor(score);

    const mistakesList = document.querySelector("#mistakes-list");
    mistakesList.replaceChildren();
    const mistakes = quiz.questions
      .map((question, index) => ({ question, index }))
      .filter(({ question }) => question.selectedAnswer !== question.record.syathr2);
    if (!mistakes.length) {
      const perfect = document.createElement("p");
      perfect.className = "hafalan-perfect-message";
      perfect.textContent = "Tidak ada kesalahan pada tantangan ini. Semua jawabanmu tepat!";
      mistakesList.append(perfect);
    } else {
      mistakes.forEach(({ question, index }) => {
        const item = document.createElement("article");
        item.className = "hafalan-mistake-item";
        const heading = document.createElement("h4");
        heading.textContent = `Soal ${index + 1} · ${question.record.bab}`;
        const firstHalf = document.createElement("p");
        firstHalf.className = "hafalan-review-nadzom";
        firstHalf.dir = "rtl";
        firstHalf.lang = "ar";
        firstHalf.textContent = question.record.syathr1;
        item.append(heading, firstHalf);
        appendReviewLine(item, "Jawabanmu", question.selectedAnswer, "rtl");
        appendReviewLine(item, "Sambungan yang tepat", question.record.syathr2, "rtl");
        mistakesList.append(item);
      });
    }

    document.querySelector("#certificate-name").textContent = quiz.participant;
    document.querySelector("#certificate-book").textContent = book.title;
    document.querySelector("#certificate-range").textContent = `Rentang bab: ${rangeLabel}`;
    document.querySelector("#certificate-score").textContent = `${score}% (${correctCount}/${quiz.questions.length})`;
    document.querySelector("#certificate-date").textContent = new Intl.DateTimeFormat("id-ID", {
      day: "numeric", month: "long", year: "numeric",
    }).format(new Date());

    setupForm.hidden = true;
    quizView.hidden = true;
    resultsView.hidden = false;
    guide.hidden = true;
    resultsView.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  bookSelect.addEventListener("change", populateChapters);
  chapterStart.addEventListener("change", () => {
    if (Number(chapterEnd.value) < Number(chapterStart.value)) chapterEnd.value = chapterStart.value;
    updateRangeHint();
  });
  chapterEnd.addEventListener("change", () => {
    if (Number(chapterEnd.value) < Number(chapterStart.value)) chapterStart.value = chapterEnd.value;
    updateRangeHint();
  });
  questionCount.addEventListener("input", updateRangeHint);
  populateChapters();

  setupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    status.textContent = "";
    const book = selectedBook();
    const startIndex = Number(chapterStart.value);
    const endIndex = Number(chapterEnd.value);
    const count = Number(questionCount.value);
    const name = document.querySelector("#participant-name").value.trim();
    const start = book?.chapters[startIndex];
    const end = book?.chapters[endIndex];
    const available = book?.chapters.slice(startIndex, endIndex + 1).reduce((sum, chapter) => sum + chapter.count, 0) || 0;

    if (!name) {
      status.textContent = "Nama peserta perlu diisi.";
      return;
    }
    if (!book || !start || !end || startIndex > endIndex) {
      status.textContent = "Pilih kitab dan rentang bab yang valid.";
      return;
    }
    if (!Number.isInteger(count) || count < 1 || count > available) {
      status.textContent = `Jumlah soal harus antara 1 sampai ${available}.`;
      return;
    }

    startButton.disabled = true;
    startButton.textContent = "Menyiapkan soal…";
    try {
      const allRows = await fetchBookRows(book.id);
      const rangeRows = allRows.slice(start.start_index, end.end_index + 1)
        .filter((row) => row.syathr1 && row.syathr2);
      if (rangeRows.length < count) throw new Error("Jumlah bait pada rentang bab tidak mencukupi.");
      const questions = shuffle(rangeRows).slice(0, count).map((record) => {
        const distractors = shuffle([...new Set(allRows
          .map((row) => String(row.syathr2 || "").trim())
          .filter((line) => line && line !== record.syathr2))]).slice(0, 3);
        return {
          record,
          choices: shuffle([record.syathr2, ...distractors]),
          selectedAnswer: null,
        };
      });
      quiz = {
        bookId: book.id,
        startIndex,
        endIndex,
        participant: name,
        questions,
        questionIndex: 0,
      };
      setupForm.hidden = true;
      guide.hidden = true;
      quizView.hidden = false;
      renderQuestion();
      quizView.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      status.textContent = error.message || "Soal belum dapat dimuat. Silakan coba lagi.";
    } finally {
      startButton.disabled = false;
      startButton.innerHTML = 'Mulai Tantangan <span aria-hidden="true">→</span>';
    }
  });

  nextButton.addEventListener("click", () => {
    if (!quiz?.questions[quiz.questionIndex]?.selectedAnswer) return;
    if (quiz.questionIndex === quiz.questions.length - 1) {
      showResults();
      return;
    }
    quiz.questionIndex += 1;
    renderQuestion();
  });

  reviewButton.addEventListener("click", () => {
    const opening = reviewPanel.hidden;
    reviewPanel.hidden = !opening;
    reviewButton.setAttribute("aria-expanded", String(opening));
    reviewButton.textContent = opening ? "Sembunyikan Evaluasi" : "Lihat Kesalahan & Motivasi";
    if (opening) reviewPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });

  document.querySelector("#certificate-print").addEventListener("click", () => {
    certificate.classList.add("is-printing");
    certificate.setAttribute("aria-hidden", "false");
    const finishPrint = () => {
      certificate.classList.remove("is-printing");
      certificate.setAttribute("aria-hidden", "true");
    };
    window.addEventListener("afterprint", finishPrint, { once: true });
    window.print();
    window.setTimeout(finishPrint, 3000);
  });
})();
