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
  history.replaceState(null, "", isSignup ? "?tab=signup" : "?tab=signin");
  authSwitch.querySelector("[data-switch]").addEventListener("click", () => setTab(isSignup ? "signin" : "signup"));
}

signinTab.addEventListener("click", () => setTab("signin"));
signupTab.addEventListener("click", () => setTab("signup"));
authSwitch.querySelector("[data-switch]").addEventListener("click", () => setTab(activeTab === "signup" ? "signin" : "signup"));

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const email = document.querySelector("#email").value.trim();
  const password = document.querySelector("#password").value;
  const name = document.querySelector("#display-name").value.trim();
  if (!email || !document.querySelector("#email").validity.valid) {
    errorMessage.textContent = "Enter a valid email address.";
    return;
  }
  if (password.length < 6) {
    errorMessage.textContent = "Your password must be at least 6 characters.";
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
    localStorage.setItem("tribeQuizUser", JSON.stringify({ name, email }));
    errorMessage.textContent = "Account details saved on this device. You can now explore the quiz.";
  } else {
    const savedUser = JSON.parse(localStorage.getItem("tribeQuizUser") || "null");
    if (!savedUser || savedUser.email !== email) {
      errorMessage.textContent = "No local account was found for that email. Create an account on this device first.";
      return;
    }
    errorMessage.textContent = `Welcome back, ${savedUser.name}. Your quiz is ready.`;
  }
});

document.querySelector("#google-button").addEventListener("click", () => {
  errorMessage.textContent = "Google sign-in is not connected in this local version.";
});
setTab(activeTab);