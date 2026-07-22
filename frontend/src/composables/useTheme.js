import { computed, onBeforeUnmount, onMounted, ref } from "vue";

const STORAGE_KEY = "tiemian-color-theme";
const currentTheme = ref(document.documentElement.dataset.theme || "light");

function applyTheme(theme) {
  currentTheme.value = theme;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute(
    "content",
    theme === "dark" ? "#111111" : "#f5f5f5"
  );
}

export function useTheme() {
  let mediaQuery;
  const onSystemChange = (event) => {
    if (!localStorage.getItem(STORAGE_KEY)) applyTheme(event.matches ? "dark" : "light");
  };

  onMounted(() => {
    applyTheme(document.documentElement.dataset.theme || "light");
    mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    mediaQuery.addEventListener("change", onSystemChange);
  });
  onBeforeUnmount(() => mediaQuery?.removeEventListener("change", onSystemChange));

  function toggle() {
    const next = currentTheme.value === "dark" ? "light" : "dark";
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
  }

  return {
    theme: computed(() => currentTheme.value),
    isDark: computed(() => currentTheme.value === "dark"),
    toggle
  };
}
