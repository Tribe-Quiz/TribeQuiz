import { verifyEmail } from "./api.js";

const message = document.querySelector("#verification-message");
const token = new URLSearchParams(location.search).get("token");

if (token) {
  history.replaceState(null, "", location.pathname);
  try {
    const result = await verifyEmail(token);
    message.textContent = `Your email is verified, ${result.user.name}. Your account is ready.`;
    message.classList.add("is-success");
  } catch (error) {
    message.textContent = error.message || "Could not verify your email. Request a new link and try again.";
  }
} else {
  message.textContent = "This verification link is missing or invalid. Sign up again to request a new link.";
}
