<template>
  <button
    class="theme-toggle"
    type="button"
    :aria-label="isDark ? '切换到浅色模式' : '切换到深色模式'"
    :aria-pressed="String(isDark)"
    @click="toggle"
  >
    <span class="theme-toggle-icon" aria-hidden="true"></span>
    <span class="theme-toggle-label">{{ isDark ? "浅色" : "深色" }}</span>
  </button>
</template>

<script setup>
import { useTheme } from "../composables/useTheme.js";

const { isDark, toggle } = useTheme();
</script>
