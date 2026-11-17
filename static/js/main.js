"use strict";

document.querySelectorAll(".quantity-form").forEach((form) => {
  const quantityInput = form.querySelector('input[name="quantity"]');
  if (!quantityInput) return;

  form.querySelectorAll("[data-quantity-change]").forEach((button) => {
    button.addEventListener("click", () => {
      const current = Number.parseInt(quantityInput.value, 10);
      const minimum = Number.parseInt(quantityInput.min, 10);
      const maximum = Number.parseInt(quantityInput.max, 10);
      const change = Number.parseInt(button.dataset.quantityChange, 10);
      if (!Number.isInteger(current) || !Number.isInteger(change)) return;

      quantityInput.value = String(Math.min(maximum, Math.max(minimum, current + change)));
      form.requestSubmit();
    });
  });
});

function setupAdminFilters({
  searchSelector,
  categorySelector,
  rowSelector,
  emptySelector,
  searchText,
}) {
  const searchInput = document.querySelector(searchSelector);
  const categoryFilter = categorySelector
    ? document.querySelector(categorySelector)
    : null;
  const rows = Array.from(document.querySelectorAll(rowSelector));
  const emptyRow = document.querySelector(emptySelector);
  if (!searchInput && !categoryFilter) return;

  function filterRows() {
    const searchTerm = searchInput ? searchInput.value.trim().toLowerCase() : "";
    const category = categoryFilter ? categoryFilter.value : "";
    let visibleCount = 0;

    rows.forEach((row) => {
      const searchableText = searchText
        ? searchText(row)
        : row.textContent.toLowerCase();
      const matchesSearch = searchableText.includes(searchTerm);
      const matchesCategory =
        !category || row.dataset.productCategory === category;
      const isVisible = matchesSearch && matchesCategory;
      row.hidden = !isVisible;
      if (isVisible) visibleCount += 1;
    });

    if (emptyRow) emptyRow.hidden = visibleCount > 0;
  }

  if (searchInput) searchInput.addEventListener("input", filterRows);
  if (categoryFilter) categoryFilter.addEventListener("change", filterRows);
}

setupAdminFilters({
  searchSelector: "#adminProductSearch",
  categorySelector: "#adminCategoryFilter",
  rowSelector: "[data-admin-product]",
  emptySelector: "[data-admin-product-empty]",
  searchText: (row) => row.dataset.productName || "",
});
setupAdminFilters({
  searchSelector: "#adminStockSearch",
  categorySelector: "#adminStockCategoryFilter",
  rowSelector: "[data-admin-stock]",
  emptySelector: "[data-admin-stock-empty]",
  searchText: (row) => row.dataset.productName || "",
});
setupAdminFilters({
  searchSelector: "#adminOrderSearch",
  rowSelector: "[data-admin-order]",
  emptySelector: "[data-admin-order-empty]",
});

document.querySelectorAll("[data-confirm-delete]").forEach((button) => {
  button.addEventListener("click", (event) => {
    if (!window.confirm("Remove this product from the active menu?")) {
      event.preventDefault();
    }
  });
});

const orderStatusContainer = document.querySelector("[data-order-status-poll]");

if (orderStatusContainer) {
  const stageNames = [
    "Order Accepted",
    "Preparing",
    "Ready for Pickup",
    "Out for Delivery",
    "Delivered",
  ];
  const refreshMessage = orderStatusContainer.querySelector("[data-order-refresh-message]");

  function applyOrderStatus(orderId, status) {
    const statusClass = `status-${status.toLowerCase().replace(/ /g, "-")}`;
    document.querySelectorAll("[data-order-status]").forEach((badge) => {
      if (badge.dataset.orderId !== String(orderId)) return;
      badge.textContent = status;
      badge.className = "order-status";
      badge.classList.add(statusClass);
    });

    document.querySelectorAll("[data-order-progress]").forEach((progress) => {
      if (progress.dataset.orderId !== String(orderId)) return;
      const currentIndex = stageNames.indexOf(status);
      progress.setAttribute("aria-label", `Order progress: ${status}`);
      progress.querySelectorAll("[data-stage-index]").forEach((stage) => {
        const index = Number.parseInt(stage.dataset.stageIndex, 10);
        stage.classList.toggle("is-done", index < currentIndex);
        stage.classList.toggle("is-current", index === currentIndex);
        stage.classList.toggle("is-upcoming", index > currentIndex);
        stage.querySelector("span").textContent = index < currentIndex ? "✓" : String(index + 1);
      });
    });

    document.querySelectorAll("[data-order-card], [data-order-id]").forEach((card) => {
      if (card.dataset.orderId !== String(orderId)) return;
      const progressWrap = card.querySelector("[data-order-progress-wrap]");
      const progress = card.querySelector("[data-order-progress]");
      const cancelledMessage = card.querySelector("[data-order-cancelled]");
      const orderTitle = card.querySelector("[data-order-title]");
      if (progressWrap) progressWrap.hidden = status === "Cancelled";
      else if (progress) progress.hidden = status === "Cancelled";
      if (cancelledMessage) cancelledMessage.hidden = status !== "Cancelled";
      if (orderTitle && status === "Cancelled") orderTitle.textContent = "This order was cancelled";
      if (orderTitle && status !== "Cancelled") orderTitle.textContent = "On its way to a good day";
    });

    const currentStatus = document.querySelector("[data-current-order-status]");
    if (currentStatus && currentStatus.closest("[data-order-status-poll]")) {
      const detailBadge = currentStatus.parentElement.parentElement.querySelector(
        `[data-order-status][data-order-id="${orderId}"]`
      );
      if (detailBadge) currentStatus.textContent = status;
    }
  }

  async function refreshOrderStatuses() {
    if (document.visibilityState === "hidden") return;
    try {
      const response = await fetch(orderStatusContainer.dataset.statusUrl, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`Status refresh failed (${response.status}).`);
      const payload = await response.json();
      payload.statuses.forEach(({ id, status }) => applyOrderStatus(id, status));
      if (refreshMessage) refreshMessage.textContent = "";
    } catch (error) {
      if (refreshMessage) {
        refreshMessage.textContent = "Order status could not be refreshed. Retrying shortly.";
      }
    }
  }

  window.setInterval(refreshOrderStatuses, 20000);
  document.addEventListener("visibilitychange", refreshOrderStatuses);
}

const menuToggle = document.querySelector(".nav-toggle");
const mainNav = document.querySelector(".main-nav");

if (menuToggle && mainNav) {
  function closeMainNav() {
    menuToggle.setAttribute("aria-expanded", "false");
    menuToggle.setAttribute("aria-label", "Open navigation");
    mainNav.classList.remove("is-open");
  }

  menuToggle.addEventListener("click", () => {
    const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
    menuToggle.setAttribute("aria-expanded", String(!isOpen));
    menuToggle.setAttribute("aria-label", isOpen ? "Open navigation" : "Close navigation");
    mainNav.classList.toggle("is-open", !isOpen);
  });

  mainNav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMainNav);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menuToggle.getAttribute("aria-expanded") === "true") {
      closeMainNav();
      menuToggle.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".nav-wrap")) closeMainNav();
  });
}

const searchInput = document.querySelector("#foodSearch");
const foodCards = Array.from(document.querySelectorAll("[data-food-card]"));
const categoryButtons = Array.from(document.querySelectorAll("[data-category-filter]"));
const emptySearch = document.querySelector("#emptySearch");
let activeCategory = "all";

function filterFoods() {
  const searchTerm = searchInput ? searchInput.value.trim().toLowerCase() : "";
  let visibleCount = 0;

  foodCards.forEach((card) => {
    const matchesCategory = activeCategory === "all" || card.dataset.category === activeCategory;
    const matchesSearch = (card.dataset.foodName || "").includes(searchTerm);
    const isVisible = matchesCategory && matchesSearch;

    card.hidden = !isVisible;
    if (isVisible) visibleCount += 1;
  });

  if (emptySearch) emptySearch.hidden = visibleCount > 0;
}

if (searchInput) searchInput.addEventListener("input", filterFoods);

categoryButtons.forEach((button) => {
  button.addEventListener("click", () => {
    activeCategory = button.dataset.categoryFilter;
    categoryButtons.forEach((categoryButton) => {
      const selected = categoryButton === button;
      categoryButton.classList.toggle("is-active", selected);
      categoryButton.setAttribute("aria-pressed", String(selected));
    });
    filterFoods();

    const foodSection = document.querySelector("#popular");
    if (foodSection && window.matchMedia("(max-width: 680px)").matches) {
      foodSection.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
});

const dashboardSearch = document.querySelector("#dashboardFoodSearch");
const dashboardFoodCards = Array.from(document.querySelectorAll("[data-dashboard-food]"));
const dashboardCategoryButtons = Array.from(
  document.querySelectorAll("[data-dashboard-category]")
);
const noDashboardFoods = document.querySelector("#dashboardNoFoods");
let dashboardCategory = "all";

function filterDashboardFoods() {
  const searchTerm = dashboardSearch ? dashboardSearch.value.trim().toLowerCase() : "";
  let visibleCount = 0;

  dashboardFoodCards.forEach((card) => {
    const matchesCategory =
      dashboardCategory === "all" || card.dataset.category === dashboardCategory;
    const matchesSearch = card.textContent.toLowerCase().includes(searchTerm);
    const isVisible = matchesCategory && matchesSearch;

    card.hidden = !isVisible;
    if (isVisible) visibleCount += 1;
  });

  if (noDashboardFoods) noDashboardFoods.hidden = visibleCount > 0;
}

if (dashboardSearch) dashboardSearch.addEventListener("input", filterDashboardFoods);

dashboardCategoryButtons.forEach((button) => {
  button.addEventListener("click", () => {
    dashboardCategory = button.dataset.dashboardCategory;
    dashboardCategoryButtons.forEach((categoryButton) => {
      const selected = categoryButton === button;
      categoryButton.classList.toggle("is-active", selected);
      categoryButton.setAttribute("aria-pressed", String(selected));
    });
    filterDashboardFoods();
  });
});

const dashboardLinks = Array.from(document.querySelectorAll(".dashboard-nav-link"));

function activateDashboardLink() {
  const activeHash = window.location.hash || "#dashboard-home";
  dashboardLinks.forEach((link) => {
    const target = link.getAttribute("href");
    const isTrackingOrder = activeHash.startsWith("#track-order-") && target === "#track-orders";
    link.classList.toggle("is-current", target === activeHash || isTrackingOrder);
  });
}

dashboardLinks.forEach((link) => {
  link.addEventListener("click", () => {
    dashboardLinks.forEach((dashboardLink) => dashboardLink.classList.remove("is-current"));
    link.classList.add("is-current");
  });
});

if (dashboardLinks.length) {
  window.addEventListener("hashchange", activateDashboardLink);
  activateDashboardLink();
}
