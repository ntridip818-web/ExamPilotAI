const API_BASE_URL = "https://exampilotai.onrender.com";

const board = document.getElementById("board");
const loadingState = document.getElementById("loadingState");
const emptyTemplate = document.getElementById("emptyStateTemplate");
const cardTemplate = document.getElementById("examCardTemplate");

let allExams = [];
let savedRecords = [];
let activeTab = "all";
let currentUser = null;

function getSupabase() {
  return window.examPilotSupabase;
}

function getAuthHeaders() {
  return currentUser?.access_token
    ? { Authorization: `Bearer ${currentUser.access_token}` }
    : {};
}

async function ensureBackendUser() {
  const supabase = getSupabase();
  if (!supabase) return null;

  const session = await window.getExamPilotSession();
  if (!session?.user) return null;

  currentUser = {
    supabaseUser: session.user,
    access_token: session.access_token,
    id: null,
  };

  const headers = {
    ...getAuthHeaders(),
    "Content-Type": "application/json",
  };

  let res = await fetch(`${API_BASE_URL}/users/`, {
    method: "POST",
    headers,
    body: JSON.stringify({ email: session.user.email }),
  });

  if (res.ok) {
    const user = await res.json();
    currentUser.id = user.id;
    return currentUser;
  }

  res = await fetch(`${API_BASE_URL}/users/me`, {
    headers: getAuthHeaders(),
  });

  if (!res.ok) {
    throw new Error("Could not load your ExamPilotAI profile");
  }

  const user = await res.json();
  currentUser.id = user.id;
  return currentUser;
}

async function refreshAuthUI() {
  const supabase = getSupabase();
  const title = document.getElementById("authTitle");
  const status = document.getElementById("authStatus");
  const fields = document.getElementById("authFields");
  const logoutBtn = document.getElementById("logoutBtn");

  if (!supabase) {
    title.textContent = "Supabase setup required";
    status.textContent = "Add the Publishable key in js/supabase-auth.js.";
    return;
  }

  const session = await window.getExamPilotSession();

  if (!session) {
    currentUser = null;
    title.textContent = "Sign in to ExamPilotAI";
    status.textContent = "Sign in to save exams to your account.";
    fields.hidden = false;
    logoutBtn.hidden = true;
    return;
  }

  try {
    await ensureBackendUser();
    title.textContent = session.user.email || "Signed in";
    status.textContent = "Your saved exams are linked to your account.";
    fields.hidden = true;
    logoutBtn.hidden = false;
  } catch (err) {
    console.error(err);
    status.textContent = err.message;
  }
}

async function signIn() {
  const supabase = getSupabase();
  if (!supabase) return;

  const email = document.getElementById("authEmail").value.trim();
  const password = document.getElementById("authPassword").value;

  if (!email || !password) {
    document.getElementById("authStatus").textContent =
      "Enter your email and password.";
    return;
  }

  document.getElementById("authStatus").textContent = "Signing in…";

  const { error } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    document.getElementById("authStatus").textContent = error.message;
    return;
  }

  await refreshAuthUI();
  await fetchSavedExams();
  render();
}

async function signUp() {
  const supabase = getSupabase();
  if (!supabase) return;

  const email = document.getElementById("authEmail").value.trim();
  const password = document.getElementById("authPassword").value;

  if (!email || !password) {
    document.getElementById("authStatus").textContent =
      "Enter your email and password.";
    return;
  }

  if (password.length < 6) {
    document.getElementById("authStatus").textContent =
      "Password must be at least 6 characters.";
    return;
  }

  document.getElementById("authStatus").textContent = "Creating account…";

  const { data, error } = await supabase.auth.signUp({
    email,
    password,
  });

  if (error) {
    document.getElementById("authStatus").textContent = error.message;
    return;
  }

  if (!data.session) {
    document.getElementById("authStatus").textContent =
      "Account created. Check your email to confirm your address, then sign in.";
    return;
  }

  await refreshAuthUI();
  await fetchSavedExams();
  render();
}

async function signOut() {
  const supabase = getSupabase();
  if (!supabase) return;

  await supabase.auth.signOut();
  currentUser = null;
  savedRecords = [];
  await refreshAuthUI();
  render();
}

function getSavedIds() {
  return savedRecords.map(record => record.exam?.id).filter(Boolean);
}

function getSavedRecord(examId) {
  return savedRecords.find(
    record => Number(record.exam?.id) === Number(examId)
  );
}

async function fetchSavedExams() {
  if (!currentUser?.id) {
    savedRecords = [];
    return;
  }

  try {
    const res = await fetch(
      `${API_BASE_URL}/saved-exams/user/${currentUser.id}`,
      { headers: getAuthHeaders() }
    );

    if (!res.ok) {
      throw new Error("Could not load saved exams");
    }

    savedRecords = await res.json();
  } catch (err) {
    console.error("Could not load saved exams:", err);
    savedRecords = [];
  }
}

async function saveExam(examId) {
  if (!currentUser?.id) {
    document.getElementById("authStatus").textContent =
      "Please sign in before saving an exam.";
    document.getElementById("authFields").hidden = false;
    return false;
  }

  try {
    const res = await fetch(`${API_BASE_URL}/saved-exams/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders()
      },
      body: JSON.stringify({
        user_id: currentUser.id,
        exam_id: examId
      })
    });

    if (!res.ok) {
      throw new Error("Could not save exam");
    }

    const savedRecord = await res.json();

    savedRecords.push(savedRecord);

    return true;
  } catch (err) {
    console.error("Could not save exam:", err);
    return false;
  }
}

async function unsaveExam(examId) {
  if (!currentUser?.id) return false;

  const savedRecord = getSavedRecord(examId);

  if (!savedRecord) {
    return false;
  }

  try {
    const res = await fetch(
      `${API_BASE_URL}/saved-exams/${savedRecord.id}`,
      {
        method: "DELETE",
        headers: getAuthHeaders()
      }
    );

    if (!res.ok) {
      throw new Error("Could not unsave exam");
    }

    savedRecords = savedRecords.filter(
      record => record.id !== savedRecord.id
    );

    return true;
  } catch (err) {
    console.error("Could not unsave exam:", err);
    return false;
  }
}

async function toggleSaved(examId) {
  if (!currentUser?.id) {
    document.getElementById("authStatus").textContent =
      "Please sign in before saving an exam.";
    document.getElementById("authFields").hidden = false;
    document.getElementById("authEmail").focus();
    return false;
  }

  const isSaved = getSavedIds().includes(examId);

  if (isSaved) {
    return await unsaveExam(examId);
  }

  return await saveExam(examId);
}

async function fetchExams() {
  const state = document.getElementById("stateFilter").value;
  const category = document.getElementById("categoryFilter").value;

  const params = new URLSearchParams();

  if (state) params.set("state", state);
  if (category) params.set("category", category);

  try {
    const res = await fetch(
      `${API_BASE_URL}/exams/?${params.toString()}`
    );

    if (!res.ok) {
      throw new Error("Request failed");
    }

    allExams = await res.json();

    if (currentUser?.id) {
      await fetchSavedExams();
    } else {
      savedRecords = [];
    }

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

  return Math.ceil(
    diff / (1000 * 60 * 60 * 24)
  );
}

function formatDate(dateStr) {
  if (!dateStr) return "—";

  return new Date(dateStr).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric"
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
    list = list.filter(exam => {
      const days = daysUntil(
        exam.application_end_date
      );

      return (
        days !== null &&
        days >= 0 &&
        days <= 7
      );
    });

  } else if (activeTab === "saved") {

    /*
     * Saved exams come directly from backend.
     * Each saved record contains:
     * {
     *   id,
     *   exam: {...},
     *   saved_at
     * }
     */

    list = savedRecords
      .map(record => record.exam)
      .filter(Boolean);
  }

  if (list.length === 0) {
    const messages = {
      all: [
        "No notices yet",
        "Verified exam notifications will appear here as soon as they're added."
      ],

      closing: [
        "Nothing closing soon",
        "No application deadlines in the next 7 days right now."
      ],

      saved: [
        "No saved exams",
        "Tap Save on a notice to track it here."
      ]
    };

    showEmptyState(
      ...messages[activeTab]
    );

    return;
  }

  list.forEach(exam => {

    const node =
      cardTemplate.content.cloneNode(true);

    const card =
      node.querySelector(".notice-card");

    node.querySelector(".notice-org").textContent =
      exam.organization;

    node.querySelector(".notice-title").textContent =
      exam.title;

    node.querySelector(".notice-state").textContent =
      exam.state || "All India";

    node.querySelector(".notice-category").textContent =
      exam.category || "General";

    node.querySelector(".deadline-date").textContent =
      formatDate(exam.application_end_date);

    const days =
      daysUntil(exam.application_end_date);

    const countdownEl =
      node.querySelector(".countdown");

    const numEl =
      node.querySelector(".countdown-num");

    if (days === null) {

      numEl.textContent = "—";

      node.querySelector(".countdown-unit")
        .textContent = "no deadline";

    } else if (days < 0) {

      numEl.textContent = "Closed";

      node.querySelector(".countdown-unit")
        .textContent = "";

    } else {

      numEl.textContent = days;

      if (days > 7) {
        countdownEl.classList.add("is-calm");
      }
    }

    const pdfBtn =
      node.querySelector(".btn-pdf");

    if (exam.official_pdf_url) {

      pdfBtn.href =
        exam.official_pdf_url;

    } else {

      pdfBtn.style.display = "none";
    }

    const saveBtn =
      node.querySelector(".btn-save");

    const saveLabel =
      node.querySelector(".save-label");

    const isSaved =
      savedIds.includes(exam.id);

    if (isSaved) {

      saveBtn.classList.add("is-saved");

      saveLabel.textContent =
        "Saved";
    }

    saveBtn.addEventListener(
      "click",
      async () => {

        saveBtn.disabled = true;

        const currentlySaved =
          getSavedIds().includes(exam.id);

        let success;

        if (currentlySaved) {

          success =
            await unsaveExam(exam.id);

        } else {

          success =
            await saveExam(exam.id);
        }

        saveBtn.disabled = false;

        if (!success) {
          return;
        }

        const nowSaved =
          getSavedIds().includes(exam.id);

        saveBtn.classList.toggle(
          "is-saved",
          nowSaved
        );

        saveLabel.textContent =
          nowSaved ? "Saved" : "Save";

        if (
          activeTab === "saved" &&
          !nowSaved
        ) {
          render();
        }
      }
    );

    board.appendChild(node);
  });
}

function setActiveTab(tabName) {

  activeTab = tabName;

  document
    .querySelectorAll(".tab, .bnav-item")
    .forEach(el => {

      el.classList.toggle(
        "is-active",
        el.dataset.tab === tabName
      );
    });

  render();
}

document
  .querySelectorAll(".tab, .bnav-item")
  .forEach(el => {

    el.addEventListener(
      "click",
      async () => {

        const tab =
          el.dataset.tab;

        if (tab === "saved" && currentUser?.id) {
          await fetchSavedExams();
        }

        setActiveTab(tab);
      }
    );
  });

const filterToggle =
  document.getElementById("filterToggle");

const filterPanel =
  document.getElementById("filterPanel");

filterToggle.addEventListener(
  "click",
  () => {

    filterPanel.hidden =
      !filterPanel.hidden;
  }
);

document
  .getElementById("stateFilter")
  .addEventListener(
    "change",
    fetchExams
  );

document
  .getElementById("categoryFilter")
  .addEventListener(
    "change",
    fetchExams
  );

document.getElementById("loginBtn").addEventListener("click", signIn);
document.getElementById("signupBtn").addEventListener("click", signUp);
document.getElementById("logoutBtn").addEventListener("click", signOut);

(async function initAuth() {
  const supabase = getSupabase();

  if (supabase) {
    supabase.auth.onAuthStateChange(async () => {
      await refreshAuthUI();
      await fetchExams();
    });
  }

  await refreshAuthUI();
  await fetchExams();
})();

if ("serviceWorker" in navigator) {

  window.addEventListener(
    "load",
    () => {

      navigator.serviceWorker
        .register("service-worker.js")
        .catch(() => {});
    }
  );
      }
