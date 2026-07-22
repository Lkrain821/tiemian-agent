<template>
  <article
    class="message"
    :class="[
      message.role === 'candidate' ? 'candidate-message' : 'interviewer-message',
      message.kind === 'followup' ? 'follow-up-message' : '',
      { 'streaming-message': streaming }
    ]"
  >
    <div class="message-avatar" aria-hidden="true">{{ message.role === "candidate" ? "我" : "铁" }}</div>
    <div class="message-content">
      <div class="message-meta">
        <strong>{{ message.role === "candidate" ? "我的回答" : "铁面 · 面试官" }}</strong>
        <time>{{ formatTime(message.created_at) }}</time>
      </div>
      <div class="message-bubble">
        <span v-if="message.kind === 'followup'" class="follow-up-label">
          追问 {{ message.followup_level }} / 2
        </span>
        <p>{{ message.content }}<i v-if="streaming" class="typing-caret" aria-hidden="true"></i></p>
      </div>
      <span v-if="message.kind === 'main_question'" class="message-tag">
        主问题<span v-if="topicLabel"> · {{ topicLabel }}</span>
      </span>
    </div>
  </article>
</template>

<script setup>
defineProps({
  message: { type: Object, required: true },
  topicLabel: { type: String, default: "" },
  streaming: { type: Boolean, default: false }
});

function formatTime(value) {
  if (!value) return "刚刚";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(date);
}
</script>
