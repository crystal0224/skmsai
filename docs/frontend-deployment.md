# Frontend Deployment Topology

## Source Of Truth

- Static frontend source of truth: `public/`
- Netlify publish directory: `public/`
- Production API: Render service defined by `render.yaml`
- Legacy snapshots: repository root `index.html`/`styles.css`, `everline-studio-clone/`

## Edit Rules

1. Frontend UI changes are made only in `public/index.html` and `public/styles.css`.
2. Backend/API changes are made under `server/`, `src/`, and deployment settings such as `render.yaml`.
3. If the frontend domain changes, update Render `ALLOWED_ORIGINS` with the new origin before or together with the deploy.

## Local Verification

```bash
cd public
python -m http.server 5500
```

Open `http://127.0.0.1:5500` and verify that API requests target the configured backend.

## Deployment Checklist

1. Frontend-only change:
   Edit `public/` and deploy Netlify.
2. Backend-only change:
   Edit `server/` or related backend code and deploy Render.
3. End-to-end feature change:
   Deploy both Netlify and Render if the UI and API contract both changed.
4. Domain change:
   Update Render `ALLOWED_ORIGINS` and then deploy the frontend to the new origin.
