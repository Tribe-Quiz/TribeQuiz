import {
  getCurrentUser,
  getAttempt,
  getQuiz,
  getUserAttempts,
  signOut,
  startAttempt,
  submitAnswer
} from "./api.js";

const grid = document.querySelector("#culture-grid");
const howtoModal = document.querySelector("#howto-modal");
const aboutModal = document.querySelector("#about-modal");
const quizModal = document.querySelector("#quiz-modal");
const toast = document.querySelector("#toast");
const menuToggle = document.querySelector("#menu-toggle");
const nav = document.querySelector("#main-nav");
const answerList = document.querySelector("#answer-list");
let cultures = [];
let questions = [];
let activeAttempts = [];
let currentCulture = null;
let currentAttemptId = null;
let currentUser = null;
let questionIndex = 0;
let score = 0;
let selectedAnswer = null;
let answerSubmitted = false;
let answerLog = [];
let timerInterval = null;
let autoAdvanceTimer = null;
let timeLeft = 15;
let toastTimer;

async function loadQuizData() {
  try {
    const quiz = await getQuiz();
    cultures = quiz.cultures;
    await refreshNavigation();
    renderCultureCards();
  } catch {
    grid.innerHTML = '<p role="alert">The quiz could not load. Please refresh and try again.</p>';
  }
}

function renderCultureCards() {
  grid.replaceChildren();
  cultures.forEach((culture, index) => {
    const resumableAttempt = activeAttempts.find((attempt) => attempt.culture_id === culture.id);
    const card = document.createElement("article");
    card.className = "culture-card";
    card.style.animationDelay = `${Math.min(index * 45, 360)}ms`;
    card.innerHTML = `
      <div class="culture-image"><img src="${culture.image}" alt="${culture.name}" loading="lazy"></div>
      <div class="culture-card-content">
        <span class="culture-index">CULTURE ${String(index + 1).padStart(2, "0")}</span>
        <h3>${culture.name}</h3>
        <p>${culture.language} <span aria-hidden="true">·</span> ${culture.region}</p>
        <button class="culture-play" type="button" aria-label="Play ${culture.name} quiz">
          Begin the quiz <span aria-hidden="true">›</span>
        </button>
        ${resumableAttempt ? `
          <button class="culture-resume" type="button">
            Resume quiz · ${resumableAttempt.answered_count}/${resumableAttempt.question_count}
          </button>` : ""}
      </div>`;
    card.querySelector("button").addEventListener("click", () => startQuiz(culture));
    const resumeButton = card.querySelector(".culture-resume");
    if (resumeButton) {
      resumeButton.addEventListener("click", () => startQuiz(culture, resumableAttempt.id));
    }
    grid.append(card);
  });
}

async function refreshNavigation() {
  const authLinks = document.querySelector("#nav-auth-links");
  const userLinks = document.querySelector("#nav-user-links");
  const userName = document.querySelector("#nav-user-name");
  try {
    ({ user: currentUser } = await getCurrentUser());
  } catch (error) {
    if (error.status !== 401) throw error;
    currentUser = null;
  }
  if (currentUser) {
    ({ attempts: activeAttempts } = await getUserAttempts());
    activeAttempts = activeAttempts.filter((attempt) => !attempt.completed_at);
  } else {
    activeAttempts = [];
  }
  authLinks.hidden = Boolean(currentUser);
  userLinks.hidden = !currentUser;
  if (currentUser) userName.textContent = currentUser.name;
}

loadQuizData();

document.querySelectorAll("[data-open-howto]").forEach((button) => {
  button.addEventListener("click", (event) => {
    event.preventDefault();
    howtoModal.showModal();
  });
});
document.querySelectorAll("[data-open-about]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    aboutModal.showModal();
  });
});
document.querySelectorAll("[data-close-dialog]").forEach((button) => {
  button.addEventListener("click", () => howtoModal.close());
});
document.querySelectorAll("[data-close-about]").forEach((button) => {
  button.addEventListener("click", () => aboutModal.close());
});
document.querySelector("[data-exit-quiz]").addEventListener("click", () => {
  clearInterval(timerInterval);
  quizModal.close();
});
howtoModal.addEventListener("click", (event) => closeOnBackdrop(event, howtoModal));
aboutModal.addEventListener("click", (event) => closeOnBackdrop(event, aboutModal));
quizModal.addEventListener("click", (event) => closeOnBackdrop(event, quizModal));
quizModal.addEventListener("close", () => {
  clearInterval(timerInterval);
  clearTimeout(autoAdvanceTimer);
  renderCultureCards();
});

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

document.querySelector("#nav-signout").addEventListener("click", async () => {
  try {
    await signOut();
    currentUser = null;
    await refreshNavigation();
    renderCultureCards();
  } catch (error) {
    showToast(error.message || "Could not sign out.");
  }
});

document.querySelector("#play-now").addEventListener("click", () => {
  if (!currentUser) {
    window.location.href = "auth.html?tab=signup";
    return;
  }
  document.querySelector("#cultures").scrollIntoView({ behavior: "smooth" });
});

function closeOnBackdrop(event, dialog) {
  if (event.target === dialog) dialog.close();
}

async function startQuiz(culture, attemptId = null) {
  if (!currentUser) {
    window.location.href = "auth.html?tab=signup";
    return;
  }
  let payload;
  try {
    payload = attemptId ? await getAttempt(attemptId) : await startAttempt(culture.id);
    if (!Array.isArray(payload.questions) || payload.questions.length !== payload.question_count) {
      throw new Error("The quiz could not load all questions. Please try again.");
    }
    if (payload.answered_count >= payload.question_count) {
      throw new Error("This quiz attempt is already complete.");
    }
    currentAttemptId = payload.attempt_id;
    questions = payload.questions;
    if (!attemptId) {
      activeAttempts.unshift({
        id: currentAttemptId,
        culture_id: culture.id,
        answered_count: 0,
        question_count: payload.question_count
      });
    }
  } catch (error) {
    showToast(error.message || "Could not connect to the quiz server.");
    return;
  }
  currentCulture = culture;
  questionIndex = payload.answered_count || 0;
  score = payload.score || 0;
  answerLog = (payload.answers || []).map((answer, index) => {
    const question = questions[index];
    return {
      prompt: question.prompt,
      selected: answer.selected_index === -1 ? "(no answer - time ran out)" : question.options[answer.selected_index],
      correctAnswer: question.options[answer.correct_index],
      correct: Boolean(answer.correct)
    };
  });
  document.querySelector("#quiz-culture").textContent = `${culture.name} · ${culture.language}`;
  document.querySelector("#result-view").hidden = true;
  document.querySelector("#question-view").hidden = false;
  renderCultureCards();
  renderQuestion();
  if (!quizModal.open) quizModal.showModal();
}

function renderQuestion() {
  clearInterval(timerInterval);
  clearTimeout(autoAdvanceTimer);
  selectedAnswer = null;
  answerSubmitted = false;
  const question = questions[questionIndex];
  const progress = ((questionIndex + 1) / questions.length) * 100;
  document.querySelector("#question-count").textContent = `Question ${questionIndex + 1} of ${questions.length}`;
  document.querySelector("#progress-percent").textContent = `${Math.round(progress)}%`;
  document.querySelector("#progress-fill").style.width = `${progress}%`;
  document.querySelector("#quiz-score").textContent = `${score} ${score === 1 ? "point" : "points"}`;
  document.querySelector("#quiz-category").textContent = question.category;
  document.querySelector("#quiz-title").textContent = question.prompt;
  document.querySelector("#quiz-feedback").textContent = "";
  document.querySelector("#quiz-feedback").className = "quiz-feedback";

  const questionImage = document.querySelector("#question-image");
  const imageCredit = document.querySelector("#question-image-credit");
  const imageSource = document.querySelector("#question-image-source");
  const imageLicense = document.querySelector("#question-image-license");
  if (question.image_url) {
    questionImage.src = question.image_url;
    questionImage.alt = question.image_search_term || `Illustration for ${currentCulture.name}`;
    questionImage.hidden = false;
    const hasImageAttribution = Boolean(
      question.image_credit || question.image_source_url || question.image_license || question.image_license_url,
    );
    imageCredit.hidden = !hasImageAttribution;
    imageLicense.hidden = !hasImageAttribution;
    if (hasImageAttribution) {
      imageSource.href = question.image_source_url || "https://commons.wikimedia.org/";
      imageSource.textContent = `Photo: ${question.image_credit || "Wikimedia Commons"}`;
      imageLicense.href = question.image_license_url || question.image_source_url || "https://commons.wikimedia.org/";
      imageLicense.textContent = question.image_license || "Source and license";
    } else {
      imageSource.removeAttribute("href");
      imageSource.textContent = "";
      imageLicense.removeAttribute("href");
      imageLicense.textContent = "";
    }
    questionImage.onerror = () => {
      questionImage.hidden = true;
      imageCredit.hidden = true;
    };
  } else {
    questionImage.removeAttribute("src");
    questionImage.hidden = true;
    imageSource.removeAttribute("href");
    imageSource.textContent = "";
    imageLicense.removeAttribute("href");
    imageLicense.textContent = "";
    imageLicense.hidden = true;
    imageCredit.hidden = true;
  }

  answerList.replaceChildren();
  question.options.forEach((option, index) => {
    const button = document.createElement("button");
    button.className = "answer-option";
    button.type = "button";
    button.textContent = `${String.fromCharCode(65 + index)}.  ${option}`;
    button.addEventListener("click", () => selectAnswer(index));
    answerList.append(button);
  });
  startTimer();
}

function startTimer() {
  timeLeft = 15;
  updateTimerDisplay();
  timerInterval = setInterval(() => {
    timeLeft = Math.max(0, timeLeft - 0.1);
    updateTimerDisplay();
    if (timeLeft <= 0) {
      clearInterval(timerInterval);
      lockAnswer(-1);
    }
  }, 100);
}

function updateTimerDisplay() {
  const percent = (timeLeft / 15) * 100;
  document.querySelector("#timer-text").textContent = `${Math.ceil(timeLeft)}s`;
  const timerBar = document.querySelector("#timer-fill");
  timerBar.style.width = `${percent}%`;
  timerBar.classList.toggle("timer-warning", percent <= 50 && percent > 20);
  timerBar.classList.toggle("timer-danger", percent <= 20);
}

function selectAnswer(index) {
  if (answerSubmitted) return;
  selectedAnswer = index;
  document.querySelectorAll(".answer-option").forEach((button, optionIndex) => {
    button.classList.toggle("selected", optionIndex === index);
  });
  lockAnswer(index);
}

async function lockAnswer(answerIndex) {
  if (answerSubmitted) return;
  clearInterval(timerInterval);
  selectedAnswer = answerIndex;
  const question = questions[questionIndex];
  const buttons = [...document.querySelectorAll(".answer-option")];
  const feedback = document.querySelector("#quiz-feedback");
  answerSubmitted = true;
  buttons.forEach((button) => { button.disabled = true; });
  try {
    const payload = await submitAnswer(currentAttemptId, question.id, answerIndex);
    score = payload.score;
    buttons.forEach((button, index) => {
      if (index === payload.correct_index) button.classList.add("correct");
      else if (index === answerIndex) button.classList.add("incorrect");
    });
    const correctAnswer = question.options[payload.correct_index];
    const selectedText = answerIndex === -1 ? "(no answer - time ran out)" : question.options[answerIndex];
    answerLog.push({
      prompt: question.prompt,
      selected: selectedText,
      correctAnswer,
      correct: payload.correct
    });
    feedback.textContent = answerIndex === -1
      ? `Time's up. ${payload.note}`
      : payload.correct ? `Correct. ${payload.note}` : `Not quite. ${payload.note}`;
    feedback.classList.add(payload.correct ? "is-correct" : "is-wrong");
    document.querySelector("#quiz-score").textContent = `${score} ${score === 1 ? "point" : "points"}`;
    const activeAttempt = activeAttempts.find((attempt) => attempt.id === currentAttemptId);
    if (activeAttempt) {
      activeAttempt.answered_count = payload.answered_count;
      activeAttempt.score = payload.score;
      if (payload.completed) {
        activeAttempts = activeAttempts.filter((attempt) => attempt.id !== currentAttemptId);
      }
    }
    autoAdvanceTimer = window.setTimeout(
      () => {
        if (answerSubmitted && quizModal.open) advanceQuestion();
      },
      answerIndex === -1 ? 1800 : 1100
    );
  } catch (error) {
    answerSubmitted = false;
    selectedAnswer = null;
    buttons.forEach((button) => { button.disabled = false; });
    buttons.forEach((button) => button.classList.remove("selected"));
    showToast(error.message || "Could not connect to the quiz server.");
  }
}

function advanceQuestion() {
  clearTimeout(autoAdvanceTimer);
  if (questionIndex < questions.length - 1) {
    questionIndex += 1;
    renderQuestion();
    return;
  }
  showResults();
}

function showResults() {
  clearInterval(timerInterval);
  document.querySelector("#question-view").hidden = true;
  const result = document.querySelector("#result-view");
  result.hidden = false;
  result.replaceChildren();

  const correctCount = answerLog.filter((answer) => answer.correct).length;
  const percentage = Math.round((correctCount / questions.length) * 100);
  const medal = document.createElement("div");
  medal.className = "result-mark";
  medal.textContent = percentage >= 90 ? "★" : percentage >= 70 ? "◆" : percentage >= 50 ? "✦" : "•";
  const eyebrow = document.createElement("p");
  eyebrow.className = "eyebrow eyebrow-gold";
  eyebrow.textContent = `Round complete · ${currentCulture.name}`;
  const title = document.createElement("h2");
  title.textContent = percentage >= 90 ? "Exceptional" : percentage >= 70 ? "Excellent!" : percentage >= 50 ? "Good effort!" : "Keep learning!";
  const resultScore = document.createElement("p");
  resultScore.className = "result-score";
  resultScore.textContent = `${correctCount} / ${questions.length}`;
  const message = document.createElement("p");
  message.textContent = `${score} points · ${correctCount} of ${questions.length} correct.`;
  const breakdown = document.createElement("ol");
  breakdown.className = "answer-breakdown";
  answerLog.forEach((answer, index) => {
    const item = document.createElement("li");
    item.className = answer.correct ? "is-correct" : "is-wrong";
    const prompt = document.createElement("p");
    prompt.textContent = `${index + 1}. ${answer.prompt}`;
    const answerText = document.createElement("p");
    answerText.textContent = answer.correct
      ? `Your answer: ${answer.selected}`
      : `Your answer: ${answer.selected} · Correct answer: ${answer.correctAnswer}`;
    item.append(prompt, answerText);
    breakdown.append(item);
  });

  const actions = document.createElement("div");
  actions.className = "result-actions";
  const replay = document.createElement("button");
  replay.className = "button button-primary";
  replay.type = "button";
  replay.textContent = "Play this culture again";
  replay.addEventListener("click", () => startQuiz(currentCulture));
  const choose = document.createElement("button");
  choose.className = "button button-secondary";
  choose.type = "button";
  choose.textContent = "Choose another culture";
  choose.addEventListener("click", () => {
    quizModal.close();
    document.querySelector("#cultures").scrollIntoView({ behavior: "smooth" });
  });
  actions.append(replay, choose);
  result.append(medal, eyebrow, title, resultScore, message, breakdown, actions);
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3500);
}
