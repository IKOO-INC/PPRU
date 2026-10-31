(() => {
  const panel = document.querySelector("#quran-panel");
  const setupForm = document.querySelector("#quran-setup");
  if (!panel || !setupForm) return;

  const surahSelect = document.querySelector("#quran-surah");
  const surahJuzControls = document.querySelector("#quran-surah-juz-controls");
  const surahJuzSelect = document.querySelector("#quran-surah-juz");
  const juzControls = document.querySelector("#quran-juz-controls");
  const surahControls = document.querySelector("#quran-surah-controls");
  const juzStart = document.querySelector("#quran-juz-start");
  const juzEnd = document.querySelector("#quran-juz-end");
  const questionCount = document.querySelector("#quran-question-count");
  const rangeHint = document.querySelector("#quran-range-hint");
  const countHint = document.querySelector("#quran-count-hint");
  const status = document.querySelector("#quran-status");
  const startButton = document.querySelector("#quran-start");
  const quizView = document.querySelector("#quran-quiz");
  const resultsView = document.querySelector("#quran-results");
  const guide = panel.querySelector(".hafalan-guide");
  const answerOptions = document.querySelector("#quran-answer-options");
  const nextButton = document.querySelector("#quran-quiz-next");
  const answerStatus = document.querySelector("#quran-answer-status");
  const reviewButton = document.querySelector("#quran-review-toggle");
  const reviewPanel = document.querySelector("#quran-review-panel");
  let dataPromise = null;
  let quranData = null;
  let allPairs = [];
  let allAnswerTexts = [];
  let quiz = null;
  let currentMotivation = "";

  const QURAN_MOTIVATION = {
    excellent: [
      "MasyaAllah, sambunganmu tepat semua. Syukuri kemudahan ini dengan terus menjaga tilawah dan murajaah.",
      "Alhamdulillah, hafalanmu terjaga dengan baik hari ini. Istiqamahkan murajaah agar ayat semakin melekat.",
      "Hasil yang sangat baik. Semoga setiap ayat yang kamu jaga menjadi cahaya dan menambah kedekatan kepada Al-Qur’an.",
      "MasyaAllah, kamu mengingat ayat dengan cermat. Teruskan mengulang dan setorkan hafalan kepada guru.",
      "Semoga Allah memberkahi ikhtiarmu. Pertahankan kebiasaan murajaah, walau sedikit tetapi rutin.",
      "Sambunganmu tepat. Jangan berhenti pada capaian hari ini; rawat hafalan dengan tilawah dan pengulangan.",
    ],
    growing: [
      "Hafalan Al-Qur’an dijaga dengan murajaah yang berulang. Tandai ayat yang tertukar dan kembalilah padanya.",
      "Setiap ayat yang belum tepat menunjukkan bagian yang perlu disimak lagi. Ulangi dengan tenang bersama mushaf.",
      "Lanjutkan dengan jadwal murajaah yang ringan dan konsisten. Sedikit demi sedikit, hafalan akan semakin kuat.",
      "Coba dengarkan bacaan guru, perhatikan awal ayat, lalu tutup mushaf dan sambungkan kembali.",
      "Hasil hari ini adalah bahan belajar. Periksa ayat yang keliru, pahami letaknya, dan ulangi kembali nanti.",
      "Jaga semangatmu. Hafalan bertambah kuat melalui tilawah, setoran, dan pengulangan yang istiqamah.",
      "Tidak perlu tergesa-gesa. Baca dengan tartil, kenali hubungan antar-ayat, lalu lanjutkan murajaah.",
    ],
    keepGoing: [
      "Jangan berputus asa. Kembali ke mushaf, baca perlahan, dan ulangi ayat yang belum tersambung.",
      "Perjalanan menjaga Al-Qur’an membutuhkan sabar. Mulai lagi dari beberapa ayat dan minta bimbingan guru.",
      "Ayat yang terasa sulit bukan alasan untuk menyerah. Beri waktu untuk mengulang dan meneguhkan hafalan.",
      "Setiap tilawah dan murajaah adalah ikhtiar yang bernilai. Lanjutkan dengan niat yang baik dan hati yang tenang.",
      "Ambil pelajaran dari soal yang terlewat. Dengarkan ayatnya, baca berulang, lalu coba tantangan lagi.",
      "Hafalan tidak tumbuh dalam satu malam. Jaga rutinitas kecilmu dan bersandar pada bimbingan ahli Al-Qur’an.",
      "Tetap semangat. Berhenti sejenak untuk memahami, kemudian sambung kembali hafalan dengan lebih mantap.",
    ],
  };

  const shuffle = (items) => {
    const shuffled = [...items];
    for (let index = shuffled.length - 1; index > 0; index -= 1) {
      const swapIndex = Math.floor(Math.random() * (index + 1));
      [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
    }
    return shuffled;
  };

  const currentMode = () => setupForm.querySelector('input[name="quran_mode"]:checked')?.value || "surah";
  const formatNumber = (number) => new Intl.NumberFormat("id-ID").format(number);

  const buildPairs = (surahs) => {
    const pairs = [];
    surahs.forEach((surah) => {
      for (let index = 0; index < surah.ayahs.length - 1; index += 1) {
        const anchor = surah.ayahs[index];
        const next = surah.ayahs[index + 1];
        if (!anchor?.arab || !next?.arab) continue;
        pairs.push({ surah, anchor, next });
      }
    });
    return pairs;
  };

  const loadQuranData = () => {
    if (quranData) return Promise.resolve(quranData);
    if (dataPromise) return dataPromise;
    status.textContent = "Sedang memuat daftar surah dan ayat Al-Qur’an…";
    dataPromise = fetch(panel.dataset.quranDataUrl, {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    }).then((response) => {
      if (!response.ok) throw new Error("Data Al-Qur’an belum dapat dimuat. Periksa koneksi lalu coba lagi.");
      return response.json();
    }).then((data) => {
      if (!Array.isArray(data) || data.length !== 114 || data.some((surah) => !Array.isArray(surah.ayahs))) {
        throw new Error("Format data Al-Qur’an belum dapat dibaca.");
      }
      quranData = data;
      allPairs = buildPairs(data);
      allAnswerTexts = [...new Set(allPairs.map((pair) => pair.next.arab).filter(Boolean))];
      populateSelectors();
      updateModeControls();
      status.textContent = "Data Al-Qur’an siap. Nama lengkap wajib diisi sebelum memulai.";
      return quranData;
    }).catch((error) => {
      dataPromise = null;
      startButton.disabled = true;
      status.textContent = error.message || "Data Al-Qur’an belum dapat dimuat. Silakan coba lagi.";
      throw error;
    });
    return dataPromise;
  };

  const refreshSurahChoices = () => {
    const previousValue = surahSelect.value;
    const juzFilter = surahJuzSelect.value || "all";
    const eligibleSurahs = juzFilter === "all"
      ? null
      : new Set(allPairs
        .filter((pair) => pair.anchor.juz === Number(juzFilter) && pair.next.juz === Number(juzFilter))
        .map((pair) => pair.surah.number));
    surahSelect.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Pilih surah";
    surahSelect.append(placeholder);
    quranData.filter((surah) => !eligibleSurahs || eligibleSurahs.has(surah.number)).forEach((surah) => {
      const option = document.createElement("option");
      option.value = String(surah.number);
      option.textContent = `${surah.number}. ${surah.name} · ${surah.translation}`;
      surahSelect.append(option);
    });
    if (previousValue && [...surahSelect.options].some((option) => option.value === previousValue)) {
      surahSelect.value = previousValue;
    }
  };

  const populateSelectors = () => {
    surahJuzSelect.replaceChildren();
    const allJuzOption = document.createElement("option");
    allJuzOption.value = "all";
    allJuzOption.textContent = "Semua Juz";
    surahJuzSelect.append(allJuzOption);
    for (let juz = 1; juz <= 30; juz += 1) {
      const option = document.createElement("option");
      option.value = String(juz);
      option.textContent = `Juz ${juz}`;
      surahJuzSelect.append(option);
    }
    surahJuzSelect.value = "all";
    refreshSurahChoices();

    [juzStart, juzEnd].forEach((select) => {
      select.replaceChildren();
      for (let juz = 1; juz <= 30; juz += 1) {
        const option = document.createElement("option");
        option.value = String(juz);
        option.textContent = `Juz ${juz}`;
        select.append(option);
      }
    });
    juzStart.value = "1";
    juzEnd.value = "1";
    questionCount.disabled = false;
    startButton.disabled = false;
  };

  const pairsForCurrentMode = () => {
    const mode = currentMode();
    if (mode === "surah") {
      const surahNumber = Number(surahSelect.value);
      const juzFilter = surahJuzSelect.value || "all";
      return allPairs.filter((pair) => pair.surah.number === surahNumber
        && (juzFilter === "all" || (pair.anchor.juz === Number(juzFilter) && pair.next.juz === Number(juzFilter))));
    }
    if (mode === "juz-range") {
      const start = Number(juzStart.value);
      const end = Number(juzEnd.value);
      if (!Number.isInteger(start) || !Number.isInteger(end) || start > end) return [];
      return allPairs.filter((pair) => pair.anchor.juz >= start && pair.next.juz <= end);
    }
    return allPairs;
  };

  const updateModeControls = () => {
    const mode = currentMode();
    const isSurah = mode === "surah";
    const isJuzRange = mode === "juz-range";
    surahControls.hidden = !isSurah;
    surahJuzControls.hidden = !isSurah;
    juzControls.hidden = !isJuzRange;
    surahSelect.disabled = !quranData || !isSurah;
    surahJuzSelect.disabled = !quranData || !isSurah;
    juzStart.disabled = !quranData || !isJuzRange;
    juzEnd.disabled = !quranData || !isJuzRange;
    questionCount.disabled = !quranData;
    startButton.disabled = !quranData;

    if (!quranData) {
      rangeHint.textContent = "Menyiapkan daftar surah dan ayat…";
      return;
    }
    const pairs = pairsForCurrentMode();
    const maximum = Math.min(100, pairs.length);
    questionCount.max = String(maximum || 100);
    if (Number(questionCount.value) > maximum && maximum > 0) questionCount.value = String(maximum);

    if (isSurah) {
      const surah = quranData.find((item) => item.number === Number(surahSelect.value));
      const juzFilter = surahJuzSelect.value || "all";
      rangeHint.textContent = surah
        ? `${surah.name} (${surah.translation})${juzFilter === "all" ? "" : ` · Juz ${juzFilter}`} · ${formatNumber(pairs.length)} sambungan ayat tersedia.`
        : juzFilter === "all"
          ? "Pilih surah untuk melihat jumlah sambungan ayat yang tersedia."
          : `Pilih surah dalam Juz ${juzFilter} untuk melihat jumlah sambungan ayat.`;
    } else if (isJuzRange) {
      const start = Number(juzStart.value);
      const end = Number(juzEnd.value);
      rangeHint.textContent = start <= end
        ? `Ada ${formatNumber(pairs.length)} sambungan ayat dari Juz ${start} sampai Juz ${end}.`
        : "Juz akhir tidak boleh lebih awal daripada juz awal.";
    } else {
      rangeHint.textContent = `${formatNumber(pairs.length)} sambungan ayat tersedia dari seluruh 30 juz; soal akan dipilih secara acak.`;
    }
    countHint.textContent = maximum
      ? `Pilih 1–${maximum} soal. Maksimal 100 soal per tantangan.`
      : "Belum ada sambungan pada rentang ini. Pilih surah atau rentang juz yang lebih luas.";
  };

  const modeDetails = () => {
    const mode = currentMode();
    if (mode === "surah") {
      const surah = quranData.find((item) => item.number === Number(surahSelect.value));
      const juzFilter = surahJuzSelect.value || "all";
      return {
        label: "Surah Challenge",
        range: surah
          ? `Surah ${surah.number} · ${surah.name} (${surah.translation})${juzFilter === "all" ? "" : ` · Juz ${juzFilter}`}`
          : "Surah pilihan",
      };
    }
    if (mode === "juz-range") {
      return {
        label: "Rentang Juz",
        range: `Juz ${Number(juzStart.value)} sampai Juz ${Number(juzEnd.value)}`,
      };
    }
    return { label: "Bil Ghaib · 30 Juz", range: "Acak dari seluruh surah dan juz" };
  };

  const motivationFor = (score) => {
    const pool = score === 100
      ? QURAN_MOTIVATION.excellent
      : score >= 60
        ? QURAN_MOTIVATION.growing
        : QURAN_MOTIVATION.keepGoing;
    return pool[Math.floor(Math.random() * pool.length)];
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

  const renderQuestion = () => {
    const question = quiz.questions[quiz.questionIndex];
    const { pair } = question;
    const progress = ((quiz.questionIndex + 1) / quiz.questions.length) * 100;
    document.querySelector("#quran-quiz-label").textContent = quiz.modeLabel;
    document.querySelector("#quran-quiz-counter").textContent = `Soal ${quiz.questionIndex + 1} dari ${quiz.questions.length}`;
    document.querySelector("#quran-progress-bar").style.width = `${progress}%`;
    document.querySelector("#quran-question-location").textContent = `${pair.surah.name} · Ayat ${pair.anchor.number}`;
    document.querySelector("#quran-prompt").textContent = pair.anchor.arab;
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
    nextButton.textContent = quiz.questionIndex === quiz.questions.length - 1 ? "Selesaikan tantangan" : "Soal berikutnya";
  };

  const showResults = () => {
    const correctCount = quiz.questions.filter((question) => question.selectedAnswer === question.pair.next.arab).length;
    const score = Math.round((correctCount / quiz.questions.length) * 100);
    const details = modeDetails();
    currentMotivation = motivationFor(score);
    document.querySelector("#quran-score-value").textContent = `${score}%`;
    document.querySelector("#quran-score-summary").textContent = `${correctCount} dari ${quiz.questions.length} sambungan tepat`;
    document.querySelector("#quran-result-mode").textContent = `Mode: ${details.label}`;
    document.querySelector("#quran-result-range").textContent = details.range;
    document.querySelector("#quran-motivation-message").textContent = currentMotivation;

    const mistakesList = document.querySelector("#quran-mistakes-list");
    mistakesList.replaceChildren();
    const mistakes = quiz.questions
      .map((question, index) => ({ question, index }))
      .filter(({ question }) => question.selectedAnswer !== question.pair.next.arab);
    if (!mistakes.length) {
      const perfect = document.createElement("p");
      perfect.className = "hafalan-perfect-message";
      perfect.textContent = "MasyaAllah, semua jawaban tepat. Terus jaga hafalan dengan murajaah.";
      mistakesList.append(perfect);
    } else {
      mistakes.forEach(({ question, index }) => {
        const { pair } = question;
        const item = document.createElement("article");
        item.className = "hafalan-mistake-item";
        const heading = document.createElement("h4");
        heading.textContent = `Soal ${index + 1} · ${pair.surah.name}, ayat ${pair.anchor.number}`;
        const prompt = document.createElement("p");
        prompt.className = "hafalan-review-nadzom";
        prompt.dir = "rtl";
        prompt.lang = "ar";
        prompt.textContent = pair.anchor.arab;
        item.append(heading, prompt);
        appendReviewLine(item, "Jawabanmu", question.selectedAnswer, "rtl");
        appendReviewLine(item, "Sambungan ayat yang tepat", pair.next.arab, "rtl");
        mistakesList.append(item);
      });
    }

    document.querySelector("#certificate-kicker").textContent = "Apresiasi atas ikhtiar menjaga Al-Qur’an";
    document.querySelector("#certificate-title").textContent = "Sertifikat Partisipasi";
    document.querySelector("#certificate-subtitle").textContent = "Al-Qur’an · Tantangan Sambung Ayat";
    document.querySelector("#certificate-name").textContent = quiz.participant;
    document.querySelector("#certificate-description").textContent = "Atas semangat dan ketekunannya menyelesaikan tantangan sambung ayat Al-Qur’an:";
    document.querySelector("#certificate-book").textContent = "Sambung Ayat Al-Qur’an";
    document.querySelector("#certificate-range").textContent = `${details.label} · ${details.range}`;
    document.querySelector("#certificate-score").textContent = `${score}% (${correctCount}/${quiz.questions.length})`;
    document.querySelector("#certificate-encouragement").textContent = currentMotivation;
    document.querySelector("#certificate-date").textContent = new Intl.DateTimeFormat("id-ID", {
      day: "numeric", month: "long", year: "numeric",
    }).format(new Date());

    setupForm.hidden = true;
    quizView.hidden = true;
    resultsView.hidden = false;
    guide.hidden = true;
    resultsView.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const startChallenge = async (event) => {
    event.preventDefault();
    status.textContent = "";
    const name = document.querySelector("#quran-participant-name").value.trim();
    if (!name) {
      status.textContent = "Nama lengkap peserta wajib diisi.";
      document.querySelector("#quran-participant-name").focus();
      return;
    }
    if (!quranData) {
      try {
        await loadQuranData();
      } catch (_error) {
        return;
      }
    }
    const mode = currentMode();
    const count = Number(questionCount.value);
    const pairs = pairsForCurrentMode();
    const maximum = Math.min(100, pairs.length);
    if (!pairs.length) {
      status.textContent = mode === "surah"
        ? "Pilih surah yang memiliki cukup sambungan ayat."
        : "Rentang ini belum memiliki sambungan ayat. Pilih rentang yang lebih luas.";
      return;
    }
    if (!Number.isInteger(count) || count < 1 || count > maximum) {
      status.textContent = `Jumlah soal harus antara 1 sampai ${maximum}.`;
      return;
    }
    if (mode === "juz-range" && Number(juzStart.value) > Number(juzEnd.value)) {
      status.textContent = "Juz awal tidak boleh lebih besar daripada juz akhir.";
      return;
    }

    startButton.disabled = true;
    startButton.textContent = "Mengacak ayat…";
    try {
      const details = modeDetails();
      const sourceTexts = [...new Set(pairs.map((pair) => pair.next.arab).filter(Boolean))];
      const distractorPool = sourceTexts.length >= 4 ? sourceTexts : allAnswerTexts;
      const questions = shuffle(pairs).slice(0, count).map((pair) => {
        let distractors = shuffle(distractorPool.filter((text) => text !== pair.next.arab)).slice(0, 3);
        if (distractors.length < 3) {
          const fallback = shuffle(allAnswerTexts.filter((text) => text !== pair.next.arab && !distractors.includes(text)));
          distractors = [...distractors, ...fallback.slice(0, 3 - distractors.length)];
        }
        return {
          pair,
          choices: shuffle([pair.next.arab, ...distractors]),
          selectedAnswer: null,
        };
      });
      quiz = {
        participant: name,
        modeLabel: details.label,
        mode,
        questions,
        questionIndex: 0,
      };
      setupForm.hidden = true;
      guide.hidden = true;
      resultsView.hidden = true;
      quizView.hidden = false;
      reviewPanel.hidden = true;
      reviewButton.setAttribute("aria-expanded", "false");
      reviewButton.textContent = "Lihat Evaluasi & Motivasi";
      renderQuestion();
      quizView.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      status.textContent = error.message || "Tantangan belum dapat disiapkan. Silakan coba lagi.";
    } finally {
      startButton.disabled = false;
      startButton.innerHTML = 'Mulai Tantangan <span aria-hidden="true"><i class="fa-solid fa-arrow-right" aria-hidden="true"></i></span>';
    }
  };

  setupForm.addEventListener("submit", startChallenge);
  setupForm.querySelectorAll('input[name="quran_mode"]').forEach((radio) => {
    radio.addEventListener("change", updateModeControls);
  });
  surahJuzSelect.addEventListener("change", () => {
    refreshSurahChoices();
    updateModeControls();
  });
  [surahSelect, juzStart, juzEnd].forEach((select) => select.addEventListener("change", updateModeControls));
  questionCount.addEventListener("input", () => {
    if (!quranData) return;
    const maximum = Math.min(100, pairsForCurrentMode().length);
    countHint.textContent = maximum
      ? `Pilih 1–${maximum} soal. Maksimal 100 soal per tantangan.`
      : "Pilih surah atau rentang juz yang memiliki sambungan ayat.";
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
    reviewButton.textContent = opening ? "Sembunyikan Evaluasi & Motivasi" : "Lihat Evaluasi & Motivasi";
    if (opening) reviewPanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  });
  document.querySelector('[data-hafalan-choice="quran"]')?.addEventListener("click", () => {
    loadQuranData().catch(() => {});
  });
  panel.addEventListener("hafalan:open", () => {
    if (setupForm.hidden && resultsView.hidden === false) {
      resultsView.hidden = true;
      setupForm.hidden = false;
      guide.hidden = false;
    }
  });
})();
