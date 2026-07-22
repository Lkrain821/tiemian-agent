<template>
  <div class="page-root history-page-root">
    <div class="ambient-grid" aria-hidden="true"></div>

    <header class="site-header compact-header">
      <Brand />
      <div class="report-header-title history-header-title">
        <span>INTERVIEW ARCHIVE</span>
        <strong>历史面试</strong>
      </div>
      <div class="header-actions">
        <ThemeToggle />
        <RouterLink class="quiet-button link-button" to="/">开始新面试</RouterLink>
      </div>
    </header>

    <main class="history-main">
      <section class="history-hero" aria-labelledby="history-title">
        <div>
          <span class="section-eyebrow">YOUR INTERVIEW JOURNEY</span>
          <h1 id="history-title">每一次练习，<em>都有迹可循。</em></h1>
          <p>回看回答表现、评分证据与改进建议，让下一场比上一场更进一步。</p>
        </div>
        <RouterLink class="primary-action compact-action history-new-action" to="/">
          <span>开始新的面试</span><span class="action-arrow" aria-hidden="true">→</span>
        </RouterLink>
      </section>

      <section class="history-summary" aria-label="历史面试统计">
        <article><span>全部记录</span><strong>{{ summary.total_count }}</strong><small>TOTAL</small></article>
        <article><span>完整面试</span><strong>{{ summary.full_count }}</strong><small>COMPLETED</small></article>
        <article><span>提前结束</span><strong>{{ summary.partial_count }}</strong><small>PARTIAL</small></article>
      </section>

      <section class="history-section" aria-labelledby="history-list-title">
        <div class="report-section-heading history-section-heading">
          <div>
            <span class="section-number">01</span>
            <div><span class="section-eyebrow">PAST INTERVIEWS</span><h2 id="history-list-title">过往面试记录</h2></div>
          </div>
          <p v-if="pagination.total_items">共 {{ pagination.total_items }} 场 · 按完成时间倒序</p>
        </div>

        <div v-if="loading" class="history-list" aria-label="正在加载历史面试">
          <div v-for="index in 4" :key="index" class="history-card history-card-skeleton">
            <i></i><div><span></span><span></span><span></span></div><b></b>
          </div>
        </div>

        <InlineState
          v-else-if="error"
          tone="error"
          title="暂时无法读取历史面试"
          :message="error.message"
          action-label="重新加载"
          @action="loadHistory"
        />

        <InlineState
          v-else-if="!items.length"
          tone="empty"
          title="还没有历史面试"
          message="完成或提前结束一场面试后，记录和评估报告会自动保存在这里。"
          action-label="开始第一场面试"
          @action="router.push('/')"
        />

        <div v-else class="history-list">
          <RouterLink
            v-for="item in items"
            :key="item.interview_id"
            class="history-card"
            :to="{ name: 'report', params: { interviewId: item.interview_id } }"
          >
            <div class="history-date">
              <strong>{{ formatDay(item.completed_at || item.generated_at) }}</strong>
              <span>{{ formatYearMonth(item.completed_at || item.generated_at) }}</span>
              <small>{{ formatTime(item.completed_at || item.generated_at) }}</small>
            </div>

            <div class="history-card-content">
              <div class="history-card-topline">
                <span class="history-status" :class="{ partial: item.completeness === 'PARTIAL' }">
                  {{ item.status_label }}
                </span>
                <span>{{ item.config.position_label }}</span>
                <i></i>
                <span>{{ item.config.focus_label }}</span>
                <i></i>
                <span>{{ item.config.difficulty_label }}</span>
              </div>
              <h3>{{ item.overall.headline || "本场面试报告已生成" }}</h3>
              <div class="history-card-meta">
                <span>{{ item.completion.completed_question_count }} / {{ item.completion.total_question_count }} 题</span>
                <span>用时 {{ formatDuration(item.completion.duration_seconds) }}</span>
                <span>{{ item.overall.expectation_label || "基于本场证据" }}</span>
              </div>
            </div>

            <div class="history-score" :class="{ empty: item.overall.total_score == null }">
              <span>综合得分</span>
              <strong>{{ item.overall.total_score ?? "—" }}<small v-if="item.overall.total_score != null"> / {{ item.overall.max_score }}</small></strong>
              <em>{{ item.overall.level_label || "暂不评分" }}</em>
            </div>
            <span class="history-card-arrow" aria-hidden="true">→</span>
          </RouterLink>
        </div>

        <nav v-if="pagination.total_pages > 1" class="history-pagination" aria-label="历史面试分页">
          <button type="button" :disabled="!pagination.has_previous || loading" @click="goToPage(currentPage - 1)">← 上一页</button>
          <span>第 <strong>{{ currentPage }}</strong> / {{ pagination.total_pages }} 页</span>
          <button type="button" :disabled="!pagination.has_next || loading" @click="goToPage(currentPage + 1)">下一页 →</button>
        </nav>
      </section>
    </main>

    <footer class="minimal-footer history-footer">
      <span>TIEMIAN INTERVIEW ARCHIVE</span><span>每份结论都来自真实回答证据</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { interviewsApi } from "../api/interviews.js";
import Brand from "../components/Brand.vue";
import InlineState from "../components/InlineState.vue";
import ThemeToggle from "../components/ThemeToggle.vue";

const route = useRoute();
const router = useRouter();
const items = ref([]);
const summary = ref({ total_count: 0, full_count: 0, partial_count: 0 });
const pagination = ref({
  page: 1,
  page_size: 10,
  total_items: 0,
  total_pages: 0,
  has_previous: false,
  has_next: false
});
const loading = ref(true);
const error = ref(null);
const currentPage = computed(() => {
  const value = Number.parseInt(String(route.query.page || "1"), 10);
  return Number.isFinite(value) && value > 0 ? value : 1;
});

onMounted(() => {
  document.body.className = "history-page";
  document.title = "历史面试｜铁面 AI 面试官";
});

watch(currentPage, loadHistory, { immediate: true });

async function loadHistory() {
  loading.value = true;
  error.value = null;
  try {
    const data = await interviewsApi.history({ page: currentPage.value, pageSize: 10 });
    if (data.pagination.total_pages > 0 && currentPage.value > data.pagination.total_pages) {
      await router.replace({ name: "history", query: { page: data.pagination.total_pages } });
      return;
    }
    items.value = data.items;
    summary.value = data.summary;
    pagination.value = data.pagination;
  } catch (reason) {
    error.value = reason;
  } finally {
    loading.value = false;
  }
}

function goToPage(page) {
  if (page < 1 || page > pagination.value.total_pages || page === currentPage.value) return;
  router.push({ name: "history", query: page === 1 ? {} : { page } });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formatDay(value) {
  return formatDateParts(value).day;
}

function formatYearMonth(value) {
  const parts = formatDateParts(value);
  return `${parts.year}.${parts.month}`;
}

function formatTime(value) {
  if (!value) return "--:--";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
}

function formatDateParts(value) {
  if (!value) return { year: "----", month: "--", day: "--" };
  const parts = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" })
    .formatToParts(new Date(value));
  return Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
}

function formatDuration(value = 0) {
  const minutes = Math.floor(value / 60);
  const seconds = String(value % 60).padStart(2, "0");
  return `${String(minutes).padStart(2, "0")}:${seconds}`;
}
</script>
