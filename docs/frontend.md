# Frontend — Design Library RAG Web UI

Web interface for interacting with the RAG API from any device on the local network.

## How It Works

```
Browser (any device on LAN)
    │
    ▼
nginx (:80)
    ├── /* → static files (HTML/CSS/JS)
    └── /api/* → proxy to FastAPI (:8000)
```

nginx serves the static frontend and proxies `/api/*` requests to the RAG API on port 8000. This avoids CORS issues and keeps everything on a single origin.

## Setup

### 1. Install nginx

```bash
sudo apt-get install -y nginx
```

### 2. Configure nginx

```bash
# Copy the config
sudo cp /home/rpi/ai-engine/setup-ai-process/nginx-ai-engine.conf /etc/nginx/sites-available/ai-engine

# Enable the site
sudo ln -sf /etc/nginx/sites-available/ai-engine /etc/nginx/sites-enabled/ai-engine

# Remove the default site
sudo rm -f /etc/nginx/sites-enabled/default

# Test config and reload
sudo nginx -t && sudo systemctl reload nginx
```

### 3. Ensure the RAG API is running

```bash
cd /home/rpi/ai-engine/rag-api
nohup /home/rpi/ai-engine/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 \
  > /home/rpi/ai-engine/logs/rag-api.log 2>&1 &
```

### 4. Access the UI

Open a browser on any device on the same network and go to:

```
http://<pi-ip-address>/
```

Find the Pi's IP with:

```bash
hostname -I
```

## Features

### Search Tab
- Semantic search across the indexed design library
- Filter by framework (HTML, React, Vue, Svelte, Astro, CSS)
- Filter by component category (hero, header, footer, etc.)
- Adjustable result count (5, 10, 20)
- Code preview with copy button

### Generate Tab
- Enter a brief describing what you want to build
- Select task type: Component, Hero Section, Full Page, SEO Rewrite
- Filter context by framework
- Adjust number of context chunks (0-5)
- Live elapsed time counter during generation
- Copy generated code to clipboard
- Shows which design library examples were used as context

### Templates Tab
- Browse available templates by category
- 16 categories: hero, header, footer, navigation, card, pricing, testimonial, contact, cta, faq, form, table, gallery, modal, sidebar, 404
- Shows file path, framework, and code preview

### SEO Audit Tab
- Paste HTML and get an instant SEO score (0-100)
- Shows errors, warnings, and passed checks
- Checks: title, meta description, H1, lang attribute, charset, viewport, image alt text, heading hierarchy, Open Graph tags, canonical URL, empty links

## File Structure

```
/home/rpi/ai-engine/frontend/
├── index.html          # SPA shell with 4 tabs
├── css/
│   └── style.css       # Dark theme styles
└── js/
    └── app.js          # API calls, DOM manipulation, loading states
```

## nginx Config

Located at `/home/rpi/ai-engine/setup-ai-process/nginx-ai-engine.conf`:

```nginx
server {
    listen 80;
    server_name _;
    root /home/rpi/ai-engine/frontend;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 600s;
    }
}
```

The `/api/` prefix is stripped by nginx. So `/api/search` becomes `localhost:8000/search`.

## Performance Notes

| Action | Time |
|--------|------|
| Search | 2-8 seconds |
| Generate (component/hero) | 2-5 minutes |
| Generate (full page) | 5-10 minutes |
| SEO audit | Instant |
| Templates | 2-8 seconds |

The Generate tab shows a live elapsed timer so you know it's working.

## Troubleshooting

**Page loads but API calls fail:**
- Check RAG API is running: `curl http://localhost:8000/health`
- Check nginx config: `sudo nginx -t`
- Check nginx logs: `sudo tail /var/log/nginx/error.log`

**Cannot access from other devices:**
- Verify the Pi's firewall allows port 80: `sudo ufw status`
- Verify nginx is listening: `ss -tlnp | grep :80`

**Health indicator shows "API offline":**
- Start the RAG API (see step 3 above)

---

**Last Updated:** February 16, 2026
