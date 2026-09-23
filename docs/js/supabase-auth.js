// Supabase authentication for ExamPilotAI.
// Replace the placeholder below with the project's Publishable key.
// Never put a Supabase secret/service_role key in this file.

const SUPABASE_URL = "https://nuswtpeebtyjdrnoipnp.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "REPLACE_WITH_SUPABASE_PUBLISHABLE_KEY";

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
