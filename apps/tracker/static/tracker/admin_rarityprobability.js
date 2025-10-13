(function() {
  function updateVisibility() {
    const versionSelect = document.getElementById('id_version');
    if (!versionSelect) return;
    const slotCountAttr = versionSelect.selectedOptions[0]?.getAttribute('data-slot-count');
    const slotCount = parseInt(slotCountAttr || '5', 10);
    for (let i = 1; i <= 5; i++) {
      const row = document.querySelector('.form-row.field-probability_slot' + i);
      if (row) {
        if (i <= slotCount) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      }
    }
  }
  document.addEventListener('DOMContentLoaded', function() {
    const versionSelect = document.getElementById('id_version');
    if (versionSelect) {
      versionSelect.addEventListener('change', updateVisibility);
      updateVisibility();
    }
  });
})();
