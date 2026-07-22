<template>
  <div class="page-root interview-page-root">
    <div class="ambient-grid" aria-hidden="true"></div>

    <header class="site-header compact-header">
      <Brand />
      <div class="session-title">
        <span class="live-dot" aria-hidden="true"></span>
        <div>
          <strong>{{ sessionHeading }}</strong>
          <small>{{ interview?.status_label || "正在载入面试" }}</small>
        </div>
      </div>
      <div class="header-actions">
        <ThemeToggle />
        <button
          class="quiet-button"
          type="button"
          :disabled="!interview?.available_actions?.finish || operationActive"
          @click="openFinishDialog"
        >提前结束</button>
      </div>
    </header>

    <main v-if="initialLoading" class="interview-shell interview-loading-shell">
      <section class="chat-card"><div class="page-loader"><i></i><strong>正在恢复面试现场</strong><span>读取会话、消息和进度…</span></div></section>
      <aside class="progress-panel"><div class="panel-skeleton"><span></span><span></span><span></span><span></span></div></aside>
    </main>

    <main v-else-if="fatalError" class="standalone-state">
      <InlineState
        tone="error"
        title="无法进入这场面试"
        :message="fatalError.message"
        action-label="返回开始页"
        @action="router.push('/')"
      />
    </main>

    <main v-else class="interview-shell">
      <section class="chat-card" aria-labelledby="chat-title">
        <div class="chat-header">
          <div><span class="section-eyebrow">LIVE INTERVIEW</span><h1 id="chat-title">技术面试</h1></div>
          <div class="question-badge">
            <span>当前问题</span>
            <strong>{{ pad(progress.current_question_number) }} <small>/ {{ pad(progress.total_question_count) }}</small></strong>
          </div>
        </div>

        <div ref="chatStream" class="chat-scroll" aria-live="polite">
          <div v-if="interview.current_question" class="timeline-marker">
            <span>问题 {{ pad(progress.current_question_number) }}</span><i></i>
            <small>{{ progress.current_topic_label || "AI Agent 开发" }}</small>
          </div>

          <InlineState
            v-if="streamError"
            tone="error"
            title="本次响应没有正常完成"
            :message="streamError.message"
            :action-label="interview.available_actions?.retry ? '重试当前步骤' : '刷新面试状态'"
            @action="interview.available_actions?.retry ? retryFailedStep() : loadSnapshot()"
          />

          <InlineState
            v-if="!displayMessages.length && !thinking"
            tone="empty"
            title="面试问题正在准备"
            message="第一道问题生成后会显示在这里。"
          />

          <InterviewMessage
            v-for="message in displayMessages"
            :key="message.id"
            :message="message"
            :topic-label="topicForMessage(message)"
            :streaming="message.id === streamMessage?.id"
          />
          <ThinkingMessage v-if="thinking" :label="thinkingLabel" />
        </div>

        <form class="answer-composer" @submit.prevent="submitAnswer">
          <label class="sr-only" for="answerInput">输入你的回答</label>
          <textarea
            id="answerInput"
            ref="answerInput"
            v-model="answerText"
            rows="4"
            :maxlength="pendingAnswer?.max_length || 1200"
            :placeholder="composerPlaceholder"
            :disabled="!canType"
            @keydown.ctrl.enter.prevent="submitAnswer"
          ></textarea>
          <div class="composer-footer">
            <span class="answer-hint"><kbd>Ctrl</kbd> + <kbd>Enter</kbd> 发送</span>
            <div class="composer-actions">
              <span class="char-count"><b>{{ answerText.length }}</b> / {{ pendingAnswer?.max_length || 1200 }}</span>
              <button class="send-button" type="submit" :disabled="!canSubmit">
                {{ operationActive ? "等待响应…" : "提交回答" }}
                <span aria-hidden="true">{{ operationActive ? "·" : "↑" }}</span>
              </button>
            </div>
          </div>
        </form>
      </section>

      <aside class="progress-panel" aria-labelledby="progress-title">
        <div class="progress-topline">
          <div><span class="section-eyebrow">SESSION STATUS</span><h2 id="progress-title">面试进度</h2></div>
          <span class="autosave-label"><i></i> {{ operationActive ? "同步中" : "已记录" }}</span>
        </div>

        <div class="progress-overview">
          <div class="progress-ring" :style="progressRingStyle" :aria-label="`面试完成 ${progress.completion_percent}%`">
            <div><strong>{{ Math.round(progress.completion_percent) }}</strong><span>%</span></div>
          </div>
          <div class="progress-copy">
            <span>已完成</span>
            <strong>{{ progress.completed_question_count }} / {{ progress.total_question_count }} <small>道主问题</small></strong>
            <p>当前：{{ progress.current_topic_label || "等待开始" }}</p>
          </div>
        </div>

        <div class="session-metrics">
          <div class="metric-card"><span>已用时长</span><strong>{{ formattedElapsed }}</strong></div>
          <div class="metric-card"><span>当前追问</span><strong><b>{{ progress.current_followup_count }}</b> <small>/ {{ progress.max_followups_per_question }}</small></strong></div>
        </div>

        <section class="follow-up-depth" aria-labelledby="depth-title">
          <div class="panel-subheading"><h3 id="depth-title">追问层级</h3><span>DEEP DIVE</span></div>
          <div class="depth-track">
            <div class="depth-step" :class="depthClass(0)"><i>{{ depthIcon(0) }}</i><span>主回答</span></div>
            <div class="depth-line" :class="{ active: progress.current_followup_count >= 1 }"></div>
            <div class="depth-step" :class="depthClass(1)"><i>{{ depthIcon(1) }}</i><span>追问一</span></div>
            <div class="depth-line" :class="{ active: progress.current_followup_count >= 2 }"></div>
            <div class="depth-step" :class="depthClass(2)"><i>{{ depthIcon(2) }}</i><span>追问二</span></div>
          </div>
        </section>

        <section class="question-outline" aria-labelledby="outline-title">
          <div class="panel-subheading"><h3 id="outline-title">问题进度</h3><span>QUESTION MAP</span></div>
          <ol>
            <li
              v-for="question in interview.question_map"
              :key="question.number"
              :class="{ done: question.status === 'completed', active: question.status === 'in_progress' }"
              :aria-current="question.status === 'in_progress' ? 'step' : undefined"
            >
              <span class="outline-index">{{ pad(question.number) }}</span>
              <span class="outline-copy"><strong>{{ question.topic_label || "待定主题" }}</strong><small>{{ outlineStatus(question) }}</small></span>
              <i v-if="question.status === 'completed'" aria-hidden="true">✓</i>
              <i v-else-if="question.status === 'in_progress'" aria-hidden="true"></i>
            </li>
          </ol>
        </section>

        <div class="interview-notice"><span aria-hidden="true">●</span><p>回答不会立即评分。完成面试后，你将获得基于本场证据的完整报告。</p></div>
      </aside>
    </main>

    <dialog ref="finishDialog" class="end-dialog" aria-labelledby="end-dialog-title" @click="closeOnBackdrop">
      <button class="dialog-close" type="button" aria-label="关闭" @click="finishDialog.close()">×</button>
      <span class="dialog-icon" aria-hidden="true">!</span>
      <h2 id="end-dialog-title">确认提前结束？</h2>
      <p>当前完成 {{ progress.completed_question_count }} / {{ progress.total_question_count }} 道主问题。报告将标记为“未完整完成”，维度结论仅供参考。</p>
      <div class="dialog-actions">
        <button class="secondary-action" type="button" @click="finishDialog.close()">继续面试</button>
        <button class="danger-action" type="button" :disabled="operationActive" @click="finishInterview">结束并查看报告</button>
      </div>
    </dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { interviewsApi } from "../api/interviews.js";
import { newIdempotencyKey } from "../api/http.js";
import { postSse } from "../api/sse.js";
import Brand from "../components/Brand.vue";
import InlineState from "../components/InlineState.vue";
import InterviewMessage from "../components/InterviewMessage.vue";
import ThinkingMessage from "../components/ThinkingMessage.vue";
import ThemeToggle from "../components/ThemeToggle.vue";

const route = useRoute();
const router = useRouter();
const interviewId = String(route.params.interviewId || "");
const interview = ref(null);
const messages = ref([]);
const streamMessage = ref(null);
const optimisticMessage = ref(null);
const pendingAnswer = ref(null);
const answerText = ref("");
const initialLoading = ref(true);
const fatalError = ref(null);
const streamError = ref(null);
const operationActive = ref(false);
const thinking = ref(false);
const thinkingLabel = ref("面试官正在思考");
const isTyping = ref(false);
const elapsedSeconds = ref(0);
const chatStream = ref(null);
const answerInput = ref(null);
const finishDialog = ref(null);
const seenEvents = new Set();
let timerId = null;
let typeTimer = null;
let typingQueue = [];
let finalStreamMessage = null;
let typingResolvers = [];
let submittedAnswer = null;

const operationStorageKey = `tiemian-operation-${interviewId}`;
const progress = computed(() => interview.value?.progress || {
  current_question_number: 0,
  total_question_count: 5,
  completed_question_count: 0,
  completion_percent: 0,
  current_followup_count: 0,
  max_followups_per_question: 2,
  current_topic_label: null
});
const sessionHeading = computed(() => interview.value
  ? `${interview.value.config.position_label} · ${interview.value.config.difficulty_label}`
  : "AI Agent 开发");
const displayMessages = computed(() => {
  const result = [...messages.value];
  if (optimisticMessage.value && !result.some((item) => item.id === optimisticMessage.value.id)) result.push(optimisticMessage.value);
  if (streamMessage.value && !result.some((item) => item.id === streamMessage.value.id)) result.push(streamMessage.value);
  return result;
});
const canType = computed(() => interview.value?.status === "WAITING_ANSWER" && pendingAnswer.value && !operationActive.value);
const canSubmit = computed(() => {
  const value = answerText.value.trim();
  return canType.value && !isTyping.value && value.length >= (pendingAnswer.value?.min_length || 1)
    && value.length <= (pendingAnswer.value?.max_length || 1200);
});
const composerPlaceholder = computed(() => {
  if (operationActive.value) return thinkingLabel.value;
  if (interview.value?.status === "FAILED") return "请先重试失败步骤…";
  return pendingAnswer.value?.placeholder || "等待面试官提问…";
});
const formattedElapsed = computed(() => formatDuration(elapsedSeconds.value));
const progressRingStyle = computed(() => ({
  background: `conic-gradient(var(--blue) 0 ${progress.value.completion_percent}%, rgba(128, 154, 184, 0.11) ${progress.value.completion_percent}% 100%)`
}));

onMounted(async () => {
  document.body.className = "interview-page";
  document.title = "面试进行中｜铁面 AI 面试官";
  if (!interviewId) {
    fatalError.value = new Error("缺少面试会话 ID");
    initialLoading.value = false;
    return;
  }
  await loadInitialState();
  timerId = window.setInterval(() => { elapsedSeconds.value += 1; }, 1000);
});

onBeforeUnmount(() => {
  window.clearInterval(timerId);
  window.clearTimeout(typeTimer);
});

async function loadInitialState() {
  try {
    const snapshot = await loadSnapshot();
    if (["COMPLETED", "PARTIAL"].includes(snapshot.status)) {
      await router.replace({ name: "report", params: { interviewId } });
      return;
    }
    if (snapshot.status === "CREATED") {
      await startInterview();
    } else if (["RUNNING", "EVALUATING", "REPORTING"].includes(snapshot.status)) {
      const saved = readSavedOperation();
      if (saved) await runCommand(saved);
      else streamError.value = new Error("上一次连接未完成，请刷新状态或稍后重试。", { cause: "missing_operation" });
    }
  } catch (error) {
    fatalError.value = error;
  } finally {
    initialLoading.value = false;
  }
}

async function loadSnapshot() {
  const data = await interviewsApi.snapshot(interviewId);
  applySnapshot(data.interview);
  return data.interview;
}

function applySnapshot(snapshot) {
  interview.value = snapshot;
  messages.value = snapshot.messages || [];
  pendingAnswer.value = snapshot.pending_answer;
  elapsedSeconds.value = snapshot.timing?.elapsed_seconds || 0;
  if (snapshot.status !== "FAILED") streamError.value = null;
  if (snapshot.status === "FAILED" && snapshot.last_error) {
    streamError.value = new Error(snapshot.last_error.message);
  }
  scrollToLatest();
}

async function startInterview() {
  const command = {
    kind: "start",
    path: `/interviews/${interviewId}/start/stream`,
    body: { expected_row_version: interview.value.row_version },
    key: newIdempotencyKey(),
    thinkingLabel: "正在准备第一道问题"
  };
  await runCommand(command);
}

async function submitAnswer() {
  if (!canSubmit.value) {
    answerInput.value?.focus();
    return;
  }
  const content = answerText.value.trim();
  submittedAnswer = { content, accepted: false };
  optimisticMessage.value = {
    id: `temporary-${Date.now()}`,
    question_id: pendingAnswer.value.question_id,
    role: "candidate",
    kind: "answer",
    followup_level: pendingAnswer.value.followup_level,
    content,
    created_at: new Date().toISOString()
  };
  thinking.value = true;
  thinkingLabel.value = "面试官正在思考";
  scrollToLatest();
  await runCommand({
    kind: "answer",
    path: `/interviews/${interviewId}/answers/stream`,
    body: {
      interrupt_id: pendingAnswer.value.interrupt_id,
      answer_to_turn_id: pendingAnswer.value.answer_to_turn_id,
      content,
      expected_row_version: interview.value.row_version
    },
    key: newIdempotencyKey(),
    thinkingLabel: "面试官正在思考"
  });
}

async function finishInterview() {
  finishDialog.value?.close();
  thinking.value = true;
  thinkingLabel.value = "正在生成本场评估报告";
  await runCommand({
    kind: "finish",
    path: `/interviews/${interviewId}/finish/stream`,
    body: {
      reason: "USER_REQUESTED",
      confirm_partial_report: true,
      expected_row_version: interview.value.row_version
    },
    key: newIdempotencyKey(),
    thinkingLabel: "正在生成本场评估报告"
  });
}

async function retryFailedStep() {
  const lastError = interview.value?.last_error;
  if (!lastError) return loadSnapshot();
  thinking.value = true;
  thinkingLabel.value = "正在重试当前步骤";
  await runCommand({
    kind: "retry",
    path: `/interviews/${interviewId}/retry/stream`,
    body: {
      failed_operation_id: lastError.failed_operation_id,
      expected_row_version: interview.value.row_version
    },
    key: newIdempotencyKey(),
    thinkingLabel: "正在重试当前步骤"
  });
}

async function runCommand(command) {
  operationActive.value = true;
  streamError.value = null;
  thinking.value = true;
  thinkingLabel.value = command.thinkingLabel;
  saveOperation(command);
  let completed = false;
  try {
    await postSse(command.path, command.body, {
      idempotencyKey: command.key,
      onEvent: async (envelope) => {
        const data = envelope.data;
        const eventKey = `${data.operation_id}:${data.sequence}`;
        if (seenEvents.has(eventKey)) return;
        seenEvents.add(eventKey);
        await handleStreamEvent(data.event, data.payload, envelope);
        if (data.event === "stream.done") completed = true;
      }
    });
    await waitForTyping();
    if (completed) sessionStorage.removeItem(operationStorageKey);
    const snapshot = await loadSnapshot();
    if (["COMPLETED", "PARTIAL"].includes(snapshot.status)) {
      await router.push({ name: "report", params: { interviewId } });
    }
  } catch (error) {
    thinking.value = false;
    streamMessage.value = null;
    resetTypewriter();
    if (!submittedAnswer?.accepted) optimisticMessage.value = null;
    streamError.value = error;
    if (!["NETWORK_ERROR", "STREAM_DISCONNECTED"].includes(error.code)) {
      sessionStorage.removeItem(operationStorageKey);
    }
    try {
      const snapshot = await loadSnapshot();
      if (["COMPLETED", "PARTIAL"].includes(snapshot.status)) {
        await router.push({ name: "report", params: { interviewId } });
      } else if (snapshot.status !== "FAILED") {
        streamError.value = error;
      }
    } catch {
      // Keep the original, more useful stream error visible.
    }
  } finally {
    operationActive.value = false;
    thinking.value = false;
    optimisticMessage.value = null;
    submittedAnswer = null;
    scrollToLatest();
  }
}

async function handleStreamEvent(event, payload, envelope) {
  if (event === "stream.open") {
    if (interview.value) interview.value.status = payload.command === "FINISH_INTERVIEW" ? "REPORTING" : "RUNNING";
  } else if (event === "answer.accepted") {
    if (submittedAnswer) {
      submittedAnswer.accepted = true;
      upsertMessage({
        id: payload.answer_turn_id,
        question_id: payload.question_id,
        role: "candidate",
        kind: "answer",
        followup_level: payload.followup_level,
        content: submittedAnswer.content,
        created_at: payload.created_at
      });
      answerText.value = "";
      optimisticMessage.value = null;
    }
  } else if (event === "question.changed") {
    interview.value.current_question = payload.current_question;
  } else if (event === "question.meta") {
    thinking.value = false;
    beginTypewriter(payload);
  } else if (event === "question.delta") {
    thinking.value = false;
    enqueueText(payload.message_id, payload.text);
  } else if (event === "question.completed") {
    completeTypewriter(payload.message);
  } else if (event === "progress.updated") {
    interview.value.progress = payload.progress;
    interview.value.row_version = payload.row_version;
  } else if (event === "waiting.answer") {
    pendingAnswer.value = payload.pending_answer;
    interview.value.pending_answer = payload.pending_answer;
    interview.value.row_version = payload.row_version;
    interview.value.status = "WAITING_ANSWER";
  } else if (event === "report.delta") {
    thinking.value = true;
    thinkingLabel.value = "正在生成本场评估报告";
  } else if (event === "report.completed") {
    thinking.value = false;
  } else if (event === "interview.completed") {
    interview.value.status = payload.status;
  } else if (event === "error") {
    thinking.value = false;
    streamError.value = new Error(envelope.message);
  } else if (event === "stream.done") {
    interview.value.status = payload.final_status;
    interview.value.row_version = payload.row_version;
  }
  scrollToLatest();
}

function beginTypewriter(payload) {
  resetTypewriter();
  streamMessage.value = {
    id: payload.message_id,
    question_id: payload.question_id,
    role: "interviewer",
    kind: payload.kind,
    followup_level: payload.followup_level,
    content: "",
    created_at: new Date().toISOString()
  };
  isTyping.value = true;
}

function enqueueText(messageId, text) {
  if (!streamMessage.value || streamMessage.value.id !== messageId) return;
  typingQueue.push(...Array.from(text || ""));
  isTyping.value = true;
  if (!typeTimer) typeNextCharacter();
}

function completeTypewriter(message) {
  if (!streamMessage.value || streamMessage.value.id !== message.id) {
    upsertMessage(message);
    return;
  }
  finalStreamMessage = message;
  if (!typingQueue.length && !typeTimer) finishTypewriter();
}

function typeNextCharacter() {
  const character = typingQueue.shift();
  if (character !== undefined && streamMessage.value) {
    streamMessage.value.content += character;
    typeTimer = window.setTimeout(() => {
      typeTimer = null;
      typeNextCharacter();
    }, 14);
    if (typingQueue.length % 8 === 0) scrollToLatest();
    return;
  }
  typeTimer = null;
  if (finalStreamMessage) finishTypewriter();
  else if (!typingQueue.length) resolveTyping();
}

function finishTypewriter() {
  const message = finalStreamMessage;
  if (message) upsertMessage(message);
  streamMessage.value = null;
  finalStreamMessage = null;
  resolveTyping();
}

function resetTypewriter() {
  window.clearTimeout(typeTimer);
  typeTimer = null;
  typingQueue = [];
  finalStreamMessage = null;
  if (isTyping.value) resolveTyping();
}

function resolveTyping() {
  isTyping.value = false;
  typingResolvers.splice(0).forEach((resolve) => resolve());
}

function waitForTyping() {
  if (!isTyping.value) return Promise.resolve();
  return new Promise((resolve) => typingResolvers.push(resolve));
}

function upsertMessage(message) {
  const index = messages.value.findIndex((item) => item.id === message.id);
  if (index >= 0) messages.value.splice(index, 1, message);
  else messages.value.push(message);
}

function saveOperation(command) {
  sessionStorage.setItem(operationStorageKey, JSON.stringify(command));
}

function readSavedOperation() {
  try { return JSON.parse(sessionStorage.getItem(operationStorageKey)); }
  catch { return null; }
}

function openFinishDialog() {
  finishDialog.value?.showModal();
}

function closeOnBackdrop(event) {
  if (event.target === finishDialog.value) finishDialog.value.close();
}

function topicForMessage(message) {
  return interview.value?.question_map?.find((item) => item.question_id === message.question_id)?.topic_label || "";
}

function outlineStatus(question) {
  if (question.status === "completed") return `已完成 · ${question.followup_count} 次追问`;
  if (question.status === "in_progress") return question.followup_count
    ? `进行中 · 追问 ${question.followup_count}/${question.max_followups}`
    : "进行中 · 主问题";
  if (question.status === "abandoned") return "已结束 · 未评分";
  return "等待开始";
}

function depthClass(level) {
  const current = progress.value.current_followup_count;
  if (level < current) return "complete";
  if (level === current) return "current";
  return "";
}

function depthIcon(level) {
  if (level < progress.value.current_followup_count) return "✓";
  if (level === 0) return "•";
  return String(level);
}

function pad(value) {
  return String(value || 0).padStart(2, "0");
}

function formatDuration(value) {
  const minutes = Math.floor(value / 60);
  const seconds = String(value % 60).padStart(2, "0");
  return `${String(minutes).padStart(2, "0")}:${seconds}`;
}

async function scrollToLatest() {
  await nextTick();
  chatStream.value?.scrollTo({ top: chatStream.value.scrollHeight, behavior: "smooth" });
}
</script>
