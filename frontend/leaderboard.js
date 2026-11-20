import { getLeaderboard, signOut } from "./api.js";

const list = document.querySelector("#leaderboard-list");
const menuToggle = document.querySelector("#menu-toggle");
const position = document.querySelector("#leaderboard-position");
const signOutButton = document.querySelector("#leaderboard-signout");
let isSignedIn = false;

menuToggle.addEventListener("click", () => {
  const isExpanded = menuToggle.getAttribute("aria-expanded") === "true";
  menuToggle.setAttribute("aria-expanded", String(!isExpanded));
  menuToggle.setAttribute("aria-label", isExpanded ? "Open menu" : "Close menu");
  document.querySelector(".main-nav").classList.toggle("is-open", !isExpanded);
});

signOutButton.addEventListener("click", async () => {
  if (!isSignedIn) {
    window.location.href = "auth.html";
    return;
  }
  try {
    await signOut();
    window.location.href = "auth.html";
  } catch (error) {
    showMessage(error.message || "Could not sign out.");
  }
});

async function loadLeaderboard() {
  try {
    const leaderboard = await getLeaderboard();
    isSignedIn = leaderboard.is_signed_in;
    signOutButton.textContent = isSignedIn ? "Sign Out" : "Sign In";
    renderPosition(
      leaderboard.current_rank,
      leaderboard.player_count,
      leaderboard.is_signed_in
    );
    renderScores(leaderboard.scores);
  } catch (error) {
    showMessage(error.message || "Could not load the leaderboard.");
  }
}

function renderPosition(rank, playerCount, isSignedIn) {
  position.textContent = rank
    ? `Your overall position: #${rank} of ${playerCount} player${playerCount === 1 ? "" : "s"}`
    : isSignedIn
      ? "Complete a quiz to appear in the overall rankings."
      : "Sign in and complete a quiz to see your overall position.";
}

function renderScores(scores) {
  if (!scores.length) {
    showMessage("No completed scores yet. Be the first to play!");
    return;
  }

  const table = document.createElement("table");
  table.className = "leaderboard-table";
  const header = document.createElement("thead");
  const headerRow = document.createElement("tr");
  ["Rank", "Player", "Overall score", "Quizzes played", "Accuracy"].forEach((label) => {
    const cell = document.createElement("th");
    cell.textContent = label;
    headerRow.append(cell);
  });
  header.append(headerRow);

  const body = document.createElement("tbody");
  scores.forEach((entry) => {
    const row = document.createElement("tr");
    if (entry.is_current_user) row.className = "current-player";
    const percent = entry.question_count
      ? Math.round((entry.correct_count / entry.question_count) * 100)
      : 0;
    const values = [
      String(entry.rank),
      entry.is_current_user ? `${entry.user_name} (You)` : entry.user_name,
      `${entry.score} points`,
      String(entry.quizzes_played),
      `${percent}%`,
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
