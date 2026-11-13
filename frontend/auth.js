const form = document.querySelector("#auth-form");
const signinTab = document.querySelector("#signin-tab");
const signupTab = document.querySelector("#signup-tab");
const nameField = document.querySelector("#name-field");
const confirmField = document.querySelector("#confirm-field");
const authTitle = document.querySelector("#auth-title");
const authSubmit = document.querySelector("#auth-submit");
const authSwitch = document.querySelector("#auth-switch");
const errorMessage = document.querySelector("#auth-error");
let activeTab = new URLSearchParams(location.search).get("tab") === "signup" ? "signup" : "signin";

function setTab(tab) {
  activeTab = tab;
  const isSignup = tab === "signup";
  signinTab.setAttribute("aria-selected", String(!isSignup));
  signupTab.setAttribute("aria-selected", String(isSignup));
  nameField.hidden = !isSignup;
  confirmField.hidden = !isSignup;
  document.querySelector("#password").autocomplete = isSignup ? "new-password" : "current-password";
  authTitle.textContent = isSignup ? "Tribe Quiz" : "Welcome back";
  authSubmit.innerHTML = isSignup ? "Create account <span>›</span>" : "Sign in <span>›</span>";
  authSwitch.innerHTML = isSignup ? 'Already have an account? <button type="button" data-switch>Sign In</button>' : 'New to Tribe Quiz? <button type="button" data-switch>Create an account</button>';
  errorMessage.textContent = "";
  errorMessage.classList.remove("is-success");
  history.replaceState(null, "", isSignup ? "?tab=signup" : "?tab=signin");
  authSwitch.querySelector("[data-switch]").addEventListener("click", () => setTab(isSignup ? "signin" : "signup"));
}

signinTab.addEventListener("click", () => setTab("signin"));
signupTab.addEventListener("click", () => setTab("signup"));
authSwitch.querySelector("[data-switch]").addEventListener("click", () => setTab(activeTab === "signup" ? "signin" : "signup"));

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const email = document.querySelector("#email").value.trim();
  const password = document.querySelector("#password").value;
  const name = document.querySelector("#display-name").value.trim();
  if (!email || !document.querySelector("#email").validity.valid) {
    errorMessage.textContent = "Enter a valid email address.";
    return;
  }
  if (password.length < 8) {
    errorMessage.textContent = "Your password must be at least 8 characters.";
    return;
  }
  if (activeTab === "signup") {
    if (!name) {
      errorMessage.textContent = "Add a display name to create your account.";
      return;
    }
    if (password !== document.querySelector("#confirm-password").value) {
      errorMessage.textContent = "Those passwords do not match.";
      return;
    }
  }
  const isSignup = activeTab === "signup";
  const payload = isSignup ? { name, email, password } : { email, password };
  authSubmit.disabled = true;
  errorMessage.classList.remove("is-success");
  try {
    const response = await fetch(isSignup ? "/api/auth/signup" : "/api/auth/signin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Account request failed.");
    errorMessage.textContent = isSignup
      ? "Your account is ready. You can now explore the quiz."
      : `Welcome back, ${result.user.name}. Your quiz is ready.`;
    errorMessage.classList.add("is-success");
  } catch (error) {
    errorMessage.textContent = error.message || "Could not connect to the account server.";
  } finally {
    authSubmit.disabled = false;
  }
});

document.querySelector("#google-button").addEventListener("click", () => {
  errorMessage.textContent = "Google sign-in is not connected in this local version.";
});
setTab(activeTab);