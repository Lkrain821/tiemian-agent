(() => {
  "use strict";

  const storageKey = "tiemian-color-theme";
  const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

  function getSavedTheme() {
    try {
      const savedTheme = localStorage.getItem(storageKey);
      return savedTheme === "light" || savedTheme === "dark" ? savedTheme : null;
    } catch {
      return null;
    }
  }

  function setSavedTheme(theme) {
    try {
      localStorage.setItem(storageKey, theme);
    } catch {
      // The visual switch still works when storage is unavailable.
    }
  }

  function applyTheme(theme) {
    const isDark = theme === "dark";
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;

    const themeColor = document.querySelector('meta[name="theme-color"]');
    if (themeColor) {
      themeColor.setAttribute("content", isDark ? "#111111" : "#f5f5f5");
    }

    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      const label = button.querySelector(".theme-toggle-label");
      if (label) label.textContent = isDark ? "浅色" : "深色";
      button.setAttribute("aria-label", isDark ? "切换到浅色模式" : "切换到深色模式");
      button.setAttribute("aria-pressed", String(isDark));
    });
  }

  applyTheme(getSavedTheme() || (darkQuery.matches ? "dark" : "light"));

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(document.documentElement.dataset.theme);

    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        setSavedTheme(nextTheme);
        applyTheme(nextTheme);
      });
    });
  });

  darkQuery.addEventListener("change", (event) => {
    if (!getSavedTheme()) {
      applyTheme(event.matches ? "dark" : "light");
    }
  });
})();
