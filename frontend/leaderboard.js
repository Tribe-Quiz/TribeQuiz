import { getCurrentUser, getLeaderboard, signOut } from "./api.js";

const list = document.querySelector("#leaderboard-list");
const filters = document.querySelector("#leaderboard-filters");
const menuToggle = document.querySelector("#menu-toggle");
let scores = [];
let currentCulture = "all";
let currentSort = "score";

menuToggle.addEventListener("click", () => {
  const isExpanded = menuToggle.getAttribute("aria-expanded") === "true";
  menuToggle.setAttribute("aria-expanded", String(!isExpanded));
  menuToggle.setAttribute("aria-label", isExpanded ? "Open menu" : "Close menu");
  document.querySelector(".main-nav").classList.toggle("is-open", !isExpanded);
});

document.querySelector("#leaderboard-signout").addEventListener("click", async () => {
  try {
    await signOut();
    window.location.href = "auth.html";
  } catch (error) {
    showMessage(error.message || "Could not sign out.");
  }
});

async function loadLeaderboard() {
  try {
    await getCurrentUser();
  } catch (error) {
    if (error.status === 401) {
      window.location.replace("auth.html");
      return;
    }
    showMessage(error.message || "Could not check your account.");
    return;
  }
  try {
    ({ scores } = await getLeaderboard());
    renderFilters();
    renderScores();
  } catch (error) {
    showMessage(error.message || "Could not load the leaderboard.");
  }
}

function renderFilters() {
  const cultures = ["all", ...new Set(scores.map((entry) => entry.culture))];
  filters.replaceChildren();
  cultures.forEach((culture) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = culture === currentCulture ? "filter-btn active" : "filter-btn";
    button.textContent = culture === "all" ? "All Cultures" : culture;
    button.setAttribute("aria-pressed", String(culture === currentCulture));
    button.addEventListener("click", () => {
      currentCulture = culture;
      renderFilters();
      renderScores();
    });
    filters.append(button);
  });
}

function renderScores() {
  const visibleScores = scores
    .filter((entry) => currentCulture === "all" || entry.culture === currentCulture)
    .sort((left, right) => {
      if (currentSort === "percentage") {
        return (right.correct_count / right.question_count) - (left.correct_count / left.question_count);
      }
      if (currentSort === "date") {
        return right.completed_at.localeCompare(left.completed_at);
      }
      return right.score - left.score || right.completed_at.localeCompare(left.completed_at);
    });

  if (!visibleScores.length) {
    showMessage("No completed scores yet. Be the first to play!");
    return;
  }

  const table = document.createElement("table");
  table.className = "leaderboard-table";
  const header = document.createElement("thead");
  const headerRow = document.createElement("tr");
  [
    ["Rank", null],
    ["Player", null],
    ["Culture", null],
    ["Score", "score"],
    ["%", "percentage"],
    ["Date", "date"]
  ].forEach(([label, sortKey]) => {
    const cell = document.createElement("th");
    if (!sortKey) {
      cell.textContent = label;
    } else {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "sort-btn";
      button.textContent = `${label}${currentSort === sortKey ? " ⬍" : ""}`;
      button.addEventListener("click", () => {
        currentSort = sortKey;
        renderScores();
      });
      cell.append(button);
    }
    headerRow.append(cell);
  });
  header.append(headerRow);

  const body = document.createElement("tbody");
  visibleScores.forEach((entry, index) => {
    const row = document.createElement("tr");
    const percent = Math.round((entry.correct_count / entry.question_count) * 100);
    const values = [
      index < 3 ? ["🥇", "🥈", "🥉"][index] : String(index + 1),
      entry.user_name,
      entry.culture,
      `${entry.score} / ${entry.question_count * 10}`,
      `${percent}%`,
      new Date(entry.completed_at).toLocaleDateString()
    ];
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    });
    body.append(row);
  });
  table.append(header, body);
  list.replaceChildren(table);
}

function showMessage(message) {
  const paragraph = document.createElement("p");
  paragraph.className = "leaderboard-message";
  paragraph.textContent = message;
  list.replaceChildren(paragraph);
}

loadLeaderboard();
