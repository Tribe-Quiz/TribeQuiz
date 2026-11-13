let cultures = [];
let questions = [];
const grid = document.querySelector("#culture-grid");
const howtoModal = document.querySelector("#howto-modal");
const quizModal = document.querySelector("#quiz-modal");
const toast = document.querySelector("#toast");
const menuToggle = document.querySelector("#menu-toggle");
const nav = document.querySelector("#main-nav");
let currentCulture = null;
let currentAttemptId = null;
let questionIndex = 0;
let score = 0;
let selectedAnswer = null;
let answerSubmitted = false;
let toastTimer;


async function loadQuizData() {
  try {
    const response = await fetch("/api/quiz");
    if (!response.ok) throw new Error("Quiz data request failed");
    ({ cultures, questions } = await response.json());
    cultures.forEach((culture, index) => {
      const card = document.createElement("article");
      card.className = "culture-card";
      card.style.setProperty("--culture-image", `url("${culture.image}")`);
      card.style.animationDelay = `${Math.min(index * 45, 360)}ms`;
      card.innerHTML = `<div class="culture-card-content"><span class="culture-index">CULTURE ${String(index + 1).padStart(2, "0")}</span><h3>${culture.name}</h3><p>${culture.language} <span aria-hidden="true">·</span> ${culture.region}</p><button class="culture-play" type="button" aria-label="Play ${culture.name} quiz">Begin the quiz <span aria-hidden="true">›</span></button></div>`;
      card.querySelector("button").addEventListener("click", () => startQuiz(culture));
      grid.append(card);
    });
  } catch {
    grid.innerHTML = '<p role="alert">The quiz could not load. Please refresh and try again.</p>';
  }
}

loadQuizData();

document.querySelectorAll("[data-open-howto]").forEach((button) => button.addEventListener("click", () => howtoModal.showModal()));
document.querySelectorAll("[data-close-dialog]").forEach((button) => button.addEventListener("click", () => howtoModal.close()));
document.querySelector("[data-exit-quiz]").addEventListener("click", () => quizModal.close());
howtoModal.addEventListener("click", (event) => closeOnBackdrop(event, howtoModal));
quizModal.addEventListener("click", (event) => closeOnBackdrop(event, quizModal));

menuToggle.addEventListener("click", () => {
  const isExpanded = menuToggle.getAttribute("aria-expanded") === "true";
  menuToggle.setAttribute("aria-expanded", String(!isExpanded));
  menuToggle.setAttribute("aria-label", isExpanded ? "Open menu" : "Close menu");
  nav.classList.toggle("is-open", !isExpanded);
});
nav.addEventListener("click", (event) => {
  if (event.target.closest("a")) {
    menuToggle.setAttribute("aria-expanded", "false");
    nav.classList.remove("is-open");
  }
});

function closeOnBackdrop(event, dialog) {
  if (event.target === dialog) dialog.close();
}

async function startQuiz(culture) {
  try {
    const response = await fetch("/api/attempts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ culture_id: culture.id })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Could not start the quiz.");
    currentAttemptId = payload.attempt_id;
  } catch (error) {
    showToast(error.message || "Could not connect to the quiz server.");
    return;
  }
  currentCulture = culture;
  questionIndex = 0;
  score = 0;
  document.querySelector("#quiz-culture").textContent = `${culture.name} · ${culture.language}`;
  document.querySelector("#result-view").hidden = true;
  document.querySelector("#question-view").hidden = false;
  renderQuestion();
  quizModal.showModal();
}

function renderQuestion() {
  selectedAnswer = null;
  answerSubmitted = false;
  const question = questions[questionIndex];
  const progress = ((questionIndex + 1) / questions.length) * 100;
  document.querySelector("#question-count").textContent = `Question ${questionIndex + 1} of ${questions.length}`;
  document.querySelector("#progress-percent").textContent = `${Math.round(progress)}%`;
  document.querySelector("#progress-fill").style.width = `${progress}%`;
  document.querySelector("#quiz-score").textContent = `${score} ${score === 1 ? "point" : "points"}`;
  document.querySelector("#quiz-title").textContent = question.prompt;
  document.querySelector("#quiz-feedback").textContent = "";
  document.querySelector("#quiz-feedback").className = "quiz-feedback";
  const answerList = document.querySelector("#answer-list");
  answerList.replaceChildren();
  question.options.forEach((option, index) => {
    const button = document.createElement("button");
    button.className = "answer-option";
    button.type = "button";
    button.textContent = `${String.fromCharCode(65 + index)}.  ${option}`;
    button.addEventListener("click", () => selectAnswer(index));
    answerList.append(button);
  });
  const nextButton = document.querySelector("#quiz-next");
  nextButton.disabled = true;
  nextButton.textContent = "Lock in answer  ›";
  nextButton.onclick = null;
}

function selectAnswer(index) {
  selectedAnswer = index;
  document.querySelectorAll(".answer-option").forEach((button, optionIndex) => {
    button.classList.toggle("selected", optionIndex === index);
  });
  document.querySelector("#quiz-next").disabled = false;
}

document.querySelector("#quiz-next").addEventListener("click", async () => {
  if (answerSubmitted) {
    advanceQuestion();
    return;
  }
  if (selectedAnswer === null) return;
  const question = questions[questionIndex];
  const buttons = [...document.querySelectorAll(".answer-option")];
  const feedback = document.querySelector("#quiz-feedback");
  const nextButton = document.querySelector("#quiz-next");
  nextButton.disabled = true;
  nextButton.textContent = "Checking answer...";
  buttons.forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch(`/api/attempts/${currentAttemptId}/answers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question_id: question.id, selected_index: selectedAnswer })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Could not submit your answer.");
    answerSubmitted = true;
    score = payload.score;
    buttons.forEach((button, index) => {
      if (index === payload.correct_index) button.classList.add("correct");
      else if (index === selectedAnswer) button.classList.add("incorrect");
    });
    feedback.textContent = payload.correct ? `Correct. ${payload.note}` : `Not quite. ${payload.note}`;
    feedback.classList.add(payload.correct ? "is-correct" : "is-wrong");
    document.querySelector("#quiz-score").textContent = `${score} points`;
    nextButton.disabled = false;
    nextButton.textContent = questionIndex === questions.length - 1 ? "See your result  ›" : "Next question  ›";
  } catch (error) {
    buttons.forEach((button) => { button.disabled = false; });
    nextButton.disabled = false;
    nextButton.textContent = "Try answer again  ›";
    showToast(error.message || "Could not connect to the quiz server.");
  }
});

function advanceQuestion() {
  if (questionIndex < questions.length - 1) {
    questionIndex += 1;
    renderQuestion();
    return;
  }
  showResults();
}

function showResults() {
  document.querySelector("#question-view").hidden = true;
  document.querySelector("#result-view").hidden = false;
  const result = document.querySelector("#result-view");
  const correctCount = score / 10;
  const message = correctCount >= 8 ? "A brilliant round. Your curiosity is a strength." : correctCount >= 5 ? "A strong start. Every answer adds to the story." : "Every journey begins with a question. Keep exploring.";
  result.innerHTML = `<div class="result-mark" aria-hidden="true">✦</div><p class="eyebrow eyebrow-gold">Round complete · ${currentCulture.name}</p><h2>Your result</h2><p class="result-score">${score} / 100 points</p><p>${correctCount} of 10 correct.<br>${message}</p><div class="result-actions"><button class="button button-primary" id="play-again" type="button">Play this culture again <span>›</span></button><button class="button button-secondary" id="choose-culture" type="button">Choose another culture</button></div>`;
  result.querySelector("#play-again").addEventListener("click", () => startQuiz(currentCulture));
  result.querySelector("#choose-culture").addEventListener("click", () => {
    quizModal.close();
    document.querySelector("#cultures").scrollIntoView({ behavior: "smooth" });
  });
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2800);
}
