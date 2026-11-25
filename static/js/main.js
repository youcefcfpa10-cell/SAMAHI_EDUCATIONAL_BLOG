/* سماحي يوسف – مدونتي التعليمية */
document.addEventListener("DOMContentLoaded", function () {
  "use strict";

  const menuToggle = document.getElementById("menuToggle");
  const mainNav = document.getElementById("mainNav");
  if (menuToggle && mainNav) {
    menuToggle.addEventListener("click", function () {
      const opened = mainNav.classList.toggle("open");
      menuToggle.setAttribute("aria-expanded", String(opened));
    });
    mainNav.querySelectorAll("a").forEach(link => link.addEventListener("click", () => {
      mainNav.classList.remove("open");
      menuToggle.setAttribute("aria-expanded", "false");
    }));
    document.addEventListener("click", event => {
      if (!mainNav.contains(event.target) && !menuToggle.contains(event.target)) {
        mainNav.classList.remove("open");
        menuToggle.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        mainNav.classList.remove("open");
        menuToggle.setAttribute("aria-expanded", "false");
      }
    });
  }

  const themeToggle = document.getElementById("themeToggle");
  const savedTheme = localStorage.getItem("samahi-theme");
  if (savedTheme === "dark") document.documentElement.setAttribute("data-theme", "dark");
  if (themeToggle) {
    themeToggle.setAttribute("aria-pressed", String(document.documentElement.getAttribute("data-theme") === "dark"));
    themeToggle.addEventListener("click", function () {
      const dark = document.documentElement.getAttribute("data-theme") !== "dark";
      if (dark) document.documentElement.setAttribute("data-theme", "dark");
      else document.documentElement.removeAttribute("data-theme");
      localStorage.setItem("samahi-theme", dark ? "dark" : "light");
      themeToggle.setAttribute("aria-pressed", String(dark));
    });
  }

  const backToTop = document.getElementById("backToTop");
  if (backToTop) {
    const update = () => backToTop.classList.toggle("visible", window.scrollY > 350);
    window.addEventListener("scroll", update, { passive: true });
    update();
    backToTop.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  }

  const year = document.getElementById("currentYear");
  if (year) year.textContent = new Date().getFullYear();

  const normalizeArabic = text => String(text || "").toLocaleLowerCase("ar")
    .replace(/[أإآ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه")
    .replace(/ـ/g, "").replace(/[\u064B-\u065F\u0670]/g, "").trim();
  const searchInput = document.getElementById("contentSearch");
  const filterButtons = document.querySelectorAll("[data-filter]");
  const filterItems = document.querySelectorAll("[data-search-item]");
  const noResults = document.getElementById("noSearchResults");
  const resultsCount = document.getElementById("visibleResultsCount");
  let selectedFilter = "all";
  function updateListing() {
    if (!filterItems.length) return;
    const term = normalizeArabic(searchInput ? searchInput.value : "");
    let count = 0;
    filterItems.forEach(item => {
      const matchesText = normalizeArabic(item.textContent).includes(term);
      const category = normalizeArabic(item.dataset.category || "");
      const matchesCategory = selectedFilter === "all" || category === normalizeArabic(selectedFilter);
      const visible = matchesText && matchesCategory;
      item.hidden = !visible;
      if (visible) count++;
    });
    if (resultsCount) resultsCount.textContent = count;
    if (noResults) noResults.hidden = count > 0;
  }
  if (searchInput) searchInput.addEventListener("input", updateListing);
  filterButtons.forEach(button => button.addEventListener("click", function () {
    selectedFilter = button.dataset.filter || "all";
    filterButtons.forEach(item => {
      item.classList.toggle("active", item === button);
      item.setAttribute("aria-pressed", String(item === button));
    });
    updateListing();
  }));
  updateListing();
  document.querySelectorAll('a[target="_blank"]').forEach(link => link.setAttribute("rel", "noopener noreferrer"));
});
