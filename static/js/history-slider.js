(() => {
  const slider = document.querySelector("[data-history-slider]");
  if (!slider) return;

  const slides = Array.from(slider.querySelectorAll("[data-history-slide]"));
  const currentLabel = slider.querySelector("[data-history-slide-current]");
  const countLabel = slider.querySelector("[data-history-slide-count]");
  if (countLabel) countLabel.textContent = String(slides.length).padStart(2, "0");
  if (slides.length < 2) return;

  const prefersReducedMotion = typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (prefersReducedMotion) return;

  const requestedInterval = Number.parseInt(slider.dataset.historyInterval, 10);
  const interval = Number.isFinite(requestedInterval) && requestedInterval >= 1000
    ? requestedInterval
    : 5000;
  let activeIndex = slides.findIndex((slide) => slide.classList.contains("is-active"));
  if (activeIndex < 0) activeIndex = 0;
  let timer = null;

  const showNextSlide = () => {
    slides[activeIndex].classList.remove("is-active");
    slides[activeIndex].setAttribute("aria-hidden", "true");
    activeIndex = (activeIndex + 1) % slides.length;
    slides[activeIndex].classList.add("is-active");
    slides[activeIndex].setAttribute("aria-hidden", "false");
    if (currentLabel) currentLabel.textContent = String(activeIndex + 1).padStart(2, "0");
  };

  const start = () => {
    if (!timer && !document.hidden) timer = window.setInterval(showNextSlide, interval);
  };
  const stop = () => {
    if (timer) window.clearInterval(timer);
    timer = null;
  };

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else start();
  });
  start();
})();
