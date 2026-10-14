# Franka-LLM research website

This is a static HTML/CSS/JavaScript site. It has no build step or runtime dependencies.

Open `index.html` directly for a quick preview, or serve this directory with any static server:

```bash
cd website
python3 -m http.server 8000
```

The site is intended for `https://cogrob-tuni.github.io/franka-llm/`; all local media paths are relative so the project-site subpath works without a bundler.

## GitHub Pages

The workflow at `.github/workflows/deploy-website.yml` publishes `website/` from the `website` branch. In repository settings, select **Pages → Build and deployment → Source → GitHub Actions**. Publication metadata links to IEEE Xplore and the arXiv preprint; the citation button includes the verified DOI and conference details.
