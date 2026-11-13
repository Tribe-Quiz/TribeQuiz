async function request(path, options = {}) {
  const { body, headers, ...requestOptions } = options;
  const response = await fetch(`/api${path}`, {
    ...requestOptions,
    headers: body === undefined ? headers : { ...headers, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const payload = await response.json();
  if (!response.ok) {
    const message = typeof payload.detail === "string" ? payload.detail : `Request failed (${response.status}).`;
    throw new Error(message);
  }
  return payload;
}

export function getQuiz() {
  return request("/quiz");
}

export function startAttempt(cultureId) {
  return request("/attempts", { method: "POST", body: { culture_id: cultureId } });
}

export function submitAnswer(attemptId, questionId, selectedIndex) {
  return request(`/attempts/${encodeURIComponent(attemptId)}/answers`, {
    method: "POST",
    body: { question_id: questionId, selected_index: selectedIndex }
  });
}

export function signIn(email, password) {
  return request("/auth/signin", { method: "POST", body: { email, password } });
}

export function signUp(name, email, password) {
  return request("/auth/signup", { method: "POST", body: { name, email, password } });
}

export function verifyEmail(token) {
  return request("/auth/verify-email", { method: "POST", body: { token } });
}

export function getGoogleAuthConfig() {
  return request("/auth/google/config");
}

export function signInWithGoogle(credential, nonce) {
  return request("/auth/google", { method: "POST", body: { credential, nonce } });
}

export function requestPasswordReset(email) {
  return request("/auth/forgot-password", { method: "POST", body: { email } });
}

export function resetPassword(token, password) {
  return request("/auth/reset-password", { method: "POST", body: { token, password } });
}
