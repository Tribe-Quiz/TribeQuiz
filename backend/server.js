const path = require("node:path");
const express = require("express");
const { cultures, questions } = require("./quizData");

const app = express();
const port = process.env.PORT || 3000;
const frontendPath = path.join(__dirname, "..", "frontend");

app.get("/api/health", (request, response) => {
  response.json({ status: "ok" });
});

app.get("/api/quiz", (request, response) => {
  response.json({ cultures, questions });
});

app.use(express.static(frontendPath));

app.listen(port, () => {
  console.log(`Tribe Quiz is running at http://localhost:${port}`);
});