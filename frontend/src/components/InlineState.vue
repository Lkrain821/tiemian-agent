<template>
  <div class="inline-state" :class="`inline-state--${tone}`" role="status">
    <span class="inline-state-icon" aria-hidden="true">{{ icon }}</span>
    <div class="inline-state-copy">
      <strong>{{ title }}</strong>
      <span v-if="message">{{ message }}</span>
    </div>
    <button v-if="actionLabel" class="inline-state-action" type="button" @click="$emit('action')">{{ actionLabel }}</button>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  tone: { type: String, default: "info" },
  title: { type: String, required: true },
  message: { type: String, default: "" },
  actionLabel: { type: String, default: "" }
});
defineEmits(["action"]);

const icon = computed(() => ({ error: "!", warning: "!", empty: "○", loading: "·" }[props.tone] || "i"));
</script>
