// tracker_set_detail.js: JavaScript for set_detail.html

document.addEventListener("DOMContentLoaded", function () {
  const rows = document.querySelectorAll(".clickable-row");
  const filterInput = document.getElementById("table-filter");
  const table = document.querySelector("table");
  const headers = table.querySelectorAll("th.sortable");
  let sortDirection = {};

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
    });
  });

  // Filter table rows based on input
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
  });

  rows.forEach((row) => {
    row.addEventListener("click", function () {
      const cardId = row.dataset.cardId;
      const action = row.dataset.action;
      if (action === "uncollect") {
        if (!confirm(window.uncollectConfirmText || "Are you sure you want to uncollect this card?")) {
          return;
        }
      }
      fetch("", {
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
      })
        .then((response) => response.json())
        .then((data) => {
          const statusCell = row.querySelector(".status-cell");
          if (data.collected) {
            statusCell.textContent = "✅";
            row.dataset.action = "uncollect";
          } else {
            statusCell.textContent = "❌";
            row.dataset.action = "collect";
          }
          // Live update rarity progress
          fetch(window.location.pathname + "?fragment=rarity_progress")
            .then(r => r.text())
            .then(html => {
              const parser = new DOMParser();
              const doc = parser.parseFromString(html, "text/html");
              const newProgress = doc.getElementById("rarity-progress");
              if (newProgress) {
                document.getElementById("rarity-progress").innerHTML = newProgress.innerHTML;
              }
            });
        });
    });
  });

  document.getElementById("collect-base-btn").addEventListener("click", function () {
    if (!confirm(window.collectBaseConfirmText || "Are you sure you want to collect all base cards?")) {
      return;
    }
    const rarities = ["common", "uncommon", "rare", "double_rare"];
    const csrfToken = window.csrfToken;
    rows.forEach((row) => {
      const rarity = row.dataset.rarity;
      if (rarities.includes(rarity) && row.dataset.action === "collect") {
        const cardId = row.dataset.cardId;
        fetch("", {
          method: "POST",
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": csrfToken,
            "X-Requested-With": "XMLHttpRequest",
          },
          body: new URLSearchParams({
            card_id: cardId,
            action: "collect",
          }),
        })
          .then((response) => response.json())
          .then((data) => {
            const statusCell = row.querySelector(".status-cell");
            if (data.collected) {
              statusCell.textContent = "✅";
              row.dataset.action = "uncollect";
            }
          });
      }
    });
  });

  document.getElementById("jump-to-illustration-rare-btn").addEventListener("click", function () {
    const illustrationRareRow = Array.from(rows).find((row) => row.dataset.rarity === "illustration_rare");
    if (illustrationRareRow) {
      illustrationRareRow.scrollIntoView({ behavior: "smooth", block: "center" });
      illustrationRareRow.classList.add("highlight");
      setTimeout(() => illustrationRareRow.classList.remove("highlight"), 2000);
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
