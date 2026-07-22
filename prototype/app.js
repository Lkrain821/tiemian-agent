(() => {
  "use strict";

  const setupForm = document.querySelector("#interviewSetup");
  const sessionKey = "tiemian-prototype-session";

  if (setupForm) {
    setupForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const formData = new FormData(setupForm);
      const session = {
        position: formData.get("position"),
        focus: formData.get("focus"),
        difficulty: formData.get("difficulty")
      };

      sessionStorage.setItem(sessionKey, JSON.stringify(session));
      window.location.href = "interview.html";
    });
  }

  let session = null;
  try {
    session = JSON.parse(sessionStorage.getItem(sessionKey));
  } catch {
    session = null;
  }

  if (session) {
    const sessionTitle = document.querySelector(".session-title strong");
    if (sessionTitle) {
      sessionTitle.textContent = `${session.position} · ${session.difficulty}`;
    }

    const reportTags = document.querySelectorAll(".report-tags span");
    if (reportTags.length >= 2) {
      reportTags[0].textContent = session.focus || session.position;
      reportTags[1].textContent = session.difficulty;
    }
  }

  const elapsedTime = document.querySelector("#elapsedTime");
  if (elapsedTime) {
    let elapsedSeconds = Number(elapsedTime.dataset.seconds || 0);
    window.setInterval(() => {
      elapsedSeconds += 1;
      const minutes = Math.floor(elapsedSeconds / 60);
      const seconds = String(elapsedSeconds % 60).padStart(2, "0");
      elapsedTime.textContent = `${String(minutes).padStart(2, "0")}:${seconds}`;
    }, 1000);
  }

  const answerForm = document.querySelector("#answerForm");
  const answerInput = document.querySelector("#answerInput");
  const charCount = document.querySelector("#charCount");
  const chatStream = document.querySelector("#chatStream");

  if (answerForm && answerInput && charCount && chatStream) {
    const sendButton = answerForm.querySelector(".send-button");

    answerInput.addEventListener("input", () => {
      charCount.textContent = String(answerInput.value.length);
    });

    answerInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && event.ctrlKey) {
        event.preventDefault();
        answerForm.requestSubmit();
      }
    });

    answerForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const answer = answerInput.value.trim();
      if (!answer) {
        answerInput.focus();
        return;
      }

      appendMessage({ role: "candidate", text: answer });
      answerInput.value = "";
      charCount.textContent = "0";
      answerInput.disabled = true;
      sendButton.disabled = true;
      sendButton.firstChild.textContent = "分析中… ";

      window.setTimeout(() => {
        appendMessage({
          role: "interviewer",
          label: "追问 2 / 2",
          text: "如果离线对照实验确认重排模型退化，但线上暂时不能立即替换模型，你会采用什么止损方案，并如何判断止损是否有效？"
        });
        updateFollowUpDepth();
        answerInput.disabled = false;
        sendButton.disabled = false;
        sendButton.firstChild.textContent = "提交回答 ";
        answerInput.focus();
      }, 650);
    });

    function appendMessage({ role, text, label }) {
      const article = document.createElement("article");
      article.className = `message ${role === "candidate" ? "candidate-message" : "interviewer-message follow-up-message"}`;

      const avatar = document.createElement("div");
      avatar.className = "message-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = role === "candidate" ? "我" : "铁";

      const content = document.createElement("div");
      content.className = "message-content";

      const meta = document.createElement("div");
      meta.className = "message-meta";
      const name = document.createElement("strong");
      name.textContent = role === "candidate" ? "我的回答" : "铁面 · 面试官";
      const time = document.createElement("time");
      time.textContent = new Intl.DateTimeFormat("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false
      }).format(new Date());
      meta.append(name, time);

      const bubble = document.createElement("div");
      bubble.className = "message-bubble";
      if (label) {
        const followUpLabel = document.createElement("span");
        followUpLabel.className = "follow-up-label";
        followUpLabel.textContent = label;
        bubble.append(followUpLabel);
      }
      const paragraph = document.createElement("p");
      paragraph.textContent = text;
      bubble.append(paragraph);

      content.append(meta, bubble);
      article.append(avatar, content);
      chatStream.append(article);
      chatStream.scrollTo({ top: chatStream.scrollHeight, behavior: "smooth" });
    }

    function updateFollowUpDepth() {
      const followUpLevel = document.querySelector("#followUpLevel");
      if (followUpLevel) {
        followUpLevel.textContent = "2";
      }

      const steps = document.querySelectorAll(".depth-step");
      const lines = document.querySelectorAll(".depth-line");
      if (steps.length >= 3) {
        steps[1].classList.remove("current");
        steps[1].classList.add("complete");
        steps[1].querySelector("i").textContent = "✓";
        steps[2].classList.add("current");
      }
      if (lines.length >= 2) {
        lines[1].classList.add("active");
      }

      const activeOutline = document.querySelector(".question-outline li.active small");
      if (activeOutline) {
        activeOutline.textContent = "进行中 · 追问 2/2";
      }
    }
  }

  const endDialog = document.querySelector("#endDialog");
  const openEndButton = document.querySelector("[data-open-end]");
  const closeEndButtons = document.querySelectorAll("[data-close-end]");

  if (endDialog && openEndButton) {
    openEndButton.addEventListener("click", () => endDialog.showModal());
    closeEndButtons.forEach((button) => {
      button.addEventListener("click", () => endDialog.close());
    });
    endDialog.addEventListener("click", (event) => {
      if (event.target === endDialog) {
        endDialog.close();
      }
    });
  }

  const reviewItems = document.querySelectorAll(".review-item");
  reviewItems.forEach((item) => {
    item.addEventListener("toggle", () => {
      if (!item.open) return;
      reviewItems.forEach((otherItem) => {
        if (otherItem !== item) otherItem.open = false;
      });
    });
  });
})();
