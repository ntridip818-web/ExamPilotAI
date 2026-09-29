// Supabase authentication for ExamPilotAI.
// Never put a Supabase secret/service_role key in this file.

const SUPABASE_URL = "https://nuswtpeebtyjdrnoipnp.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_0rSiyxsCogeKapEdP2aqZg_8iAveTp5";
const EXAMPILOT_FRONTEND_URL = "https://exampilotai-frontend-test.onrender.com";

window.examPilotSupabase = null;

if (window.supabase && SUPABASE_PUBLISHABLE_KEY !== "REPLACE_WITH_SUPABASE_PUBLISHABLE_KEY") {
  window.examPilotSupabase = window.supabase.createClient(
    SUPABASE_URL,
    SUPABASE_PUBLISHABLE_KEY
  );
}

window.getExamPilotSession = async function () {
  if (!window.examPilotSupabase) return null;
  const { data, error } = await window.examPilotSupabase.auth.getSession();
  if (error) {
    console.error("Supabase session error:", error);
    return null;
  }
  return data.session;
};

// Always send password-reset emails back to the deployed ExamPilotAI site,
// even if the user previously opened the app on localhost:3000.
if (window.examPilotSupabase) {
  const auth = window.examPilotSupabase.auth;
  const originalResetPasswordForEmail = auth.resetPasswordForEmail.bind(auth);

  auth.resetPasswordForEmail = function (email, options = {}) {
    return originalResetPasswordForEmail(email, {
      ...options,
      redirectTo: EXAMPILOT_FRONTEND_URL
    });
  };
}

function isRecoveryLink() {
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const query = new URLSearchParams(window.location.search);
  return hash.get("type") === "recovery" || query.get("type") === "recovery";
}

function showPasswordResetPanel() {
  const panel = document.getElementById("passwordResetPanel");
  const fields = document.getElementById("authFields");
  const status = document.getElementById("authStatus");
  if (!panel) return;
  if (fields) fields.hidden = true;
  panel.hidden = false;
  if (status) status.textContent = "Choose a new password for your account.";
}

function hidePasswordResetPanel() {
  const panel = document.getElementById("passwordResetPanel");
  const fields = document.getElementById("authFields");
  if (panel) panel.hidden = true;
  if (fields) fields.hidden = false;
}

async function handlePasswordUpdate(event) {
  event.preventDefault();
  event.stopImmediatePropagation();

  const supabase = window.examPilotSupabase;
  const status = document.getElementById("authStatus");
  const password = document.getElementById("newPassword")?.value || "";
  const confirm = document.getElementById("newPasswordConfirm")?.value || "";

  if (password.length < 6) {
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

  await supabase.auth.signOut();
  window.history.replaceState({}, document.title, window.location.pathname);
  hidePasswordResetPanel();
  document.getElementById("newPassword").value = "";
  document.getElementById("newPasswordConfirm").value = "";
  status.textContent = "Password updated successfully. You can now sign in.";
}

function installRecoveryFlow() {
  const updateBtn = document.getElementById("updatePasswordBtn");
  const cancelBtn = document.getElementById("cancelPasswordResetBtn");

  if (updateBtn) {
    updateBtn.addEventListener("click", handlePasswordUpdate, true);
  }
  if (cancelBtn) {
    cancelBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopImmediatePropagation();
      window.examPilotSupabase?.auth.signOut();
      window.history.replaceState({}, document.title, window.location.pathname);
      hidePasswordResetPanel();
    }, true);
  }

  window.examPilotSupabase?.auth.onAuthStateChange((event) => {
    if (event === "PASSWORD_RECOVERY" || isRecoveryLink()) {
      showPasswordResetPanel();
    }
  });

  if (isRecoveryLink()) {
    setTimeout(showPasswordResetPanel, 500);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", installRecoveryFlow);
} else {
  installRecoveryFlow();
}
