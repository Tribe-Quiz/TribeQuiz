import { resetPassword } from "./api.js";

const form = document.querySelector("#reset-form");
const passwordInput = document.querySelector("#new-password");
const confirmInput = document.querySelector("#confirm-new-password");
const submitButton = document.querySelector("#reset-submit");
const message = document.querySelector("#reset-message");
const token = new URLSearchParams(location.search).get("token");

if (token) {
  history.replaceState(null, "", location.pathname);
} else {
  form.hidden = true;
  message.textContent = "This reset link is invalid or has expired. Request a new one.";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!token) return;
  if (passwordInput.value.length < 8) {
    message.textContent = "Your password must be at least 8 characters.";
    return;
  }
  if (passwordInput.value !== confirmInput.value) {
    message.textContent = "Those passwords do not match.";
    return;
  }

  submitButton.disabled = true;
  message.classList.remove("is-success");
  try {
    await resetPassword(token, passwordInput.value);
    form.hidden = true;
    message.textContent = "Your password has been reset. You can now sign in.";
    message.classList.add("is-success");
  } catch (error) {
    message.textContent = error.message || "Could not reset your password.";
  } finally {
    submitButton.disabled = false;
  }
});
