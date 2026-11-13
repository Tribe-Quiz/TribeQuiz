import { requestPasswordReset } from "./api.js";

const form = document.querySelector("#forgot-form");
const emailInput = document.querySelector("#forgot-email");
const submitButton = document.querySelector("#forgot-submit");
const message = document.querySelector("#forgot-message");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!emailInput.validity.valid) {
    message.textContent = "Enter a valid email address.";
    return;
  }

  submitButton.disabled = true;
  message.classList.remove("is-success");
  try {
    const result = await requestPasswordReset(emailInput.value.trim());
    message.textContent = result.message;
    message.classList.add("is-success");
  } catch (error) {
    message.textContent = error.message || "Could not request a password reset.";
  } finally {
    submitButton.disabled = false;
  }
});
