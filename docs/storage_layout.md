# Design Library — Storage Layout Reference

## Mount Point

```
/mnt/design-library/          ← 500GB USB SSD mounted via fstab
```

## Full Directory Structure

```
/mnt/design-library/
│
├── example-websites/                  ← Git-cloned repos (your primary source)
│   │
│   ├── html-css/                      ← Pure HTML/CSS sites
│   │   ├── html5up-massively/         ← git clone of html5up.net templates
│   │   │   ├── index.html
│   │   │   ├── generic.html
│   │   │   ├── elements.html
│   │   │   └── assets/
│   │   │       ├── css/main.css
│   │   │       ├── js/main.js
│   │   │       └── sass/              ← SCSS source files
│   │   ├── startbootstrap-agency/
│   │   ├── tailwindui-spotlight/
│   │   └── ...
│   │
│   ├── react/                         ← React-based projects
│   │   ├── shadcn-taxonomy/           ← Next.js + shadcn/ui example
│   │   │   ├── src/
│   │   │   │   ├── app/
│   │   │   │   │   ├── layout.tsx
│   │   │   │   │   ├── page.tsx
│   │   │   │   │   └── (routes)/
│   │   │   │   ├── components/
│   │   │   │   │   ├── ui/
│   │   │   │   │   │   ├── button.tsx
│   │   │   │   │   │   ├── card.tsx
│   │   │   │   │   │   └── ...
│   │   │   │   │   ├── header.tsx
│   │   │   │   │   ├── hero.tsx
│   │   │   │   │   └── footer.tsx
│   │   │   │   ├── lib/
│   │   │   │   └── styles/
│   │   │   │       └── globals.css
│   │   │   ├── tailwind.config.ts
│   │   │   ├── package.json
│   │   │   └── tsconfig.json
│   │   ├── vitesse-react/
│   │   ├── refine-crm-dashboard/
│   │   └── ...
│   │
│   ├── nextjs/                        ← Next.js specific
│   │   ├── next-saas-stripe-starter/
│   │   ├── nextjs-commerce/
│   │   ├── next-enterprise/
│   │   └── ...
│   │
│   ├── astro/                         ← Astro static sites
│   │   ├── astro-landing-page/
│   │   │   ├── src/
│   │   │   │   ├── pages/
│   │   │   │   │   └── index.astro
│   │   │   │   ├── layouts/
│   │   │   │   │   └── Layout.astro
│   │   │   │   ├── components/
│   │   │   │   │   ├── Hero.astro
│   │   │   │   │   ├── Features.astro
│   │   │   │   │   └── Footer.astro
│   │   │   │   └── styles/
│   │   │   │       └── global.css
│   │   │   └── astro.config.mjs
│   │   ├── astro-paper/               ← Blog theme
│   │   ├── starlight-docs/            ← Documentation theme
│   │   └── ...
│   │
│   ├── vue/                           ← Vue.js projects
│   │   ├── vue-element-admin/
│   │   ├── nuxt-ui-landing/
│   │   └── ...
│   │
│   ├── svelte/                        ← SvelteKit projects
│   │   ├── sveltekit-superforms/
│   │   └── ...
│   │
│   ├── tailwind/                      ← Tailwind CSS focused templates
│   │   ├── tailwindcss-templates/
│   │   ├── hyperui-components/
│   │   └── ...
│   │
│   └── multi-page-sites/             ← Full multi-page business sites
│       ├── developer-portfolio/
│       ├── restaurant-theme/
│       ├── law-firm-theme/
│       ├── saas-landing/
│       └── ...
│
├── components/                        ← Extracted/curated standalone components
│   ├── headers/
│   │   ├── sticky-nav-tailwind.html
│   │   ├── mega-menu-react.jsx
│   │   └── hamburger-menu-css.html
│   ├── hero-sections/
│   │   ├── split-hero-with-image.html
│   │   ├── video-background-hero.html
│   │   └── animated-gradient-hero.jsx
│   ├── footers/
│   ├── pricing-tables/
│   ├── testimonials/
│   ├── contact-forms/
│   ├── cta-blocks/
│   ├── feature-grids/
│   ├── faq-accordions/
│   └── 404-pages/
│
├── seo-configs/
│   ├── schema-templates/              ← JSON-LD structured data
│   │   ├── local-business.json
│   │   ├── organization.json
│   │   ├── product.json
│   │   ├── faq-page.json
│   │   ├── breadcrumb.json
│   │   └── service.json
│   ├── meta-templates/                ← Industry-specific meta tag configs
│   │   ├── restaurant.yaml
│   │   ├── law-firm.yaml
│   │   ├── plumber.yaml
│   │   ├── dentist.yaml
│   │   └── ecommerce.yaml
│   └── robots-templates/
│       ├── standard-robots.txt
│       └── ecommerce-robots.txt
│
├── style-guides/
│   ├── color-palettes/
│   │   ├── warm-organic.json          ← { "primary": "#C4704B", ... }
│   │   ├── dark-luxury.json
│   │   ├── fresh-modern.json
│   │   └── bold-brutalist.json
│   ├── typography-systems/
│   │   ├── editorial.json             ← { "display": "Playfair Display", "body": "Source Serif 4" }
│   │   ├── geometric-clean.json
│   │   └── monospace-tech.json
│   └── design-tokens/
│       ├── spacing.json
│       └── breakpoints.json
│
├── client-projects/                   ← Output directory for generated sites
│   └── {client-slug}/
│       ├── brief.yaml
│       ├── src/
│       ├── build/
│       └── seo-audit.json
│
└── .index/                            ← Indexer metadata (auto-generated)
    ├── file_hashes.json               ← SHA256 hashes for change detection
    ├── index_log.jsonl                 ← Indexing run logs
    └── stats.json                     ← Library statistics
```

## File Types the Indexer Processes

### Code Files (Primary — chunked, embedded, and stored in ChromaDB)

| Extension | Language / Framework | What Gets Indexed |
|-----------|---------------------|-------------------|
| `.html` | HTML | Full page structure, semantic sections, meta tags |
| `.htm` | HTML | Same as .html |
| `.css` | CSS | Rule blocks, custom properties, media queries |
| `.scss` `.sass` | SCSS/Sass | Mixins, variables, component styles |
| `.js` | JavaScript | Component logic, DOM manipulation, animations |
| `.jsx` | React JSX | React components, hooks, props patterns |
| `.tsx` | React TypeScript | Same as JSX with type definitions |
| `.ts` | TypeScript | Utility functions, type definitions |
| `.vue` | Vue SFC | Template + script + style combined |
| `.svelte` | Svelte | Component markup + logic |
| `.astro` | Astro | Astro component/page format |

### Config Files (Indexed as metadata, not chunked)

| Extension | Purpose |
|-----------|---------|
| `.json` | package.json, tsconfig, design tokens, color palettes |
| `.yaml` `.yml` | Client briefs, SEO configs, CI configs |
| `.toml` | Astro/Vite/Hugo config |
| `tailwind.config.*` | Tailwind theme configuration |
| `next.config.*` | Next.js configuration |
| `astro.config.*` | Astro configuration |

### Files the Indexer SKIPS

| Pattern | Reason |
|---------|--------|
| `node_modules/` | Dependencies — not useful for design reference |
| `.git/` | Git internals |
| `dist/` `build/` `.next/` `.output/` | Build artifacts |
| `*.min.js` `*.min.css` | Minified — unreadable |
| `*.map` | Source maps |
| `*.lock` | Lock files |
| `*.png` `*.jpg` `*.svg` `*.gif` `*.webp` `*.ico` | Binary assets |
| `*.woff` `*.woff2` `*.ttf` `*.eot` | Font files |
| `*.mp4` `*.webm` `*.mp3` | Media files |
| `LICENSE*` `CHANGELOG*` `.env*` | Non-design files |

## Recommended Git Repos to Clone

### HTML/CSS Templates
```bash
cd /mnt/design-library/example-websites/html-css/
git clone https://github.com/html5up/html5up.github.io html5up-collection
git clone https://github.com/StartBootstrap/startbootstrap-agency
git clone https://github.com/StartBootstrap/startbootstrap-creative
git clone https://github.com/tailwindtoolbox/Landing-Page
```

### React / Next.js
```bash
cd /mnt/design-library/example-websites/react/
git clone https://github.com/shadcn-ui/taxonomy
git clone https://github.com/steven-tey/dub             # SaaS landing
git clone https://github.com/cruip/open-react-template

cd /mnt/design-library/example-websites/nextjs/
git clone https://github.com/vercel/commerce nextjs-commerce
git clone https://github.com/mickasmt/next-saas-stripe-starter
```

### Astro
```bash
cd /mnt/design-library/example-websites/astro/
git clone https://github.com/onwidget/astrowind
git clone https://github.com/satnaing/astro-paper
git clone https://github.com/withastro/starlight
```

### Tailwind Component Libraries
```bash
cd /mnt/design-library/example-websites/tailwind/
git clone https://github.com/markmead/hyperui
git clone https://github.com/tailwindlabs/tailwindcss.com
```

### Full Business Sites
```bash
cd /mnt/design-library/example-websites/multi-page-sites/
git clone https://github.com/RyanFitzgerald/devportfolio
```

```
┌────────────────────────────────────────────────────────────┐
│  SYSTEMD SERVICE MANAGEMENT CHEAT SHEET                    │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  STOP (immediate):                                         │
│    sudo systemctl stop <service>                           │
│                                                            │
│  START (immediate):                                        │
│    sudo systemctl start <service>                          │
│                                                            │
│  RESTART (immediate):                                      │
│    sudo systemctl restart <service>                        │
│                                                            │
│  DISABLE (prevent boot auto-start):                        │
│    sudo systemctl disable <service>                        │
│                                                            │
│  ENABLE (allow boot auto-start):                           │
│    sudo systemctl enable <service>                         │
│                                                            │
│  STATUS (check if running):                                │
│    systemctl status <service>                              │
│                                                            │
│  LOGS (view recent):                                       │
│    journalctl -u <service> -n 50                           │
│                                                            │
│  LOGS (live follow):                                       │
│    journalctl -u <service> -f                              │
│                                                            │
└────────────────────────────────────────────────────────────┘

Services:
  - design-library-watcher
  - design-library-reindex.timer
  - design-library-reindex.service
```