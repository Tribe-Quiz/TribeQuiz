import { getCurrentUser, getGoogleAuthConfig, signIn, signInWithGoogle, signUp } from "./api.js";

const form = document.querySelector("#auth-form");
const signinTab = document.querySelector("#signin-tab");
const signupTab = document.querySelector("#signup-tab");
const nameField = document.querySelector("#name-field");
const confirmField = document.querySelector("#confirm-field");
const authTitle = document.querySelector("#auth-title");
const authSubmit = document.querySelector("#auth-submit");
const authSwitch = document.querySelector("#auth-switch");
const errorMessage = document.querySelector("#auth-error");
const googleButton = document.querySelector("#google-button");
const forgotPasswordLink = document.querySelector("#forgot-password-link");
document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  const input = document.getElementById(button.getAttribute("aria-controls"));
  button.addEventListener("click", () => {
    const showPassword = input.type === "password";
    input.type = showPassword ? "text" : "password";
    button.textContent = showPassword ? "Hide" : "Show";
    button.setAttribute("aria-label", `${showPassword ? "Hide" : "Show"} password`);
    button.setAttribute("aria-pressed", String(showPassword));
  });
});
const googleNonceBytes = crypto.getRandomValues(new Uint8Array(32));
const googleNonce = Array.from(googleNonceBytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
let activeTab = new URLSearchParams(location.search).get("tab") === "signup" ? "signup" : "signin";

function loadGoogleIdentityServices() {
  return new Promise((resolve, reject) => {
    if (window.google && window.google.accounts && window.google.accounts.id) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error("Google sign-in could not be loaded."));
    document.head.append(script);
  });
}

async function handleGoogleCredential(credential) {
  errorMessage.textContent = "";
  errorMessage.classList.remove("is-success");
  googleButton.setAttribute("aria-busy", "true");
  try {
    const result = await signInWithGoogle(credential, googleNonce);
    errorMessage.textContent = `Welcome, ${result.user.name}. Your Google account is ready.`;
    errorMessage.classList.add("is-success");
    window.setTimeout(() => { window.location.href = "index.html"; }, 700);
  } catch (error) {
    errorMessage.textContent = error.message || "Google sign-in failed. Please try again.";
  } finally {
    googleButton.removeAttribute("aria-busy");
  }
}

async function setupGoogleSignIn() {
  try {
    const config = await getGoogleAuthConfig();
    if (!config.enabled || !config.client_id) {
      googleButton.textContent = "Google sign-in is not configured on this server.";
      googleButton.setAttribute("aria-disabled", "true");
      return;
    }
    await loadGoogleIdentityServices();
    window.google.accounts.id.initialize({
      client_id: config.client_id,
      nonce: googleNonce,
      callback: ({ credential }) => {
        if (credential) handleGoogleCredential(credential);
        else errorMessage.textContent = "Google did not return a sign-in credential.";
      }
    });
    window.google.accounts.id.renderButton(googleButton, {
      type: "standard",
      theme: "outline",
      size: "large",
      text: "continue_with",
      shape: "rectangular",
      width: Math.min(googleButton.clientWidth, 400)
    });
  } catch (error) {
    googleButton.textContent = error.message || "Google sign-in could not be initialized.";
    googleButton.setAttribute("aria-disabled", "true");
  }
}

function setTab(tab) {
  activeTab = tab;
  const isSignup = tab === "signup";
  signinTab.setAttribute("aria-selected", String(!isSignup));
  signupTab.setAttribute("aria-selected", String(isSignup));
  nameField.hidden = !isSignup;
  confirmField.hidden = !isSignup;
  forgotPasswordLink.hidden = isSignup;
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
    const result = isSignup
      ? await signUp(payload.name, payload.email, payload.password)
      : await signIn(payload.email, payload.password);
    errorMessage.textContent = isSignup
      ? result.message
      : `Welcome back, ${result.user.name}. Your quiz is ready.`;
    errorMessage.classList.add("is-success");
    if (!isSignup) window.setTimeout(() => { window.location.href = "index.html"; }, 700);
  } catch (error) {
    errorMessage.textContent = error.message || "Could not connect to the account server.";
  } finally {
    authSubmit.disabled = false;
  }
});

setTab(activeTab);
setupGoogleSignIn();

getCurrentUser().then(() => {
  window.location.replace("index.html");
}).catch((error) => {
  if (error.status !== 401) {
    errorMessage.textContent = error.message || "Could not check your account session.";
  }
});