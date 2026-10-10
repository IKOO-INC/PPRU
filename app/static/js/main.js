// PPRU — perilaku situs publik (navbar, menu mobile, counter, carousel) + helper admin.
(function () {
  // ----- Navbar: kaca transparan -> putih saat di-scroll (sama dengan referensi) -----
  var nav = document.getElementById('navbar');
  function onScroll() {
    if (!nav) return;
    var scrolled = window.scrollY > 50;
    nav.classList.toggle('scrolled-header', scrolled);
    nav.classList.toggle('glass-header', !scrolled);
    nav.classList.toggle('text-slate-800', scrolled);
    nav.classList.toggle('text-white', !scrolled);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // ----- Menu mobile -----
  var toggle = document.getElementById('menuToggle');
  var mobile = document.getElementById('mobileMenu');
  if (toggle && mobile) {
    toggle.addEventListener('click', function () {
      var open = mobile.classList.toggle('is-hidden') === false;
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    mobile.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        mobile.classList.add('is-hidden');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  // ----- Animasi scroll (AOS) -----
  // Jika script AOS dari CDN gagal dimuat, konten jangan tertinggal transparan.
  if (window.AOS) {
    AOS.init({ duration: 800, once: true, offset: 100, easing: 'ease-out-cubic' });
  } else {
    document.querySelectorAll('[data-aos]').forEach(function (el) {
      el.classList.add('aos-animate');
    });
  }

  // ----- Counter statistik -----
  var counters = document.querySelectorAll('.counter');
  if (counters.length && 'IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries, obs) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var el = entry.target;
        var target = parseInt(el.getAttribute('data-target'), 10) || 0;
        var steps = 60, i = 0;
        var timer = setInterval(function () {
          i++;
          el.textContent = Math.round((target / steps) * i);
          if (i >= steps) { el.textContent = target; clearInterval(timer); }
        }, 20);
        obs.unobserve(el);
      });
    }, { threshold: 0.5 });
    counters.forEach(function (c) { io.observe(c); });
  }

  // ----- Carousel berita (Swiper) -----
  if (window.Swiper && document.querySelector('.mySwiper')) {
    var slides = document.querySelectorAll('.mySwiper .swiper-slide').length;
    new Swiper('.mySwiper', {
      slidesPerView: 1,
      spaceBetween: 30,
      loop: slides >= 3,
      autoplay: { delay: 3500, disableOnInteraction: false },
      pagination: { el: '.mySwiper .swiper-pagination', clickable: true },
      breakpoints: {
        640: { slidesPerView: 1 },
        768: { slidesPerView: 2 },
        1024: { slidesPerView: 3 },
      },
    });
  }

  // ----- Admin: sidebar mobile -----
  var adminToggle = document.querySelector('.admin-toggle');
  var adminSide = document.getElementById('admin-side');
  if (adminToggle && adminSide) {
    adminToggle.addEventListener('click', function () {
      var open = adminSide.classList.toggle('open');
      adminToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // ----- Admin: pilih path gambar yang sudah ada -----
  var picker = document.getElementById('pilih-gambar');
  if (picker) {
    picker.addEventListener('change', function () {
      var input = document.getElementById('gambar');
      if (picker.value && input) input.value = picker.value;
    });
  }
  document.querySelectorAll('select.pick-image').forEach(function (sel) {
    sel.addEventListener('change', function () {
      var input = document.querySelector('[name="' + sel.dataset.target + '"]');
      if (sel.value && input) input.value = sel.value;
    });
  });
})();
