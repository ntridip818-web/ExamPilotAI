const API_BASE_URL = "https://YOUR-BACKEND-URL-HERE.onrender.com";

const board = document.getElementById("board");
const loadingState = document.getElementById("loadingState");
const emptyTemplate = document.getElementById("emptyStateTemplate");
const cardTemplate = document.getElementById("examCardTemplate");

let allExams = [];
let activeTab = "all";

function getSavedIds() {
  return JSON.parse(localStorage.getItem("exampilotai_saved") || "[]");
}

function toggleSaved(examId) {
  const saved = getSavedIds();
  const idx = saved.indexOf(examId);
  if (idx === -1) {
    saved.push(examId);
  } else {
    saved.splice(idx, 1);
  }
  localStorage.setItem("exampilotai_saved", JSON.stringify(saved));
  return saved.includes(examId);
}

async function fetchExams() {
  const state = document.getElementById("stateFilter").value;
  const category = document.getElementById("categoryFilter").value;

  const params = new URLSearchParams();
  if (state) params.set("state", state);
  if (category) params.set("category", category);

  try {
    const res = await fetch(`${API_BASE_URL}/exams/?${params.toString()}`);
    if (!res.ok) throw new Error("Request failed");
    allExams = await res.json();
  } catch (err) {
    console.error("Could not load exams:", err);
    allExams = [];
    showEmptyState(
      "Couldn't reach the server",
      "Check your internet connection, or the backend may still be starting up (free servers can take ~30s to wake up)."
    );
    loadingState.remove();
    return;
  }
  render();
}

function daysUntil(dateStr) {
  if (!dateStr) return null;
  const diff = new Date(dateStr) - new Date();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

function formatDate(dateStr) {
  if (!dateStr) return "—";
  return new Date(dateStr).toLocaleDateString("en-IN", {
    day: "2-digit", month: "short", year: "numeric"
  });
}

function showEmptyState(title, message) {
  const node = emptyTemplate.content.cloneNode(true);
  node.querySelector("h3").textContent = title;
  node.querySelector("p").textContent = message;
  board.appendChild(node);
}

function render() {
  board.innerHTML = "";
  const savedIds = getSavedIds();

  let list = allExams;
  if (activeTab === "closing") {
    list = list.filter(e => {
      const d = daysUntil(e.application_end_date);
      return d !== null && d >= 0 && d <= 7;
    });
  } else if (activeTab === "saved") {
    list = list.filter(e => savedIds.includes(e.id));
  }

  if (list.length === 0) {
    const messages = {
      all: ["No notices yet", "Verified exam notifications will appear here as soon as they're added."],
      closing: ["Nothing closing soon", "No application deadlines in the next 7 days right now."],
      saved: ["No saved exams", "Tap Save on a notice to track it here."],
    };
    showEmptyState(...messages[activeTab]);
    return;
  }

  list.forEach(exam => {
    const node = cardTemplate.content.cloneNode(true);
    const card = node.querySelector(".notice-card");

    node.querySelector(".notice-org").textContent = exam.organization;
    node.querySelector(".notice-title").textContent = exam.title;
    node.querySelector(".notice-state").textContent = exam.state || "All India";
    node.querySelector(".notice-category").textContent = exam.category || "General";
    node.querySelector(".deadline-date").textContent = formatDate(exam.application_end_date);

    const days = daysUntil(exam.application_end_date);
    const countdownEl = node.querySelector(".countdown");
    const numEl = node.querySelector(".countdown-num");
    if (days === null) {
      numEl.textContent = "—";
      node.querySelector(".countdown-unit").textContent = "no deadline";
    } else if (days < 0) {
      numEl.textContent = "Closed";
      node.querySelector(".countdown-unit").textContent = "";
    } else {
      numEl.textContent = days;
      if (days > 7) countdownEl.classList.add("is-calm");
    }

    const pdfBtn = node.querySelector(".btn-pdf");
    if (exam.official_pdf_url) {
      pdfBtn.href = exam.official_pdf_url;
    } else {
      pdfBtn.style.display = "none";
    }

    const saveBtn = node.querySelector(".btn-save");
    const saveLabel = node.querySelector(".save-label");
    const isSaved = savedIds.includes(exam.id);
    if (isSaved) {
      saveBtn.classList.add("is-saved");
      saveLabel.textContent = "Saved";
    }
    saveBtn.addEventListener("click", () => {
      const nowSaved = toggleSaved(exam.id);
      saveBtn.classList.toggle("is-saved", nowSaved);
      saveLabel.textContent = nowSaved ? "Saved" : "Save";
      if (activeTab === "saved" && !nowSaved) render();
    });

    board.appendChild(node);
  });
}

function setActiveTab(tabName) {
  activeTab = tabName;
  document.querySelectorAll(".tab, .bnav-item").forEach(el => {
    el.classList.toggle("is-active", el.dataset.tab === tabName);
  });
  render();
}

document.querySelectorAll(".tab, .bnav-item").forEach(el => {
  el.addEventListener("click", () => setActiveTab(el.dataset.tab));
});

const filterToggle = document.getElementById("filterToggle");
const filterPanel = document.getElementById("filterPanel");
filterToggle.addEventListener("click", () => {
  filterPanel.hidden = !filterPanel.hidden;
});
document.getElementById("stateFilter").addEventListener("change", fetchExams);
document.getElementById("categoryFilter").addEventListener("change", fetchExams);

fetchExams();

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}
