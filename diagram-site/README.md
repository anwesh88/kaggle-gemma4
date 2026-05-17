# Finsight OS Diagrams

Standalone static viewer for the architecture and data pipeline diagrams.

## Local preview

```bash
cd diagram-site
python -m http.server 8765
```

Open:
- `/` for the toggle viewer
- `/#architecture` for the architecture view
- `/#data-pipeline` for the data pipeline view

## Vercel

Deploy this folder as its own Vercel project. When using the CLI from the repo root:

```bash
npx vercel@latest --cwd diagram-site
npx vercel@latest --cwd diagram-site --prod
```
