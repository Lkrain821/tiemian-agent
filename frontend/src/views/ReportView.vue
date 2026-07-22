<template>
  <div class="page-root report-page-root">
    <div class="ambient-grid" aria-hidden="true"></div>

    <header class="site-header compact-header">
      <Brand />
      <div class="report-header-title">
        <span>ASSESSMENT REPORT</span>
        <strong>面试评估报告</strong>
      </div>
      <div class="header-actions">
        <ThemeToggle />
        <RouterLink class="quiet-button link-button" to="/history">历史记录</RouterLink>
        <RouterLink class="quiet-button link-button" to="/">重新面试</RouterLink>
      </div>
    </header>

    <main v-if="loading" class="report-main report-state-main">
      <div class="report-page-loader">
        <div class="report-loader-mark"><i></i><i></i><i></i></div>
        <span class="section-eyebrow">ASSESSMENT REPORT</span>
        <h1>正在读取评估报告</h1>
        <p>整理能力维度、逐题证据与改进建议…</p>
      </div>
    </main>

    <main v-else-if="error" class="report-main report-state-main">
      <InlineState
        tone="error"
        :title="errorTitle"
        :message="error.message"
        :action-label="errorActionLabel"
        @action="handleErrorAction"
      />
      <RouterLink class="text-return-link" to="/">返回开始页</RouterLink>
    </main>

    <main v-else class="report-main">
      <section class="report-hero" aria-labelledby="report-title">
        <div class="report-intro">
          <span class="section-eyebrow">INTERVIEW {{ report.completeness === "FULL" ? "COMPLETED" : "ENDED EARLY" }} · {{ generatedDate }}</span>
          <h1 id="report-title">{{ report.overall.headline || "本场面试评估已生成。" }}</h1>
          <p>{{ report.overall.summary || report.completion.limitation_note }}</p>
          <div class="report-tags">
            <span>{{ report.config.position_label }}</span>
            <span>{{ report.config.focus_label }}</span>
            <span>{{ report.config.difficulty_label }}</span>
            <span>{{ report.completion.completed_question_count }} / {{ report.completion.total_question_count }} 已完成</span>
            <span>用时 {{ formattedDuration }}</span>
          </div>
        </div>

        <div class="total-score-card" :class="{ 'score-insufficient': totalScore == null }">
          <div class="score-topline"><span>综合得分</span><small>TOTAL SCORE</small></div>
          <div class="score-value"><strong>{{ totalScore ?? "—" }}</strong><span>/ {{ report.overall.max_score || 100 }}</span></div>
          <div class="score-band"><i></i><span>{{ report.overall.level_label || "证据不足" }}</span><small>{{ report.overall.expectation_label || "暂不形成结论" }}</small></div>
          <div class="score-scale" aria-hidden="true">
            <i></i><i></i><i></i><i></i><i></i><span :style="{ '--score-position': `${scorePosition}%` }"></span>
          </div>
          <div class="score-scale-labels"><span>需加强</span><span>达到预期</span><span>优秀</span></div>
        </div>
      </section>

      <InlineState
        v-if="report.completeness === 'PARTIAL'"
        class="partial-report-banner"
        tone="warning"
        title="本报告基于部分面试证据"
        :message="report.completion.limitation_note || '本场面试提前结束，未完成的问题不会生成得分或点评。'"
      />

      <section class="dimension-section" aria-labelledby="dimension-title">
        <div class="report-section-heading">
          <div>
            <span class="section-number">01</span>
            <div><span class="section-eyebrow">CAPABILITY PROFILE</span><h2 id="dimension-title">能力维度</h2></div>
          </div>
          <p>分数仅基于本场回答证据</p>
        </div>

        <div v-if="report.dimensions.length" class="dimension-grid five-dimension-grid">
          <article
            v-for="(dimension, index) in report.dimensions"
            :key="dimension.code"
            class="dimension-card"
            :class="{ 'focus-card': isFocusDimension(dimension), 'dimension-insufficient': dimension.score == null }"
          >
            <div class="dimension-top">
              <span class="dimension-icon">{{ pad(index + 1) }}</span>
              <span class="dimension-score">{{ dimension.score ?? "—" }}<small>/{{ dimension.max_score || 100 }}</small></span>
            </div>
            <h3>{{ dimension.short_label || dimension.label }}</h3>
            <p>{{ dimension.summary || "本场可用回答证据不足，暂不形成维度结论。" }}</p>
            <div class="dimension-bar"><i :style="{ '--bar-width': `${dimension.score ?? 0}%` }"></i></div>
            <span class="dimension-level" :class="dimensionLevelClass(dimension)">{{ dimension.level_label || "证据不足" }}</span>
          </article>
        </div>
        <InlineState v-else tone="empty" title="暂无能力维度" message="本场没有足够的已评分回答用于生成能力画像。" />
      </section>

      <section v-if="primaryStrength || primaryGap" class="evidence-summary" aria-label="表现摘要">
        <article v-if="primaryStrength" class="summary-card strength-summary">
          <div class="summary-label"><span aria-hidden="true">↑</span> 明确优势</div>
          <h3>{{ primaryStrength.title }}</h3>
          <p>{{ primaryStrength.summary }}</p>
        </article>
        <article v-if="primaryGap" class="summary-card risk-summary">
          <div class="summary-label"><span aria-hidden="true">△</span> 主要短板</div>
          <h3>{{ primaryGap.title }}</h3>
          <p>{{ primaryGap.summary }}</p>
        </article>
      </section>

      <section class="question-review" aria-labelledby="review-title">
        <div class="report-section-heading">
          <div>
            <span class="section-number">02</span>
            <div><span class="section-eyebrow">QUESTION REVIEW</span><h2 id="review-title">逐题得分与点评</h2></div>
          </div>
          <p>展开查看回答证据与改进方向</p>
        </div>

        <div v-if="report.question_reviews.length" class="review-list">
          <details
            v-for="review in report.question_reviews"
            :key="review.question_id"
            ref="reviewItems"
            class="review-item"
            @toggle="keepOneReviewOpen"
          >
            <summary>
              <span class="review-index">{{ pad(review.number) }}</span>
              <span class="review-title"><small>{{ review.topic_label }} · {{ review.followup_count }} 次追问</small><strong>{{ review.stem }}</strong></span>
              <span class="review-score" :class="reviewScoreClass(review.score)"><strong>{{ review.score ?? "—" }}</strong><small>{{ review.score == null ? "" : "分" }}</small></span>
              <span class="detail-toggle" aria-hidden="true">+</span>
            </summary>
            <div class="review-body">
              <div><h4>回答亮点</h4><ul><li v-for="item in review.strengths" :key="item">{{ item }}</li><li v-if="!review.strengths.length">暂无明确优势证据</li></ul></div>
              <div><h4>可以更好</h4><ul><li v-for="item in review.gaps" :key="item">{{ item }}</li><li v-if="!review.gaps.length">暂无明显短板</li></ul></div>
              <div class="review-improvement"><h4>本题改进方向</h4><p>{{ review.improvement }}</p></div>
              <div v-if="review.better_answer_outline?.length" class="answer-outline"><h4>更好回答框架</h4><ol><li v-for="item in review.better_answer_outline" :key="item">{{ item }}</li></ol></div>
              <div v-if="review.evidence?.length" class="evidence-quote">
                <span>证据摘录</span>
                <p v-for="evidence in review.evidence" :key="evidence.turn_id">“{{ evidence.quote }}”</p>
              </div>
            </div>
          </details>
        </div>
        <InlineState v-else tone="empty" title="暂无逐题点评" message="本场没有完成可评分的主问题，因此不会生成虚构点评。" />
      </section>

      <section class="improvement-section" aria-labelledby="improvement-title">
        <div class="report-section-heading">
          <div>
            <span class="section-number">03</span>
            <div><span class="section-eyebrow">NEXT ACTIONS</span><h2 id="improvement-title">三条优先改进建议</h2></div>
          </div>
          <p>按投入产出比排序</p>
        </div>

        <div v-if="report.suggestions.length" class="improvement-list">
          <article
            v-for="suggestion in report.suggestions"
            :key="suggestion.priority"
            class="improvement-card"
            :class="{ 'priority-one': suggestion.priority === 1 }"
          >
            <span class="priority-index">{{ pad(suggestion.priority) }}</span>
            <div class="improvement-content">
              <div class="improvement-heading"><span>{{ suggestion.priority_label }}</span><small>{{ suggestion.effort_label }}</small></div>
              <h3>{{ suggestion.title }}</h3>
              <p>{{ suggestion.why }} {{ suggestion.actions.join("；") }}</p>
              <div class="action-check"><i aria-hidden="true">✓</i><span>完成标志：{{ suggestion.completion_criteria }}</span></div>
            </div>
          </article>
        </div>
        <InlineState v-else tone="empty" title="暂无改进建议" message="可完成更多问题后再次练习，以获得基于证据的行动建议。" />
      </section>

      <section v-if="report.next_interview" class="report-cta">
        <div><span class="section-eyebrow">READY FOR ANOTHER ROUND?</span><h2>针对短板，再练一次。</h2><p>建议下一场选择“{{ report.next_interview.focus_label }} · {{ report.next_interview.difficulty_label }}”。{{ report.next_interview.reason }}</p></div>
        <RouterLink class="primary-action compact-action" :to="nextInterviewLink"><span>开始新的面试</span><span class="action-arrow" aria-hidden="true">→</span></RouterLink>
      </section>

      <p class="report-disclaimer">{{ report.disclaimer }}</p>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { interviewsApi } from "../api/interviews.js";
import Brand from "../components/Brand.vue";
import InlineState from "../components/InlineState.vue";
import ThemeToggle from "../components/ThemeToggle.vue";

const route = useRoute();
const router = useRouter();
const interviewId = String(route.params.interviewId || "");
const report = ref(null);
const loading = ref(true);
const error = ref(null);
const reviewItems = ref([]);

const totalScore = computed(() => report.value?.overall?.total_score ?? null);
const scorePosition = computed(() => Math.min(100, Math.max(0, totalScore.value ?? 0)));
const generatedDate = computed(() => formatDate(report.value?.generated_at));
const formattedDuration = computed(() => formatDuration(report.value?.completion?.duration_seconds || 0));
const primaryStrength = computed(() => report.value?.highlights?.strengths?.[0] || null);
const primaryGap = computed(() => report.value?.highlights?.primary_gap || null);
const errorTitle = computed(() => error.value?.code === "REPORT_NOT_READY" ? "报告还在生成" : "无法读取评估报告");
const errorActionLabel = computed(() => error.value?.code === "INTERVIEW_NOT_FOUND" ? "开始新的面试" : "重新获取报告");
const nextInterviewLink = computed(() => ({
  name: "start",
  query: {
    position: report.value.next_interview.position_code,
    focus: report.value.next_interview.focus_code,
    difficulty: report.value.next_interview.difficulty
  }
}));

onMounted(() => {
  document.body.className = "report-page";
  document.title = "面试评估报告｜铁面 AI 面试官";
  loadReport();
});

async function loadReport() {
  loading.value = true;
  error.value = null;
  try {
    const data = await interviewsApi.report(interviewId);
    report.value = data.report;
  } catch (reason) {
    error.value = reason;
  } finally {
    loading.value = false;
  }
}

function handleErrorAction() {
  if (error.value?.code === "INTERVIEW_NOT_FOUND") return router.push("/");
  return loadReport();
}

function keepOneReviewOpen(event) {
  if (!event.target.open) return;
  reviewItems.value.forEach((item) => {
    if (item !== event.target) item.open = false;
  });
}

function isFocusDimension(dimension) {
  return dimension.level_code === "NEEDS_IMPROVEMENT" || dimension.level_code === "FOCUS" || (dimension.score != null && dimension.score < 60);
}

function dimensionLevelClass(dimension) {
  if (["STRENGTH", "BEST"].includes(dimension.level_code)) return "strong";
  if (isFocusDimension(dimension)) return "focus";
  return "";
}

function reviewScoreClass(score) {
  if (score == null) return "insufficient";
  if (score >= 85) return "high";
  if (score < 60) return "needs-work";
  return "";
}

function pad(value) {
  return String(value || 0).padStart(2, "0");
}

function formatDuration(value) {
  const minutes = Math.floor(value / 60);
  const seconds = String(value % 60).padStart(2, "0");
  return `${String(minutes).padStart(2, "0")}:${seconds}`;
}

function formatDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" })
    .format(new Date(value))
    .replaceAll("/", ".");
}
</script>
