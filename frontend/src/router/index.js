import { createRouter, createWebHistory } from "vue-router";

import InterviewView from "../views/InterviewView.vue";
import HistoryView from "../views/HistoryView.vue";
import ReportView from "../views/ReportView.vue";
import StartView from "../views/StartView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "start", component: StartView },
    { path: "/history", name: "history", component: HistoryView },
    { path: "/interviews/:interviewId", name: "interview", component: InterviewView },
    { path: "/interviews/:interviewId/report", name: "report", component: ReportView },
    { path: "/:pathMatch(.*)*", redirect: "/" }
  ],
  scrollBehavior() {
    return { top: 0 };
  }
});

export default router;
