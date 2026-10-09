import { useEffect, useState } from 'react';
import { getHealth } from './api/client';

type ApiState = 'checking' | 'online' | 'offline';

export default function App() {
  const [status, setStatus] = useState<ApiState>('checking');
  const [version, setVersion] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setStatus('checking');
    const timeout = window.setTimeout(() => controller.abort(), 8000);
    getHealth(controller.signal)
      .then((health) => { if (active) { setVersion(health.version); setStatus('online'); } })
      .catch(() => { if (active) setStatus('offline'); })
      .finally(() => window.clearTimeout(timeout));
    return () => { active = false; controller.abort(); window.clearTimeout(timeout); };
  }, [attempt]);

  return (
    <div className="shell">
      <header className="header">
        <a className="brand" href="/" aria-label="Transaction Monitoring home">
          <span className="brand-mark" aria-hidden="true">T</span>
          <span>Transaction Monitoring<span className="brand-subtitle">PLATFORM</span></span>
        </a>
        <span className="environment">LOCAL DEVELOPMENT</span>
      </header>
      <main>
        <h1>A foundation for<br /><span>every transaction.</span></h1>
        <p className="intro">The platform is taking shape. Your API, background worker, and
          infrastructure now have a home in one workspace.</p>

        <section className="status-card" aria-labelledby="api-title">
          <div>
            <div className="eyebrow">SERVICE CONNECTION</div>
            <h2 id="api-title">FastAPI health</h2>
            <p aria-live="polite">
              <span className={`status-dot ${status}`} aria-hidden="true" />
              {status === 'checking' && 'Checking API connection…'}
              {status === 'online' && `API is responding · v${version}`}
              {status === 'offline' && 'API unavailable. Start the API service and check again.'}
            </p>
          </div>
          <button onClick={() => setAttempt((value) => value + 1)} disabled={status === 'checking'}>
            {status === 'checking' ? 'Checking…' : 'Check again'}
          </button>
        </section>

        <section className="workspace" aria-labelledby="workspace-title">
          <div className="section-heading"><h2 id="workspace-title">Your workspace</h2><span>BOOTSTRAP v0.1.0</span></div>
          <div className="grid">
            <article><span className="tile-number">01</span><h3>API service</h3><p>FastAPI application with an HTTP health endpoint and interactive documentation.</p><a href="/api/docs" target="_blank" rel="noreferrer">Open API docs <span aria-hidden="true">↗</span></a></article>
            <article><span className="tile-number">02</span><h3>Background worker</h3><p>A standalone Python process with graceful shutdown. Event processing comes next.</p><span className="tile-tag">BOOTSTRAP MODE</span></article>
            <article><span className="tile-number">03</span><h3>Infrastructure</h3><p>PostgreSQL, Redis, and Kafka are configured in Docker Compose with service health checks.</p><span className="tile-tag">CHECK WITH DOCKER COMPOSE PS</span></article>
          </div>
        </section>
        <footer>Transaction ingestion and anomaly detection will be implemented in later milestones.</footer>
      </main>
    </div>
  );
}
