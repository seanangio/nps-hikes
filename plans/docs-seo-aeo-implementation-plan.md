# Docs SEO/AEO Implementation Plan

## Objective

Improve discoverability of the MkDocs documentation site for:

- Search engines (SEO)
- Answer engines and AI assistants (AEO)
- Developers, recruiters, and project readers landing from GitHub, search, or AI-generated answers

This is a small personal project site by Sean Angiolillo, hosted long-term at:

```text
https://seanangio.github.io/nps-hikes/
```

The goal is not to make the project look like a commercial open source product. The docs should stay practical, personal, and developer-focused while giving crawlers and AI agents clearer metadata and entry points.

---

## Current State

### Existing Strengths

- `mkdocs.yml` already sets `site_url`, which enables correct absolute URLs and sitemap generation.
- MkDocs already publishes a working sitemap:
  - `https://seanangio.github.io/nps-hikes/sitemap.xml`
- The site has a clear four-page structure:
  - Home
  - Getting Started
  - Data Sources & Schema
  - API Tutorial
- The docs include useful links to:
  - GitHub repository
  - Streamlit demo
  - FastAPI Swagger UI
  - Python SDK repository

### Gaps

- No site-wide description or author metadata in `mkdocs.yml`.
- No page-level metadata/front matter.
- No `llms.txt`.
- No explicit crawler guidance file.
- No Google Search Console setup.
- No Google Analytics setup for the docs site.
- No structured data/schema markup.

---

## Decisions

### Audience

Target all three audiences:

1. Public search traffic
2. Portfolio/recruiting readers
3. AI/dev-agent discoverability

### Site Identity

Position the docs as:

> A personal project by Sean Angiolillo for collecting, analyzing, and exploring US National Park hiking trail data.

Avoid framing it primarily as a general-purpose open source product.

### Live Demos

The Render API and Streamlit app are stable enough to reference as demos, but metadata should describe them as demos rather than guaranteed production services.

### AI Crawling

AI crawlers and agents are allowed to crawl, train on, and summarize the public docs.

### Tone

Use a practical developer-docs tone. Metadata should be clear and descriptive, not marketing-heavy.

### Indexed Content

No pages or assets need to be excluded from indexing.

### Structured Data

Keep the first implementation simple. Defer JSON-LD/schema markup unless there is a later reason to invest in richer search result presentation.

### Search and Traffic Measurement

Set up both Google Search Console and Google Analytics.

- Google Search Console is for SEO validation: indexing, sitemap submission, crawl errors, canonical URLs, and Google Search queries.
- Google Analytics is for visitor behavior: page views, acquisition sources, geography, engagement, and repeat traffic.

Use Search Console to answer "can people find this site in Google?" and Analytics to answer "what do visitors do after they arrive?"

---

## Guidance on Open Questions

### What Should `llms.txt` Link To?

Recommendation: include both docs pages and high-value external project links, grouped by importance.

Use `llms.txt` as an AI-friendly table of contents, not as a comprehensive mirror of the whole project.

Include:

- Canonical docs home page
- Getting Started
- Data Sources & Schema
- API Tutorial
- GitHub repository
- Streamlit demo
- FastAPI Swagger UI demo
- Python SDK repository

Do not include:

- Every source file
- Generated assets
- Long API response samples
- Internal scratch/planning docs

Possible structure:

```markdown
# NPS Hikes

> Personal project by Sean Angiolillo for collecting, validating, analyzing, and exploring US National Park hiking trail data.

## Docs

- [Overview](https://seanangio.github.io/nps-hikes/)
- [Getting Started](https://seanangio.github.io/nps-hikes/getting-started/)
- [Data Sources & Schema](https://seanangio.github.io/nps-hikes/data/)
- [Using the API](https://seanangio.github.io/nps-hikes/api-tutorial/)

## Demos and Code

- [Streamlit demo](https://seanangio-nps-hikes.streamlit.app)
- [API Swagger UI demo](https://seanangio-nps-hikes.onrender.com/docs)
- [GitHub repository](https://github.com/seanangio/nps-hikes)
- [Python SDK repository](https://github.com/seanangio/nps-hikes-python-sdk)
```

Add `llms-full.txt` only if there is a real use case for a larger context bundle later.

### Should This Project Use Google Search Console?

Recommendation: yes. It should be part of the post-deployment SEO validation work.

Google Search Console is useful because it lets you:

- Verify whether Google can crawl the GitHub Pages site.
- Submit the sitemap directly.
- See indexing status and crawl errors.
- See search queries that surface the docs.
- Confirm canonical URLs.

For a small personal site, it is low maintenance. The only friction is proving ownership of the GitHub Pages URL. If custom domain ownership is not available, URL-prefix verification may require adding an HTML verification file or meta tag, depending on Google's available methods.

### Should This Project Use Google Analytics?

Recommendation: yes, since you want both SEO visibility and traffic measurement.

Google Analytics is useful because it lets you:

- See whether anyone visits the docs site.
- Understand which pages are getting attention.
- Compare traffic from GitHub, Google Search, direct visits, and AI/referral sources where available.
- Measure whether changes to metadata, docs structure, or external links affect visits.

For MkDocs Material, the likely implementation is the built-in Analytics config in `mkdocs.yml` once a GA4 measurement ID exists:

```yaml
extra:
  analytics:
    provider: google
    property: G-XXXXXXXXXX
```

Use the actual GA4 measurement ID from Google Analytics. Do not commit any private account credentials; the public measurement ID is expected to appear in the site source.

### Should This Project Add Structured Data?

Recommendation: defer.

Structured data means adding machine-readable JSON-LD to describe the page or software entity, for example `SoftwareSourceCode`, `WebApplication`, or `Person`. It can help search engines understand content, but it adds maintenance and is not necessary for the first SEO/AEO pass.

Revisit later if:

- Search Console shows the docs are indexed but poorly understood.
- The site moves to a custom domain.
- The project gets a more polished portfolio presentation.
- You want richer entity-level signals around Sean Angiolillo, the project, the app, and the API.

---

## Implementation Plan

### Phase 1: Site-Wide Metadata

Update `mkdocs.yml`.

Add:

```yaml
site_description: Personal project by Sean Angiolillo for collecting, analyzing, and exploring US National Park hiking trail data.
site_author: Sean Angiolillo
repo_name: seanangio/nps-hikes
```

Confirm existing values:

```yaml
site_url: https://seanangio.github.io/nps-hikes/
repo_url: https://github.com/seanangio/nps-hikes
```

Expected result:

- Better default page metadata.
- Clearer site identity.
- Continued sitemap generation.

### Phase 2: Page-Level Metadata

Add YAML front matter to each docs page.

Recommended page metadata:

#### `docs/index.md`

```yaml
---
title: NPS Hikes
description: Personal project by Sean Angiolillo for collecting, analyzing, and exploring US National Park hiking trail data with a FastAPI API, Streamlit app, and PostGIS database.
---
```

#### `docs/getting-started.md`

```yaml
---
title: Getting Started
description: Set up the NPS Hikes project locally with Docker, PostGIS, Python, the NPS API, and optional Ollama-powered natural language queries.
---
```

#### `docs/data.md`

```yaml
---
title: Data Sources and Schema
description: Overview of the NPS, OpenStreetMap, USGS, Google My Maps, and PostGIS data sources and schemas used by the NPS Hikes project.
---
```

#### `docs/api-tutorial.md`

```yaml
---
title: Using the API
description: Tutorial for querying the NPS Hikes FastAPI service, including parks, trails, stats, visualizations, and natural language search.
---
```

Expected result:

- Search snippets have better source descriptions.
- AI tools get concise summaries for each page.
- Page titles become more intentional.

### Phase 3: `llms.txt`

Add `docs/llms.txt`.

Purpose:

- Provide a concise, AI-readable index of the project.
- Clarify that this is a personal project.
- Point agents toward canonical docs and stable demos.

Recommended content:

```markdown
# NPS Hikes

> Personal project by Sean Angiolillo for collecting, validating, analyzing, and exploring US National Park hiking trail data.

NPS Hikes combines data from the National Park Service API, OpenStreetMap, USGS, and personal Google My Maps exports to build a PostGIS-backed trail database. The project exposes the data through a FastAPI API, a Streamlit web app, and a Python SDK.

## Documentation

- [Overview](https://seanangio.github.io/nps-hikes/): Project overview, architecture, live demos, and data pipeline summary.
- [Getting Started](https://seanangio.github.io/nps-hikes/getting-started/): Local setup with Docker, Python, PostGIS, the NPS API, and optional Ollama support.
- [Data Sources and Schema](https://seanangio.github.io/nps-hikes/data/): Source APIs, imported data, processing notes, and database schema.
- [Using the API](https://seanangio.github.io/nps-hikes/api-tutorial/): Tutorial for API endpoints, trail queries, visualizations, and natural language search.

## Demos

- [Streamlit demo](https://seanangio-nps-hikes.streamlit.app): Interactive map-based explorer for parks and trails.
- [API Swagger UI demo](https://seanangio-nps-hikes.onrender.com/docs): Interactive FastAPI documentation for the hosted demo API.

## Code

- [Project repository](https://github.com/seanangio/nps-hikes): Main repository for the data pipeline, API, Streamlit app, and docs.
- [Python SDK repository](https://github.com/seanangio/nps-hikes-python-sdk): Python client for the NPS Hikes API.

## Notes for AI Assistants

- Treat this as a personal project by Sean Angiolillo, not as an official National Park Service product.
- The hosted API and Streamlit app are demos and may pause or wake slowly on free hosting tiers.
- Prefer the documentation pages above as canonical context before inferring behavior from code.
```

Expected result:

- `https://seanangio.github.io/nps-hikes/llms.txt` is available after deployment.
- AI agents have a compact, canonical starting point.

### Phase 4: Robots Guidance

Recommendation: add `docs/robots.txt`, but document the GitHub Pages limitation.

For GitHub Pages project sites, the crawler-standard robots file for the host is normally:

```text
https://seanangio.github.io/robots.txt
```

This project can publish:

```text
https://seanangio.github.io/nps-hikes/robots.txt
```

That file is harmless and useful as an explicit convention, but some crawlers may only consult the host-level file.

Recommended content:

```txt
User-agent: *
Allow: /

Sitemap: https://seanangio.github.io/nps-hikes/sitemap.xml
```

Do not use `Disallow` unless there is content that should not be crawled.

Expected result:

- Clear allow-all crawler policy.
- Sitemap location advertised.
- No accidental blocking of docs pages.

### Phase 5: Validation

Run:

```bash
mkdocs build --strict
```

Inspect generated files:

```text
site/index.html
site/getting-started/index.html
site/data/index.html
site/api-tutorial/index.html
site/sitemap.xml
site/llms.txt
site/robots.txt
```

Check:

- Build passes with no warnings.
- Sitemap still includes all pages.
- `llms.txt` is copied to the site root.
- `robots.txt` is copied to the site root.
- Page titles and descriptions render as expected in HTML.

### Phase 6: Optional Post-Deployment Tasks

After the changes are deployed to GitHub Pages:

1. Visit:
   - `https://seanangio.github.io/nps-hikes/sitemap.xml`
   - `https://seanangio.github.io/nps-hikes/llms.txt`
   - `https://seanangio.github.io/nps-hikes/robots.txt`
2. Set up Google Search Console for the GitHub Pages URL.
3. Submit the sitemap in Search Console:

```text
https://seanangio.github.io/nps-hikes/sitemap.xml
```

4. Set up Google Analytics 4 for the docs site.
5. Add the GA4 measurement ID to `mkdocs.yml`.
6. Redeploy the docs site and confirm Analytics receives traffic.
7. Search for indexed pages after a few days:

```text
site:seanangio.github.io/nps-hikes
```

---

## Google Tool Setup Notes

### Google Search Console

Recommended property type:

- Use a URL-prefix property for `https://seanangio.github.io/nps-hikes/`.

Possible verification methods:

- HTML file upload, if Google allows it for the GitHub Pages project path.
- HTML meta tag added through MkDocs theme customization, if needed.
- Google Analytics verification, after GA is installed.

After verification:

- Submit `https://seanangio.github.io/nps-hikes/sitemap.xml`.
- Check the Pages report for indexing issues.
- Use URL Inspection on the home page and the API tutorial.

### Google Analytics

Recommended property type:

- Create or reuse a GA4 property.
- Create a web data stream for `https://seanangio.github.io/nps-hikes/`.
- Copy the measurement ID, which starts with `G-`.

Implementation:

- Add MkDocs Material's built-in analytics configuration to `mkdocs.yml`.
- Keep the measurement ID in config unless you intentionally want environment-specific docs builds.

Validation:

- Run `mkdocs build --strict`.
- Deploy the site.
- Open the docs site in a browser.
- Confirm traffic appears in GA4 Realtime.

---

## Files to Modify

| File | Change |
| --- | --- |
| `mkdocs.yml` | Add site description, author, and repo display name |
| `docs/index.md` | Add title and description front matter |
| `docs/getting-started.md` | Add title and description front matter |
| `docs/data.md` | Add title and description front matter |
| `docs/api-tutorial.md` | Add title and description front matter |
| `docs/llms.txt` | Add AI-readable project index |
| `docs/robots.txt` | Add allow-all crawler guidance and sitemap URL |
| `mkdocs.yml` | Later: add Google Analytics config after GA4 measurement ID exists |

---

## References

- Google Search Central: Robots.txt introduction
  - `https://developers.google.com/search/docs/crawling-indexing/robots/intro`
- Google Search Central: Sitemaps
  - `https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview`
- Google Search Central: Title links and snippets
  - `https://developers.google.com/search/docs/appearance/title-link`
  - `https://developers.google.com/search/docs/appearance/snippet`
- MkDocs: Configuration and page metadata
  - `https://www.mkdocs.org/user-guide/configuration/`
  - `https://www.mkdocs.org/user-guide/writing-your-docs/`
- `llms.txt` proposal
  - `https://llmstxt.org/`
