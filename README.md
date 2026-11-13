# Tribe Quiz

The project is split into a browser frontend and a Node.js/Express backend.

## Structure

- `frontend/` contains the pages, styles, and browser-side quiz behavior.
- `backend/` contains the Express server and quiz data returned by the API.

## Run locally

Install Node.js, then run:

```sh
npm install
npm start
```

Open `http://localhost:3000`. The backend exposes `GET /api/health` and `GET /api/quiz`.

Account forms currently use browser local storage as a demo. They are not backed by server authentication or suitable for real user credentials.