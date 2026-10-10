// Menu responsif (publik & admin) + pemilih path gambar di form admin.
(function () {
  function bindToggle(btn, target) {
    if (!btn || !target) return;
    btn.addEventListener('click', function () {
      var open = target.classList.toggle('open');
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }
  bindToggle(document.querySelector('.header .nav-toggle'), document.getElementById('menu'));
  bindToggle(document.querySelector('.admin-toggle'), document.getElementById('admin-side'));

  // Pilih gambar yang sudah ada -> isi kolom path di sebelahnya.
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
