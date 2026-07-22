<template>
  <div class="page-root start-page-root">
    <div class="ambient-grid" aria-hidden="true"></div>

    <header class="site-header">
      <Brand />
      <div class="header-meta">
        <RouterLink class="quiet-button link-button history-header-link" to="/history">历史记录</RouterLink>
        <ThemeToggle />
        <span class="system-status" :class="{ 'status-down': readyState === 'error' }">
          <i></i>
          {{ readinessText }}
        </span>
        <span class="header-divider" aria-hidden="true"></span>
        <span class="version-label">{{ options?.product?.release_label || "MVP / 01" }}</span>
      </div>
    </header>

    <main class="start-main">
      <section class="start-hero" aria-labelledby="hero-title">
        <div class="hero-kicker"><span>专项训练</span> AI AGENT DEVELOPMENT</div>
        <h1 id="hero-title">把每一次回答，<br /><em>练成真正的竞争力。</em></h1>
        <p class="hero-lead">
          针对 AI Agent 开发岗位的深度模拟面试。根据你的回答动态追问，在真实压力之前，找到技术盲区与表达短板。
        </p>

        <div class="interview-spec" aria-label="面试规格">
          <div class="spec-item">
            <strong>{{ options?.interview_spec?.main_question_count ?? 5 }}</strong>
            <span>道主问题</span>
          </div>
          <div class="spec-separator" aria-hidden="true"></div>
          <div class="spec-item">
            <strong>{{ options?.interview_spec?.max_followups_per_question ?? 2 }}</strong>
            <span>次追问上限</span>
          </div>
          <div class="spec-separator" aria-hidden="true"></div>
          <div class="spec-item">
            <strong>{{ options?.interview_spec?.estimated_duration_minutes ?? 25 }}<small>min</small></strong>
            <span>预计用时</span>
          </div>
        </div>

        <div class="question-preview" aria-label="面试问题示例">
          <div class="preview-topline">
            <span class="preview-label">QUESTION PREVIEW</span>
            <span class="preview-index">02 / 05</span>
          </div>
          <p>“{{ options?.preview_question?.content || "一个 RAG 系统的召回效果突然下降，你会按照什么顺序排查？" }}”</p>
          <div class="preview-signal"><span aria-hidden="true"></span>铁面将根据回答继续追问</div>
        </div>
      </section>

      <section class="setup-card" aria-labelledby="setup-title">
        <div class="card-step"><span>01</span> 面试配置</div>
        <div class="setup-heading">
          <div>
            <h2 id="setup-title">准备开始</h2>
            <p>选择本场面试的方向与难度</p>
          </div>
          <span class="secure-badge">仅供练习</span>
        </div>

        <InlineState
          v-if="pageError"
          tone="error"
          title="暂时无法加载面试配置"
          :message="pageError.message"
          action-label="重新加载"
          @action="loadPage"
        />
        <div v-else-if="pageLoading" class="setup-loading" aria-label="正在加载面试配置">
          <span></span><span></span><span></span><span></span>
        </div>

        <form v-else id="interviewSetup" class="setup-form" @submit.prevent="startInterview">
          <fieldset class="form-section">
            <legend><span>岗位方向</span><small>POSITION</small></legend>
            <label
              v-for="position in options.positions"
              :key="position.code"
              class="position-option"
              :class="{ selected: form.position_code === position.code }"
            >
              <input v-model="form.position_code" type="radio" name="position" :value="position.code" />
              <span class="position-icon" aria-hidden="true">AI</span>
              <span class="position-copy">
                <strong>{{ position.label }}</strong>
                <small>{{ position.description }}</small>
              </span>
              <span class="option-check" aria-hidden="true"></span>
            </label>
          </fieldset>

          <fieldset class="form-section">
            <legend><span>能力侧重点</span><small>FOCUS</small></legend>
            <div class="focus-grid">
              <label v-for="focus in focusOptions" :key="focus.code" class="focus-option">
                <input v-model="form.focus_code" type="radio" name="focus" :value="focus.code" />
                <span>{{ focus.short_label }}</span>
              </label>
            </div>
          </fieldset>

          <fieldset class="form-section">
            <legend><span>面试难度</span><small>DIFFICULTY</small></legend>
            <div class="difficulty-control">
              <label v-for="difficulty in options.difficulties" :key="difficulty.code">
                <input v-model="form.difficulty" type="radio" name="difficulty" :value="difficulty.code" />
                <span><strong>{{ difficulty.label }}</strong><small>{{ difficulty.description }}</small></span>
              </label>
            </div>
          </fieldset>

          <div class="rules-strip">
            <span class="info-symbol" aria-hidden="true">i</span>
            <p>{{ ruleSummary }}</p>
          </div>

          <InlineState
            v-if="submitError"
            tone="error"
            title="无法开始面试"
            :message="submitError.message"
          />

          <button class="primary-action" type="submit" :disabled="!canStart">
            <span>{{ submitting ? "正在创建面试…" : readyState === "error" ? "系统暂未就绪" : "开始模拟面试" }}</span>
            <span class="action-arrow" aria-hidden="true">{{ submitting ? "·" : "→" }}</span>
          </button>
          <p class="form-footnote">{{ options.usage_disclaimer }}</p>
        </form>
      </section>
    </main>

    <footer class="minimal-footer">
      <span>TIEMIAN INTERVIEW LAB</span><span>练习 · 复盘 · 进阶</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { interviewsApi } from "../api/interviews.js";
import { newIdempotencyKey } from "../api/http.js";
import Brand from "../components/Brand.vue";
import InlineState from "../components/InlineState.vue";
import ThemeToggle from "../components/ThemeToggle.vue";

const route = useRoute();
const router = useRouter();
const options = ref(null);
const readyState = ref("loading");
const pageLoading = ref(true);
const pageError = ref(null);
const submitError = ref(null);
const submitting = ref(false);
const form = reactive({ position_code: "", focus_code: "", difficulty: "" });

const focusOptions = computed(() => {
  return options.value?.positions?.find((item) => item.code === form.position_code)?.focus_options || [];
});
const readinessText = computed(() => ({
  loading: "正在检查模拟面试系统",
  ready: "模拟面试系统已就绪",
  error: "模拟面试系统暂未就绪"
}[readyState.value]));
const canStart = computed(() => {
  return readyState.value === "ready" && !submitting.value && form.position_code && form.focus_code && form.difficulty;
});
const ruleSummary = computed(() => {
  return options.value?.rules?.items?.[1] || "面试中不展示分数；完成全部问题后生成完整评估报告。";
});

onMounted(() => {
  document.body.className = "start-page";
  document.title = "开始面试｜铁面 AI 面试官";
  loadPage();
});

async function loadPage() {
  pageLoading.value = true;
  pageError.value = null;
  readyState.value = "loading";
  const [optionsResult, readyResult] = await Promise.allSettled([
    interviewsApi.options(),
    interviewsApi.readiness()
  ]);
  if (optionsResult.status === "rejected") {
    pageError.value = optionsResult.reason;
  } else {
    options.value = optionsResult.value;
    Object.assign(form, options.value.defaults);
    applyRouteRecommendation();
  }
  readyState.value = readyResult.status === "fulfilled" && readyResult.value.status === "READY"
    ? "ready"
    : "error";
  if (readyResult.status === "rejected" && !pageError.value) submitError.value = readyResult.reason;
  pageLoading.value = false;
}

function applyRouteRecommendation() {
  const position = options.value.positions.find((item) => item.code === route.query.position);
  if (position) form.position_code = position.code;
  const focus = position?.focus_options?.find((item) => item.code === route.query.focus);
  if (focus) form.focus_code = focus.code;
  const difficulty = options.value.difficulties.find((item) => item.code === route.query.difficulty);
  if (difficulty) form.difficulty = difficulty.code;
}

async function startInterview() {
  if (!canStart.value) return;
  submitting.value = true;
  submitError.value = null;
  try {
    const data = await interviewsApi.create(
      {
        ...form,
        rules_version: options.value.rules.version,
        rules_confirmed: true
      },
      newIdempotencyKey()
    );
    const interviewId = data.interview.id;
    sessionStorage.setItem("tiemian-active-interview", interviewId);
    await router.push({ name: "interview", params: { interviewId }, query: { start: "1" } });
  } catch (error) {
    submitError.value = error;
  } finally {
    submitting.value = false;
  }
}
</script>
