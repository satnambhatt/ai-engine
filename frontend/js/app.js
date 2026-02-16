/* ── Design Library RAG — Frontend Logic ─────────────────────────── */

const API = '/api';

// ── Tab Navigation ──────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active');
    });
});

// ── Health Check ────────────────────────────────────────────────────
async function checkHealth() {
    const indicator = document.getElementById('health-indicator');
    const dot = indicator.querySelector('.health-dot');
    const text = indicator.querySelector('.health-text');
    try {
        const res = await fetch(`${API}/health`);
        const data = await res.json();
        dot.className = 'health-dot ' + (data.status === 'ok' ? 'ok' : 'degraded');
        text.textContent = `${data.chunks_indexed.toLocaleString()} chunks`;
        indicator.title = `Embed: ${data.ollama_embed ? 'OK' : 'DOWN'} | Chat: ${data.ollama_chat ? 'OK' : 'DOWN'} | DB: ${data.chromadb ? 'OK' : 'DOWN'}`;
    } catch {
        dot.className = 'health-dot error';
        text.textContent = 'API offline';
        indicator.title = 'Cannot reach RAG API';
    }
}
checkHealth();
setInterval(checkHealth, 30000);

// ── Copy to Clipboard ───────────────────────────────────────────────
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        const toast = document.getElementById('copy-toast');
        if (!toast) {
            const el = document.createElement('div');
            el.id = 'copy-toast';
            el.className = 'copy-toast';
            el.textContent = 'Copied to clipboard';
            document.body.appendChild(el);
            requestAnimationFrame(() => el.classList.add('show'));
            setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 200); }, 1500);
        }
    });
}

// ── Escape HTML ─────────────────────────────────────────────────────
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Search ──────────────────────────────────────────────────────────
document.getElementById('search-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = document.getElementById('search-query').value.trim();
    const framework = document.getElementById('search-framework').value;
    const category = document.getElementById('search-category').value;
    const nResults = parseInt(document.getElementById('search-n-results').value);

    const meta = document.getElementById('search-meta');
    const results = document.getElementById('search-results');
    meta.textContent = 'Searching...';
    results.innerHTML = '';

    const body = { query, n_results: nResults };
    if (framework) body.framework = framework;
    if (category) body.category = category;

    try {
        const res = await fetch(`${API}/search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const err = await res.json();
            meta.innerHTML = '';
            results.innerHTML = `<div class="error-msg">${escapeHtml(err.detail || 'Search failed')}</div>`;
            return;
        }

        const data = await res.json();
        meta.textContent = `${data.results.length} results in ${(data.duration_ms / 1000).toFixed(1)}s`;

        if (data.results.length === 0) {
            results.innerHTML = '<div class="empty-state">No results found. Try a different query or broader filters.</div>';
            return;
        }

        results.innerHTML = data.results.map(r => `
            <div class="result-card">
                <div class="result-header">
                    <span class="result-path">${escapeHtml(r.file_path)}</span>
                    <div class="result-badges">
                        <span class="badge badge-framework">${escapeHtml(r.framework)}</span>
                        ${r.component_category ? `<span class="badge badge-category">${escapeHtml(r.component_category)}</span>` : ''}
                        <span class="badge badge-similarity">${(r.similarity * 100).toFixed(0)}%</span>
                    </div>
                </div>
                <div class="result-code"><pre>${escapeHtml(r.text)}</pre></div>
                <div class="result-actions">
                    <button class="btn btn-sm btn-ghost" onclick="copyToClipboard(${escapeHtml(JSON.stringify(JSON.stringify(r.text)))})">Copy Code</button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        meta.innerHTML = '';
        results.innerHTML = `<div class="error-msg">Network error: ${escapeHtml(err.message)}</div>`;
    }
});

// ── Generate ────────────────────────────────────────────────────────
document.getElementById('generate-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const brief = document.getElementById('generate-brief').value.trim();
    const task = document.getElementById('generate-task').value;
    const framework = document.getElementById('generate-framework').value;
    const nContext = parseInt(document.getElementById('generate-context').value);

    const status = document.getElementById('generate-status');
    const output = document.getElementById('generate-output');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    submitBtn.disabled = true;
    status.innerHTML = `
        <div class="status-bar">
            <div class="spinner"></div>
            <span>Generating code... This may take 2-10 minutes on Raspberry Pi.</span>
        </div>
    `;
    output.innerHTML = '';

    const body = { brief, task, n_context: nContext };
    if (framework) body.framework = framework;

    const startTime = Date.now();
    // Update elapsed time every second
    const timer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const mins = Math.floor(elapsed / 60);
        const secs = elapsed % 60;
        const timeStr = mins > 0 ? `${mins}m ${secs}s` : `${secs}s`;
        const spinnerEl = status.querySelector('.status-bar span');
        if (spinnerEl) {
            spinnerEl.textContent = `Generating code... (${timeStr} elapsed)`;
        }
    }, 1000);

    try {
        const res = await fetch(`${API}/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        clearInterval(timer);

        if (!res.ok) {
            const err = await res.json();
            status.innerHTML = '';
            output.innerHTML = `<div class="error-msg">${escapeHtml(err.detail || 'Generation failed')}</div>`;
            submitBtn.disabled = false;
            return;
        }

        const data = await res.json();
        const duration = (data.duration_ms / 1000).toFixed(1);
        status.innerHTML = '';

        output.innerHTML = `
            <div class="code-block">
                <div class="code-block-header">
                    <span>${escapeHtml(data.model)} | ${duration}s | ${data.code.length.toLocaleString()} chars</span>
                    <button class="btn btn-sm btn-ghost" id="copy-generated">Copy</button>
                </div>
                <pre>${escapeHtml(data.code)}</pre>
            </div>
            ${data.context_used.length > 0 ? `
                <div class="context-summary">
                    <strong>Context used:</strong> ${data.context_used.length} chunks from the design library
                    ${data.context_used.map(c =>
                        `<br>&nbsp;&nbsp;- ${escapeHtml(c.file_path)} (${(c.similarity * 100).toFixed(0)}% match)`
                    ).join('')}
                </div>
            ` : ''}
        `;

        document.getElementById('copy-generated').addEventListener('click', () => {
            copyToClipboard(data.code);
        });
    } catch (err) {
        clearInterval(timer);
        status.innerHTML = '';
        output.innerHTML = `<div class="error-msg">Network error: ${escapeHtml(err.message)}</div>`;
    }

    submitBtn.disabled = false;
});

// ── Templates ───────────────────────────────────────────────────────
document.getElementById('templates-load').addEventListener('click', async () => {
    const category = document.getElementById('templates-category').value;
    const meta = document.getElementById('templates-meta');
    const grid = document.getElementById('templates-grid');

    meta.textContent = 'Loading...';
    grid.innerHTML = '';

    try {
        const res = await fetch(`${API}/templates/${encodeURIComponent(category)}`);
        if (!res.ok) {
            const err = await res.json();
            meta.innerHTML = '';
            grid.innerHTML = `<div class="error-msg">${escapeHtml(err.detail || 'Failed to load templates')}</div>`;
            return;
        }

        const data = await res.json();
        meta.textContent = `${data.count} ${data.category} templates found`;

        if (data.templates.length === 0) {
            grid.innerHTML = '<div class="empty-state">No templates found for this category.</div>';
            return;
        }

        grid.innerHTML = data.templates.map(t => `
            <div class="template-card">
                <div class="template-card-header">
                    <span class="template-card-path" title="${escapeHtml(t.file_path)}">${escapeHtml(t.file_path.split('/').slice(-2).join('/'))}</span>
                    <span class="badge badge-framework">${escapeHtml(t.framework)}</span>
                </div>
                <pre>${escapeHtml(t.preview)}</pre>
                <div class="result-actions">
                    <button class="btn btn-sm btn-ghost" onclick="copyToClipboard(${escapeHtml(JSON.stringify(JSON.stringify(t.preview)))})">Copy</button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        meta.innerHTML = '';
        grid.innerHTML = `<div class="error-msg">Network error: ${escapeHtml(err.message)}</div>`;
    }
});

// ── SEO Audit ───────────────────────────────────────────────────────
document.getElementById('seo-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const html = document.getElementById('seo-html').value.trim();
    const results = document.getElementById('seo-results');

    results.innerHTML = '<div class="results-meta">Auditing...</div>';

    try {
        const res = await fetch(`${API}/seo/audit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ html }),
        });

        if (!res.ok) {
            const err = await res.json();
            results.innerHTML = `<div class="error-msg">${escapeHtml(err.detail || 'Audit failed')}</div>`;
            return;
        }

        const data = await res.json();
        const scoreClass = data.score >= 80 ? 'good' : data.score >= 50 ? 'ok' : 'bad';

        results.innerHTML = `
            <div class="seo-score">
                <div class="score-number ${scoreClass}">${data.score}</div>
                <div class="score-breakdown">
                    <div>${data.passed_count} passed / ${data.total_checks} checks</div>
                    <div>${data.errors} errors / ${data.warnings} warnings</div>
                </div>
            </div>
            <ul class="seo-issues">
                ${data.issues.map(i => `
                    <li class="seo-issue">
                        <span class="issue-icon ${i.severity}">${i.severity === 'error' ? '!' : '?'}</span>
                        <span>${escapeHtml(i.message)}</span>
                    </li>
                `).join('')}
                ${data.passed.map(p => `
                    <li class="seo-issue">
                        <span class="issue-icon pass">&#10003;</span>
                        <span>${escapeHtml(p.message)}</span>
                    </li>
                `).join('')}
            </ul>
        `;
    } catch (err) {
        results.innerHTML = `<div class="error-msg">Network error: ${escapeHtml(err.message)}</div>`;
    }
});
