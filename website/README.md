# Research project website

This directory is a static project website template for Cognitive Robotics Group projects. It has no build step or runtime dependencies.

## Local preview

```bash
cd website
python3 -m http.server 8000
```

Open <http://localhost:8000/> in a browser.

## Creating a project website

Use this directory as the starting point for the `website` branch of a project repository. Replace the project-specific content in `index.html`, media files, and `site.json`. Keep the lab branding, navigation, and footer links unless the lab maintains a newer template version.

The required registry file is `site.json`:

```json
{
  "schemaVersion": 1,
  "published": true,
  "title": "Your project name",
  "description": "A short description for the lab project index.",
  "authors": ["Researcher Name"],
  "year": 2026,
  "url": "https://cogrob-tuni.github.io/repository-name/",
  "repository": "https://github.com/cogrob-tuni/repository-name",
  "image": "media/featured-image.jpg",
  "order": 20
}
```

Set `published` to `false` while the page is a draft. The lab landing page will only list websites with a valid `site.json` where `published` is `true`.

The landing page can discover this file from the `website` branch at:

```text
https://raw.githubusercontent.com/cogrob-tuni/<repository>/website/website/site.json
```

## GitHub Pages

The workflow at `.github/workflows/deploy-website.yml` publishes `website/` from the `website` branch. In repository settings, select **Pages → Build and deployment → Source → GitHub Actions**.

The project URL is normally:

```text
https://cogrob-tuni.github.io/<repository-name>/
```

Keep local media paths relative so the site works from this project-site subpath.

## Lab links

- [CogRob lab homepage](https://cogrob-tuni.github.io/)
- [Tampere University Cognitive Robotics Group](https://www.tuni.fi/en/tau/research/cognitive-robotics-group)
- [CogRob research site](https://research.tuni.fi/cogrob/)
