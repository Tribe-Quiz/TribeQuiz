const cultures = [
  { name: "Zulu", language: "IsiZulu", region: "South Africa", image: "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=700&q=80" },
  { name: "Xhosa", language: "IsiXhosa", region: "South Africa", image: "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=700&q=80" },
  { name: "Sesotho", language: "Sesotho", region: "Lesotho · South Africa", image: "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=700&q=80" },
  { name: "Sepedi", language: "Sesotho sa Leboa", region: "South Africa", image: "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?auto=format&fit=crop&w=700&q=80" },
  { name: "Tswana", language: "Setswana", region: "Botswana · South Africa", image: "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?auto=format&fit=crop&w=700&q=80" },
  { name: "Tsonga", language: "itsonga", region: "Southern Africa", image: "https://images.unsplash.com/photo-1523805009345-7448845a9e53?auto=format&fit=crop&w=700&q=80" },
  { name: "Venda", language: "Tshivenḓa", region: "South Africa", image: "https://images.unsplash.com/photo-1516426122078-c23e76319801?auto=format&fit=crop&w=700&q=80" },
  { name: "Swati", language: "siSwati", region: "Eswatini · South Africa", image: "https://images.unsplash.com/photo-1509316785289-025f5b846b35?auto=format&fit=crop&w=700&q=80" },
  { name: "Ndebele", language: "isiNdebele", region: "Southern Africa", image: "https://images.unsplash.com/photo-1547471080-7cc2caa01a7e?auto=format&fit=crop&w=700&q=80" },
  { name: "Afrikaner", language: "Afrikaans", region: "Southern Africa", image: "https://images.unsplash.com/photo-1484318571209-661cf29a69c3?auto=format&fit=crop&w=700&q=80" },
  { name: "Swahili", language: "Kiswahili", region: "East Africa", image: "https://images.unsplash.com/photo-1523805009345-7448845a9e53?auto=format&fit=crop&w=700&q=80" }
];

const questions = [
  { prompt: "Which language family includes many languages spoken across southern Africa?", options: ["Romance", "Bantu", "Celtic", "Slavic"], answer: 1, note: "Many languages across central, eastern, and southern Africa belong to the Bantu language family." },
  { prompt: "What is the name for a traditional African community gathering place often centered around a homestead?", options: ["Agora", "Forum", "Kraal", "Piazza"], answer: 2, note: "A kraal is an enclosure or homestead settlement, a term used in parts of southern Africa." },
  { prompt: "Which instrument is commonly used to carry rhythms and stories across generations?", options: ["Bagpipe", "Harpsichord", "Accordion", "Talking drum"], answer: 3, note: "Drums have many roles across African musical traditions, including communication and ceremony." },
  { prompt: "What is oral tradition?", options: ["A written census", "Passing knowledge through spoken stories", "A style of weaving", "A harvest festival"], answer: 1, note: "Oral tradition keeps history, values, and knowledge alive through spoken forms." },
  { prompt: "The Swahili language developed along which coast?", options: ["West African coast", "Mediterranean coast", "East African coast", "Atlantic coast of Europe"], answer: 2, note: "Swahili grew through centuries of exchange along the East African coast." },
  { prompt: "Which material is widely used in traditional beadwork across southern Africa?", options: ["Glass beads", "Rubber tiles", "Tin foil", "Concrete"], answer: 0, note: "Colorful glass beads are used in many communities for adornment and visual expression." },
  { prompt: "What does a family name or praise name often help preserve?", options: ["Weather forecasts", "Market prices", "Road directions", "Ancestry and identity"], answer: 3, note: "Names and praise poetry can carry lineage, identity, and family history." },
  { prompt: "Which country is home to the Basotho people and is entirely surrounded by South Africa?", options: ["Ghana", "Lesotho", "Kenya", "Tunisia"], answer: 1, note: "Lesotho is a highland kingdom completely enclosed by South Africa." },
  { prompt: "What is a common purpose of ceremonial dance?", options: ["Measuring distance", "Keeping written records", "Celebration, storytelling, and community", "Predicting tides"], answer: 2, note: "Dance can mark important events and express shared histories and beliefs." },
  { prompt: "Which principle is often described by the Nguni word Ubuntu?", options: ["Strength through solitude", "Trade by sea", "A type of harvest", "Humanity through our relationships"], answer: 3, note: "Ubuntu is commonly expressed as the idea that our humanity is bound up with one another." }
];

const grid = document.querySelector("#culture-grid");
const howtoModal = document.querySelector("#howto-modal");
const quizModal = document.querySelector("#quiz-modal");
const toast = document.querySelector("#toast");
const menuToggle = document.querySelector("#menu-toggle");
const nav = document.querySelector("#main-nav");
let currentCulture = null;
let questionIndex = 0;
let score = 0;
let selectedAnswer = null;
let answerSubmitted = false;
let toastTimer;

cultures.forEach((culture, index) => {
  const card = document.createElement("article");
  card.className = "culture-card";
  card.style.setProperty("--culture-image", `url("${culture.image}")`);
  card.style.animationDelay = `${Math.min(index * 45, 360)}ms`;
  card.innerHTML = `<div class="culture-card-content"><span class="culture-index">CULTURE ${String(index + 1).padStart(2, "0")}</span><h3>${culture.name}</h3><p>${culture.language} <span aria-hidden="true">·</span> ${culture.region}</p><button class="culture-play" type="button" aria-label="Play ${culture.name} quiz">Begin the quiz <span aria-hidden="true">›</span></button></div>`;
  card.querySelector("button").addEventListener("click", () => startQuiz(culture));
  grid.append(card);
});

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

function startQuiz(culture) {
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

document.querySelector("#quiz-next").addEventListener("click", () => {
  if (answerSubmitted) {
    advanceQuestion();
    return;
  }
  if (selectedAnswer === null) return;
  answerSubmitted = true;
  const question = questions[questionIndex];
  const buttons = [...document.querySelectorAll(".answer-option")];
  const feedback = document.querySelector("#quiz-feedback");
  buttons.forEach((button, index) => {
    button.disabled = true;
    if (index === question.answer) button.classList.add("correct");
    else if (index === selectedAnswer) button.classList.add("incorrect");
  });
  const isCorrect = selectedAnswer === question.answer;
  if (isCorrect) score += 10;
  feedback.textContent = isCorrect ? `Correct. ${question.note}` : `Not quite. ${question.note}`;
  feedback.classList.add(isCorrect ? "is-correct" : "is-wrong");
  document.querySelector("#quiz-score").textContent = `${score} points`;
  const nextButton = document.querySelector("#quiz-next");
  nextButton.disabled = false;
  nextButton.textContent = questionIndex === questions.length - 1 ? "See your result  ›" : "Next question  ›";
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

window.addEventListener("storage", (event) => {
  if (event.key === "tribeQuizUser") showToast("Your account details were updated in another tab.");
});