// tracker_set_detail.js: JavaScript for set_detail.html

document.addEventListener("DOMContentLoaded", function () {
  const rows = document.querySelectorAll(".clickable-row");
  const tiles = document.querySelectorAll(".card-tile");
  const tilesById = new Map(Array.from(tiles, (tile) => [tile.dataset.cardId, tile]));
  const rowsById = new Map(Array.from(rows, (row) => [row.dataset.cardId, row]));
  const gridView = document.getElementById("grid-view");
  const tableView = document.getElementById("table-view");
  const filterInput = document.getElementById("table-filter");
  const table = document.querySelector("table");
  const headers = table.querySelectorAll("th.sortable");
  let sortDirection = {};

  // Keep the grid in the same order as the (sorted) table
  function syncGridOrder() {
    if (!gridView) return;
    table.querySelectorAll("tbody tr").forEach((row) => {
      const tile = tilesById.get(row.dataset.cardId);
      if (tile) gridView.appendChild(tile);
    });
  }

  // Initial sort by card number (ascending)
  (function initialSortByNumber() {
    const tbody = table.querySelector("tbody");
    const rowArr = Array.from(tbody.querySelectorAll("tr"));
    rowArr.sort((a, b) => {
      const aVal = parseInt(a.children[0].textContent.trim()) || 0;
      const bVal = parseInt(b.children[0].textContent.trim()) || 0;
      return aVal - bVal;
    });
    rowArr.forEach((row) => tbody.appendChild(row));
    syncGridOrder();
    // Set arrow for number column
    const numberHeader = Array.from(headers).find((h) => h.dataset.sort === "number");
    if (numberHeader) {
      const arrowSpan = numberHeader.querySelector(".sort-arrow");
      if (arrowSpan) arrowSpan.textContent = "▲";
      sortDirection["number"] = "asc";
    }
  })();

  headers.forEach((header, idx) => {
    header.addEventListener("click", function () {
      const sortKey = header.dataset.sort;
      const tbody = table.querySelector("tbody");
      const rows = Array.from(tbody.querySelectorAll("tr"));
      const dir = sortDirection[sortKey] === "asc" ? "desc" : "asc";
      sortDirection[sortKey] = dir;

      // Remove all arrows
      document.querySelectorAll(".sort-arrow").forEach((span) => {
        span.textContent = "";
      });

      // Set arrow for current header
      const arrowSpan = header.querySelector(".sort-arrow");
      arrowSpan.textContent = dir === "asc" ? "▲" : "▼";

      rows.sort((a, b) => {
        let aVal, bVal;
        if (sortKey === "number") {
          aVal = parseInt(a.children[0].textContent.trim()) || 0;
          bVal = parseInt(b.children[0].textContent.trim()) || 0;
        } else if (sortKey === "name") {
          aVal = a.children[1].textContent.trim().toLowerCase();
          bVal = b.children[1].textContent.trim().toLowerCase();
        } else if (sortKey === "rarity") {
          aVal = rarityOrderMap[a.dataset.rarity] || 99;
          bVal = rarityOrderMap[b.dataset.rarity] || 99;
        } else if (sortKey === "status") {
          aVal = a.querySelector(".status-cell").textContent.trim();
          bVal = b.querySelector(".status-cell").textContent.trim();
        }
        if (aVal < bVal) return dir === "asc" ? -1 : 1;
        if (aVal > bVal) return dir === "asc" ? 1 : -1;
        return 0;
      });

      rows.forEach((row) => tbody.appendChild(row));
      syncGridOrder();
    });
  });

  // Filter table rows and grid tiles based on input
  filterInput.addEventListener("input", function () {
    const filterValue = filterInput.value.toLowerCase();
    rows.forEach((row) => {
      const cells = Array.from(row.querySelectorAll("td"));
      const rowText = cells.map((cell) => cell.textContent.toLowerCase()).join(" ");
      if (rowText.includes(filterValue)) {
        row.style.display = "";
      } else {
        row.style.display = "none";
      }
    });
    tiles.forEach((tile) => {
      tile.hidden = !tile.dataset.search.includes(filterValue);
    });
  });

  function setStatusCell(statusCell, collected) {
    const emoji = collected ? "✅" : "❌";
    const label = collected ? window.collectedLabel || "Collected" : window.notCollectedLabel || "Not collected";
    statusCell.innerHTML = "";
    const span = document.createElement("span");
    span.setAttribute("role", "img");
    span.setAttribute("aria-label", label);
    span.textContent = emoji;
    statusCell.appendChild(span);
  }

  // Reflect a card's collected state in both its table row and grid tile
  function setCollected(cardId, collected) {
    const action = collected ? "uncollect" : "collect";
    const row = rowsById.get(cardId);
    if (row) {
      setStatusCell(row.querySelector(".status-cell"), collected);
      row.dataset.action = action;
    }
    const tile = tilesById.get(cardId);
    if (tile) {
      tile.dataset.action = action;
      tile.setAttribute("aria-pressed", collected ? "true" : "false");
    }
  }

  function postCardAction(cardId, action) {
    return fetch("", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-CSRFToken": window.csrfToken,
        "X-Requested-With": "XMLHttpRequest",
      },
      body: new URLSearchParams({
        card_id: cardId,
        action: action,
      }),
    }).then((response) => response.json());
  }

  function refreshRarityProgress() {
    fetch(window.location.pathname + "?fragment=rarity_progress")
      .then((r) => r.text())
      .then((html) => {
        const parser = new DOMParser();
        const doc = parser.parseFromString(html, "text/html");
        const newProgress = doc.getElementById("rarity-progress");
        if (newProgress) {
          document.getElementById("rarity-progress").innerHTML = newProgress.innerHTML;
        }
      });
  }

  function toggleCard(el) {
    const cardId = el.dataset.cardId;
    const action = el.dataset.action;
    if (action === "uncollect") {
      if (!confirm(window.uncollectConfirmText || "Are you sure you want to uncollect this card?")) {
        return;
      }
    }
    postCardAction(cardId, action).then((data) => {
      setCollected(cardId, data.collected);
      refreshRarityProgress();
    });
  }

  rows.forEach((row) => row.addEventListener("click", () => toggleCard(row)));
  tiles.forEach((tile) => tile.addEventListener("click", () => toggleCard(tile)));

  document.getElementById("collect-base-btn").addEventListener("click", function () {
    if (!confirm(window.collectBaseConfirmText || "Are you sure you want to collect all base cards?")) {
      return;
    }
    const rarities = ["common", "uncommon", "rare", "double_rare"];
    const requests = [];
    rows.forEach((row) => {
      const rarity = row.dataset.rarity;
      if (rarities.includes(rarity) && row.dataset.action === "collect") {
        const cardId = row.dataset.cardId;
        requests.push(
          postCardAction(cardId, "collect").then((data) => {
            if (data.collected) {
              setCollected(cardId, true);
            }
          })
        );
      }
    });
    Promise.all(requests).then(refreshRarityProgress);
  });

  // Table / grid view toggle, remembered per browser
  const VIEW_KEY = "tcgp.setDetailView";
  const gridColsGroup = document.getElementById("grid-cols-group");
  function showView(mode) {
    if (!gridView) return;
    const grid = mode === "grid";
    gridView.hidden = !grid;
    tableView.hidden = grid;
    if (gridColsGroup) gridColsGroup.hidden = !grid;
    const radio = document.getElementById(grid ? "view-grid" : "view-table");
    if (radio) radio.checked = true;
  }
  document.querySelectorAll('input[name="view-mode"]').forEach((radio) => {
    radio.addEventListener("change", function () {
      showView(radio.value);
      try {
        localStorage.setItem(VIEW_KEY, radio.value);
      } catch (e) {
        // Storage unavailable (private mode etc.); the toggle still works.
      }
    });
  });
  try {
    showView(localStorage.getItem(VIEW_KEY) || "table");
  } catch (e) {
    showView("table");
  }

  // Grid column count toggle (3 / 5 / full width), remembered per browser
  const GRID_COLS_KEY = "tcgp.setDetailGridCols";
  function setGridCols(cols) {
    if (!gridView) return;
    const radio = document.getElementById("grid-cols-" + cols);
    if (!radio) return;
    radio.checked = true;
    if (cols === "full") {
      delete gridView.dataset.cols;
    } else {
      gridView.dataset.cols = cols;
    }
  }
  document.querySelectorAll('input[name="grid-cols"]').forEach((radio) => {
    radio.addEventListener("change", function () {
      setGridCols(radio.value);
      try {
        localStorage.setItem(GRID_COLS_KEY, radio.value);
      } catch (e) {
        // Storage unavailable (private mode etc.); the toggle still works.
      }
    });
  });
  try {
    setGridCols(localStorage.getItem(GRID_COLS_KEY) || "full");
  } catch (e) {
    setGridCols("full");
  }

  document.getElementById("jump-to-illustration-rare-btn").addEventListener("click", function () {
    const items = gridView && !gridView.hidden ? tiles : rows;
    const target = Array.from(items).find((el) => el.dataset.rarity === "illustration_rare");
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.add("highlight");
      setTimeout(() => target.classList.remove("highlight"), 2000);
    }
  });

  // Floating button show/hide logic
  const floatingBtns = document.getElementById("floating-btns");
  const scrollToTopBtn = document.getElementById("scroll-to-top-btn");
  const floatingBackBtn = document.getElementById("floating-back-btn");

  function updateFloatingBtns() {
    if (window.scrollY > 200) {
      floatingBtns.style.display = "flex";
      if (scrollToTopBtn) scrollToTopBtn.style.display = "inline-block";
      if (floatingBackBtn) floatingBackBtn.style.display = "inline-block";
    } else {
      floatingBtns.style.display = "none";
      if (scrollToTopBtn) scrollToTopBtn.style.display = "none";
      if (floatingBackBtn) floatingBackBtn.style.display = "none";
    }
  }
  window.addEventListener("scroll", updateFloatingBtns);
  updateFloatingBtns(); // Initial state

  // Fix: Scroll to top button click handler
  if (scrollToTopBtn) {
    scrollToTopBtn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }
});
