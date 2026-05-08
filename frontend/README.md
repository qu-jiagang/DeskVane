# DeskVane Frontend

This is the first Web UI surface for the Tauri migration.

It intentionally has no npm dependencies yet. The scripts use Node's standard
library so the dashboard can run before the final frontend framework is chosen.

## Commands

```bash
npm --prefix frontend run dev
npm --prefix frontend run build
npm --prefix frontend run preview
```

The dashboard expects the Python runtime API at:

```text
http://127.0.0.1:37655
```

Start DeskVane first, then open:

```text
http://127.0.0.1:5173
```
