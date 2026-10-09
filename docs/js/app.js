const API_BASE_URL = "https://exampilotai.onrender.com";

const board = document.getElementById("board");
const loadingState = document.getElementById("loadingState");
const emptyTemplate = document.getElementById("emptyStateTemplate");
const cardTemplate = document.getElementById("examCardTemplate");

let allExams = [];
let savedRecords = [];
let reminderRecords = [];
let activeTab = "all";
let reminderExam = null;
let currentUser = null;

function getSupabase() {
  return window.examPilotSupabase;
}

function getAuthHeaders() {
  return currentUser?.access_token
    ? { Authorization: `Bearer ${currentUser.access_token}` }
    : {};
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map(char => char.charCodeAt(0)));
}

async function updatePushButtonState() {
  const button = document.getElementById("enableNotificationsBtn");
  if (!button) return;
  if (!currentUser?.id || !("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
    button.hidden = true;
    return;
  }
  button.hidden = false;
  if (Notification.permission === "denied") {
    button.textContent = "Notifications blocked";
    button.disabled = true;
    return;
  }
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    button.textContent = subscription ? "Notifications enabled" : "Enable notifications";
    button.disabled = !!subscription;
  } catch (err) {
    console.error("Could not check push subscription:", err);
    button.textContent = "Enable notifications";
    button.disabled = false;
  }
}

async function enablePushNotifications() {
  const button = document.getElementById("enableNotificationsBtn");
  const status = document.getElementById("authStatus");
  if (!currentUser?.id) {
    status.textContent = "Please sign in before enabling notifications.";
    return;
  }
  if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
    status.textContent = "Push notifications are not supported by this browser.";
    return;
  }
  button.disabled = true;
  button.textContent = "Enabling…";
  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      status.textContent = permission === "denied"
        ? "Notifications are blocked for this site. Allow them in browser settings."
        : "Notification permission was not granted.";
      await updatePushButtonState();
      return;
    }
    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      const keyResponse = await fetch(API_BASE_URL + "/push-subscriptions/public-key");
      if (!keyResponse.ok) throw new Error("Push notifications are not configured on the server.");
      const { public_key } = await keyResponse.json();
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      });
    }
    const saveResponse = await fetch(API_BASE_URL + "/push-subscriptions/", {
      method: "POST",
      headers: {"Content-Type": "application/json", ...getAuthHeaders()},
      body: JSON.stringify({endpoint: subscription.endpoint, subscription: subscription.toJSON()}),
    });
    if (!saveResponse.ok) throw new Error("Could not register this device for notifications.");
    status.textContent = "Notifications enabled on this device.";
    await updatePushButtonState();
  } catch (err) {
    console.error("Could not enable push notifications:", err);
    status.textContent = err.message || "Could not enable notifications.";
    button.disabled = false;
    button.textContent = "Enable notifications";
  }
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

  const res = await fetch(`${API_BASE_URL}/users/me`, {
    headers: getAuthHeaders(),
  });

  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = body.detail ? `: ${body.detail}` : "";
    } catch (_) {}
    throw new Error(`Could not load your ExamPilotAI profile${detail}`);
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
    await updatePushButtonState();
    return;
  }

  try {
    await ensureBackendUser();
    title.textContent = session.user.email || "Signed in";
    status.textContent = "Your saved exams are linked to your account.";
    fields.hidden = true;
    logoutBtn.hidden = false;
    await updatePushButtonState();
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

async function requestPasswordReset() {
  const supabase = getSupabase();
  if (!supabase) return;

  const email = document.getElementById("authEmail").value.trim();
  const status = document.getElementById("authStatus");

  if (!email) {
    status.textContent = "Enter your email address first.";
    document.getElementById("authEmail").focus();
    return;
  }

  status.textContent = "Sending password reset email…";

  const redirectTo = window.location.origin + window.location.pathname;
  const { error } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo
  });

  if (error) {
    status.textContent = error.message;
    return;
  }

  status.textContent = "Password reset email sent. Check your inbox.";
}

function showPasswordResetPanel() {
  const panel = document.getElementById("passwordResetPanel");
  const fields = document.getElementById("authFields");
  const logoutBtn = document.getElementById("logoutBtn");

  if (panel) panel.hidden = false;
  if (fields) fields.hidden = true;
  if (logoutBtn) logoutBtn.hidden = true;
  document.getElementById("authTitle").textContent = "Reset your password";
  document.getElementById("authStatus").textContent =
    "Enter and confirm your new password.";
}

async function updatePassword() {
  const supabase = getSupabase();
  const password = document.getElementById("newPassword").value;
  const confirm = document.getElementById("newPasswordConfirm").value;
  const status = document.getElementById("authStatus");

  if (!password || password.length < 6) {
    status.textContent = "Password must be at least 6 characters.";
    return;
  }

  if (password !== confirm) {
    status.textContent = "Passwords do not match.";
    return;
  }

  status.textContent = "Updating password…";
  const { error } = await supabase.auth.updateUser({ password });

  if (error) {
    status.textContent = error.message;
    return;
  }

  document.getElementById("newPassword").value = "";
  document.getElementById("newPasswordConfirm").value = "";
  document.getElementById("passwordResetPanel").hidden = true;
  window.history.replaceState({}, document.title, window.location.pathname);
  await supabase.auth.signOut();
  currentUser = null;
  document.getElementById("authFields").hidden = false;
  document.getElementById("logoutBtn").hidden = true;
  document.getElementById("authTitle").textContent = "Sign in to ExamPilotAI";
  status.textContent = "Password updated successfully. You can now sign in.";
}

function cancelPasswordReset() {
  const panel = document.getElementById("passwordResetPanel");
  if (panel) panel.hidden = true;
  window.history.replaceState({}, document.title, window.location.pathname);
  document.getElementById("authFields").hidden = false;
  document.getElementById("authTitle").textContent = "Sign in to ExamPilotAI";
  document.getElementById("authStatus").textContent =
    "Sign in to save exams to your account.";
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


function getReminderStorageKey() {
  return currentUser?.id ? `exampilotai:reminders:${currentUser.id}` : null;
}

function loadCachedReminders() {
  const key = getReminderStorageKey();
  if (!key) return [];
  try {
    const cached = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(cached) ? cached : [];
  } catch (_) {
    return [];
  }
}

function cacheReminders() {
  const key = getReminderStorageKey();
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(reminderRecords));
  } catch (_) {}
}

async function fetchReminders() {
  if (!currentUser?.id) {
    reminderRecords = [];
    return;
  }

  // Show the last known reminder immediately while the API request runs.
  reminderRecords = loadCachedReminders();

  try {
    let res = await fetch(
      `${API_BASE_URL}/reminders/user/${currentUser.id}`,
      { headers: getAuthHeaders() }
    );

    // Retry once with the latest Supabase access token if the first request
    // is rejected during a session refresh.
    if (res.status === 401) {
      const session = await window.getExamPilotSession();
      if (session?.user && session.access_token) {
        currentUser.access_token = session.access_token;
        res = await fetch(
          `${API_BASE_URL}/reminders/user/${currentUser.id}`,
          { headers: getAuthHeaders() }
        );
      }
    }

    if (!res.ok) {
      throw new Error("Could not load reminders (HTTP " + res.status + ")");
    }

    const records = await res.json();
    reminderRecords = Array.isArray(records) ? records : [];
    cacheReminders();
  } catch (err) {
    console.error("Could not load reminders:", err);
    // Keep already-loaded reminders during a temporary background failure.
  }
}

function getReminderForExam(examId) {
  return reminderRecords.find(
    record => Number(record.exam_id) === Number(examId)
  );
}

function toISTDateTimeInput(date) {
  const d = new Date(date);
  if (Number.isNaN(d.getTime())) return "";

  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).formatToParts(d);

  const values = Object.fromEntries(
    parts
      .filter(part => part.type !== "literal")
      .map(part => [part.type, part.value])
  );

  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`;
}

function parseISTDateTimeInput(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return new Date(NaN);

  const [, year, month, day, hour, minute] = match;
  const utcMillis = Date.UTC(
    Number(year),
    Number(month) - 1,
    Number(day),
    Number(hour),
    Number(minute)
  ) - (5 * 60 + 30) * 60 * 1000;

  return new Date(utcMillis);
}

function getDefaultReminderTime() {
  // Default to one minute from now, expressed explicitly in IST.
  // This keeps the form aligned with Indian Standard Time even if the
  // device/browser timezone is configured differently.
  return new Date(Date.now() + 60 * 1000);
}

function openReminderModal(exam) {
  if (!currentUser?.id) {
    document.getElementById("authStatus").textContent =
      "Please sign in before setting a reminder.";
    document.getElementById("authFields").hidden = false;
    document.getElementById("authEmail").focus();
    return;
  }

  reminderExam = exam;
  const modal = document.getElementById("reminderModal");

  document.getElementById("reminderExamTitle").textContent = exam.title;
  document.getElementById("reminderType").value = "application_deadline";
  document.getElementById("reminderAt").value =
    toISTDateTimeInput(getDefaultReminderTime());
  const existingCount = reminderRecords.filter(
    record => Number(record.exam_id) === Number(exam.id) && !record.is_sent
  ).length;
  document.getElementById("reminderStatus").textContent =
    existingCount ? `${existingCount} reminder(s) already set. This will add another.` : "";

  modal.hidden = false;
}

function closeReminderModal() {
  document.getElementById("reminderModal").hidden = true;
  document.getElementById("reminderStatus").textContent = "";
  reminderExam = null;
}

async function saveReminder() {
  if (!currentUser?.id || !reminderExam) return;

  const type = document.getElementById("reminderType").value;
  const input = document.getElementById("reminderAt").value;
  const status = document.getElementById("reminderStatus");

  if (!input) {
    status.textContent = "Choose a reminder date and time.";
    return;
  }

  const remindAt = parseISTDateTimeInput(input);
  if (Number.isNaN(remindAt.getTime()) || remindAt.getTime() <= Date.now()) {
    status.textContent = "Choose a future date and time.";
    return;
  }

  status.textContent = "Saving reminder…";

  const res = await fetch(`${API_BASE_URL}/reminders/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders()
    },
    body: JSON.stringify({
      user_id: currentUser.id,
      exam_id: reminderExam.id,
      reminder_type: type,
      remind_at: remindAt.toISOString()
    })
  });

  if (!res.ok) {
    let detail = "Could not save reminder.";
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch (_) {}
    status.textContent = detail;
    return;
  }

  const record = await res.json();
  reminderRecords.push(record);
  cacheReminders();
  closeReminderModal();
  render();
}


async function createAutomaticDeadlineReminders(exam) {
  if (!currentUser?.id) {
    document.getElementById("authStatus").textContent = "Please sign in before setting reminders.";
    return;
  }
  const status = document.getElementById("authStatus");
  status.textContent = "Creating automatic deadline reminders…";
  try {
    const response = await fetch(
      `${API_BASE_URL}/reminders/automatic/${exam.id}`,
      { method: "POST", headers: getAuthHeaders() }
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Could not create automatic reminders.");
    await fetchReminders();
    render();
    const created = body.created?.length || 0;
    status.textContent = created
      ? `Created ${created} automatic reminder(s) for ${exam.title}. Reminders are scheduled for 9:00 AM IST.`
      : (body.message || "No new future reminders were needed.");
  } catch (err) {
    status.textContent = err.message || "Could not create automatic reminders.";
  }
}


async function createAutomaticExamDayReminders(exam) {
  if (!currentUser?.id) {
    document.getElementById("authStatus").textContent = "Please sign in before setting reminders.";
    return;
  }
  const status = document.getElementById("authStatus");
  status.textContent = "Creating exam-day reminders…";
  try {
    const response = await fetch(
      `${API_BASE_URL}/reminders/automatic-exam/${exam.id}`,
      { method: "POST", headers: getAuthHeaders() }
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Could not create exam-day reminders.");
    await fetchReminders();
    render();
    status.textContent = body.created?.length
      ? `Created ${body.created.length} exam-day reminder(s) for ${exam.title}.`
      : (body.message || "No new future exam-day reminders were needed.");
  } catch (err) {
    status.textContent = err.message || "Could not create exam-day reminders.";
  }
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
      await fetchReminders();
    } else {
      savedRecords = [];
      reminderRecords = [];
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

    const reminderBtn =
      node.querySelector(".btn-reminder");

    const existingReminders = reminderRecords.filter(
      record => Number(record.exam_id) === Number(exam.id) && !record.is_sent
    );
    if (existingReminders.length) {
      reminderBtn.textContent = `Reminders (${existingReminders.length})`;
      reminderBtn.classList.add("is-set");
    }

    reminderBtn.addEventListener("click", () => openReminderModal(exam));
    const automaticBtn = node.querySelector(".btn-auto-reminder");
    if (automaticBtn) {
      automaticBtn.addEventListener("click", () => createAutomaticDeadlineReminders(exam));
    }
    const examDayBtn = node.querySelector(".btn-exam-reminder");
    if (examDayBtn) {
      examDayBtn.addEventListener("click", () => createAutomaticExamDayReminders(exam));
    }

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
document.getElementById("forgotPasswordBtn").addEventListener("click", requestPasswordReset);
document.getElementById("updatePasswordBtn").addEventListener("click", updatePassword);
document.getElementById("cancelPasswordResetBtn").addEventListener("click", cancelPasswordReset);
document.getElementById("saveReminderBtn").addEventListener("click", saveReminder);
document.getElementById("cancelReminderBtn").addEventListener("click", closeReminderModal);
document.getElementById("reminderCloseBtn").addEventListener("click", closeReminderModal);
document.getElementById("enableNotificationsBtn")?.addEventListener("click", enablePushNotifications);

(async function initAuth() {
  const supabase = getSupabase();

  if (supabase && new URLSearchParams(window.location.hash.substring(1)).get("type") === "recovery") {
    showPasswordResetPanel();
  }

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
        .then(() => updatePushButtonState())
        .catch((err) => console.error("Service worker registration failed:", err));
    }
  );
      }
