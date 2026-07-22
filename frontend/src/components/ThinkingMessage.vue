<template>
  <article class="message interviewer-message thinking-message" role="status" aria-live="polite">
    <div class="message-avatar" aria-hidden="true">铁</div>
    <div class="message-content">
      <div class="message-meta"><strong>铁面 · 面试官</strong><time>正在处理</time></div>
      <div class="message-bubble">
        <div class="thinking-copy">
          <span class="thinking-dots" aria-hidden="true"><i></i><i></i><i></i></span>
          <span>{{ label }}</span>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup>
defineProps({ label: { type: String, default: "面试官正在思考" } });
</script>
