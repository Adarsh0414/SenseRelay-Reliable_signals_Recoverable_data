import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, FormEvent, PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import { Link, NavLink, Route, Routes, useNavigate, useLocation } from 'react-router-dom';
import {
  Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, Bell, BookOpen, Check, CheckCircle2,
  ChevronDown, CircleAlert, CircleHelp, Cloud, Database, ExternalLink, FileCheck2, Gauge, Home,
  HardDrive, HeartPulse, Layers3, LockKeyhole, LogOut, Menu, RadioTower, RefreshCw, Search,
  Server, Settings2, ShieldCheck, Signal, WifiOff, X, Sun, Moon, Download,
} from 'lucide-react';
import { apiFetch, ApiError, getAuthSession, getDemoStatus, getEvents, getLosses, getResources, getResults, getSessions, getSummary, resetDemoDataset, seedDemoDataset } from './api';
import type { AuthSession, DemoStatus, IntegrityEvent, LossRecord, ResourceSnapshot, SessionRow, Summary, WindowResult } from './api';
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

type DashboardSection = 'overview' | 'sessions' | 'results' | 'integrity' | 'resources' | 'settings';
type ThemeMode = 'light' | 'dark';
type ThemeContextValue = { themeMode: ThemeMode; setThemeMode: (mode: ThemeMode) => void };
const ThemeContext = createContext<ThemeContextValue>({ themeMode: 'light', setThemeMode: () => undefined });
const API_DOCS_ENABLED = import.meta.env.VITE_API_DOCS_ENABLED !== 'false';

function useAppTheme() {
  return useContext(ThemeContext);
}

function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { themeMode, setThemeMode } = useAppTheme();
  const nextMode = themeMode === 'light' ? 'dark' : 'light';
  return (
    <button
      type="button"
      className={`icon-button theme-toggle ${compact ? 'theme-toggle-compact' : ''}`}
      onClick={() => setThemeMode(nextMode)}
      aria-label={`Switch to ${nextMode} mode`}
      title={`Switch to ${nextMode} mode`}
    >
      {themeMode === 'light' ? <Moon size={17} /> : <Sun size={17} />}
      {!compact && <span>{nextMode === 'dark' ? 'Dark mode' : 'Light mode'}</span>}
    </button>
  );
}

function readRefreshPreference(): number {
  try {
    const value = Number(window.localStorage.getItem('mayacardio.refreshIntervalSeconds'));
    return [10, 15, 30].includes(value) ? value : 10;
  } catch { return 10; }
}

function readThemePreference(): ThemeMode {
  try { return window.localStorage.getItem('mayacardio.theme') === 'dark' ? 'dark' : 'light'; }
  catch { return 'light'; }
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link to="/" className={`brand ${compact ? 'brand-compact' : ''}`} aria-label="MayaCardio home">
      <span className="brand-mark" aria-hidden="true">
        <HeartPulse size={25} strokeWidth={2.25} />
      </span>
      <span className="brand-wordmark">
        <strong>MayaCardio</strong>
        <small>Signal Operations</small>
      </span>
    </Link>
  );
}

function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);
  return (
    <header className="site-header">
      <div className="header-inner">
        <Brand />
        <button className="mobile-menu-button icon-button" onClick={() => setMenuOpen((open) => !open)} aria-label={menuOpen ? 'Close navigation' : 'Open navigation'} aria-expanded={menuOpen}>
          {menuOpen ? <X size={21} /> : <Menu size={21} />}
        </button>
        <nav className={`main-nav ${menuOpen ? 'main-nav-open' : ''}`} aria-label="Main navigation">
          <NavLink to="/" end onClick={closeMenu} className={({ isActive }) => isActive ? 'nav-link nav-link-home active' : 'nav-link nav-link-home'}><Home size={15} aria-hidden="true" /> Home</NavLink>
          <NavLink to="/architecture" onClick={closeMenu} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>Architecture</NavLink>
          <NavLink to="/security" onClick={closeMenu} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>Security</NavLink>
          <NavLink to="/docs" onClick={closeMenu} className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>Documentation</NavLink>
          <ThemeToggle compact />
          <Link to="/dashboard" onClick={closeMenu} className="button button-dark header-cta">Open dashboard <ArrowUpRight size={16} /></Link>
        </nav>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="site-footer">
      <div className="footer-inner">
        <Brand compact />
        <p>Engineering demonstration · Synthetic data only · Not for clinical use</p>
        <span className="footer-version">Web UI v1.0</span>
      </div>
    </footer>
  );
}

function PageFrame({ children, home = false }: { children: ReactNode; home?: boolean }) {
  return (
    <div className={`site-shell ${home ? 'site-shell-home' : ''}`}>
      <Header />
      <main className="site-main">{children}</main>
      {!home && <Footer />}
    </div>
  );
}

function SignalArtwork() {
  return (
    <div className="signal-artwork" aria-label="Decorative illustration of a synthetic signal waveform" role="img">
      <div className="artwork-topline"><span className="live-dot" /> SYNTHETIC SIGNAL PATH <span className="artwork-topline-right">400 Hz / SENSOR STREAM</span></div>
      <svg viewBox="0 0 560 210" className="signal-svg" aria-hidden="true">
        <defs><linearGradient id="signalFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#31bea7" stopOpacity=".23"/><stop offset="100%" stopColor="#31bea7" stopOpacity="0"/></linearGradient></defs>
        {[30, 70, 110, 150, 190].map((y) => <line key={y} x1="0" x2="560" y1={y} y2={y} stroke="#294050" strokeWidth="1" strokeDasharray="3 5" />)}
        {[40, 100, 160, 220, 280, 340, 400, 460, 520].map((x) => <line key={x} y1="0" y2="210" x1={x} x2={x} stroke="#294050" strokeWidth="1" strokeDasharray="3 5" />)}
        <path d="M0 123 L22 123 L31 115 L39 130 L48 123 L76 123 L88 119 L97 126 L110 123 L131 123 L145 120 L153 124 L165 123 L183 123 L191 110 L199 139 L207 123 L228 123 L242 122 L250 124 L276 123 L288 119 L296 128 L304 123 L333 123 L346 123 L355 64 L363 162 L373 123 L397 123 L411 120 L420 126 L429 123 L457 123 L470 121 L480 125 L489 123 L514 123 L530 123 L541 115 L550 130 L560 123 L560 210 L0 210 Z" fill="url(#signalFill)" />
        <path d="M0 123 L22 123 L31 115 L39 130 L48 123 L76 123 L88 119 L97 126 L110 123 L131 123 L145 120 L153 124 L165 123 L183 123 L191 110 L199 139 L207 123 L228 123 L242 122 L250 124 L276 123 L288 119 L296 128 L304 123 L333 123 L346 123 L355 64 L363 162 L373 123 L397 123 L411 120 L420 126 L429 123 L457 123 L470 121 L480 125 L489 123 L514 123 L530 123 L541 115 L550 130 L560 123" fill="none" stroke="#52d6c0" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        <circle cx="355" cy="64" r="5" fill="#c0fff4" stroke="#2fc7b0" strokeWidth="3" />
      </svg>
      <div className="artwork-footer"><div><span className="small-key">PIPELINE</span><strong>Capture → Persist → Process</strong></div><div><span className="small-key">RECOVERY</span><strong>Local-first · Replayable sync</strong></div></div>
    </div>
  );
}

function HomePage() {
  return (
    <PageFrame home>
      <section className="hero-section">
        <div className="hero-inner">
          <div className="hero-copy">
            <div className="eyebrow"><span className="eyebrow-dot" /> ENGINEERING DEMONSTRATION</div>
            <h1>Reliable signals.<br /><span>Visible by design.</span></h1>
            <p className="hero-description">An observable synthetic biosignal pipeline built to make data capture, processing, and recovery easier to inspect - even when connectivity drops.</p>
            <div className="hero-actions"><Link to="/dashboard" className="button button-primary">Explore live dashboard <ArrowRight size={17} /></Link><Link to="/architecture" className="button button-ghost">Explore architecture <ArrowUpRight size={16} /></Link></div>
            <div className="hero-proof"><span><CheckCircle2 size={16} /> Local persistence</span><span><CheckCircle2 size={16} /> Online / offline mode</span><span><CheckCircle2 size={16} /> Explicit loss ledger</span></div>
          </div>
          <SignalArtwork />
        </div>
      </section>
      <section className="notice-strip"><div className="notice-inner"><ShieldCheck size={19} /><p><strong>Built for engineering verification.</strong> Synthetic data only. This project uses synthetic signals and is not a clinically validated monitoring or diagnostic system.</p><Link to="/security">Read the scope note <ArrowRight size={14} /></Link></div></section>
      <section className="section content-section">
        <div className="section-heading"><div><div className="eyebrow eyebrow-light">THE SYSTEM</div><h2>Resilience you can inspect.</h2></div><p>Designed around durable collection and transparent operational state - not a dashboard that hides what it cannot verify.</p></div>
        <div className="feature-grid">
          <FeatureCard icon={<Database />} number="01" title="Durable local capture" description="Samples are committed to local SQLite storage before synchronization is considered complete." />
          <FeatureCard icon={<WifiOff />} number="02" title="Offline-aware processing" description="The pipeline keeps collecting locally during cloud interruptions and records its processing mode." />
          <FeatureCard icon={<Cloud />} number="03" title="Recoverable synchronization" description="Queued records can be retried and reconciled with cloud storage without treating an attempt as an acknowledgement." />
          <FeatureCard icon={<FileCheck2 />} number="04" title="Transparent data quality" description="Missing samples and integrity events are exposed instead of filling gaps with invented values." />
        </div>
      </section>
      <section className="architecture-preview"><div className="section content-section architecture-inner"><div className="section-heading"><div><div className="eyebrow eyebrow-light">END-TO-END FLOW</div><h2>One pipeline. Clear boundaries.</h2></div><Link className="text-link" to="/architecture">View full architecture <ArrowRight size={16} /></Link></div><div className="flow-row"><FlowStep icon={<RadioTower />} title="Synthetic source" detail="TCP · NDJSON" /><div className="flow-connector" /><FlowStep icon={<Database />} title="Device store" detail="SQLite · WAL" /><div className="flow-connector" /><FlowStep icon={<Activity />} title="Processor" detail="1-second windows" /><div className="flow-connector" /><FlowStep icon={<Cloud />} title="Cloud API" detail="Persistent storage" /><div className="flow-connector" /><FlowStep icon={<Gauge />} title="Dashboard" detail="Verified telemetry" /></div></div></section>
      <section className="section content-section bottom-cta"><div><div className="eyebrow eyebrow-light">START WITH THE DATA</div><h2>See what the running system can actually prove.</h2><p>The dashboard reads from the application's API. When the device database or a metric is unavailable, it says so rather than inventing a value.</p></div><Link to="/dashboard" className="button button-primary">Open operations dashboard <ArrowRight size={17} /></Link></section>
      <PwaInstallLauncher />
    </PageFrame>
  );
}

function FeatureCard({ icon, number, title, description }: { icon: ReactNode; number: string; title: string; description: string }) {
  return <article className="feature-card"><div className="feature-card-top"><span className="feature-icon">{icon}</span><span className="feature-number">{number}</span></div><h3>{title}</h3><p>{description}</p></article>;
}

function FlowStep({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return <div className="flow-step"><span className="flow-icon">{icon}</span><strong>{title}</strong><small>{detail}</small></div>;
}

type InstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
};

type DragPosition = { left: number; top: number };
type DragState = { pointerX: number; pointerY: number; left: number; top: number; moved: boolean };

function PwaInstallLauncher() {
  const [position, setPosition] = useState<DragPosition | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [installed, setInstalled] = useState(false);
  const promptRef = useRef<InstallPromptEvent | null>(null);
  const dragRef = useRef<DragState | null>(null);
  const draggedRef = useRef(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem('mayacardio.pwaInstallPosition');
      if (stored) {
        const parsed = JSON.parse(stored) as DragPosition;
        if (Number.isFinite(parsed.left) && Number.isFinite(parsed.top)) {
          setPosition({
            left: Math.max(8, Math.min(window.innerWidth - 58, parsed.left)),
            top: Math.max(82, Math.min(window.innerHeight - 66, parsed.top)),
          });
        }
      }
    } catch { /* The install control remains usable when browser storage is unavailable. */ }

    const standalone = window.matchMedia('(display-mode: standalone)').matches || Boolean((navigator as Navigator & { standalone?: boolean }).standalone);
    setInstalled(standalone);
    const onBeforeInstall = (event: Event) => {
      event.preventDefault();
      promptRef.current = event as InstallPromptEvent;
    };
    const onInstalled = () => {
      setInstalled(true);
      promptRef.current = null;
      setShowHelp(false);
    };
    window.addEventListener('beforeinstallprompt', onBeforeInstall);
    window.addEventListener('appinstalled', onInstalled);
    const onResize = () => setPosition((current) => current ? ({
      left: Math.max(8, Math.min(window.innerWidth - 58, current.left)),
      top: Math.max(82, Math.min(window.innerHeight - 66, current.top)),
    }) : null);
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall);
      window.removeEventListener('appinstalled', onInstalled);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  const handleInstall = async () => {
    if (draggedRef.current) {
      draggedRef.current = false;
      return;
    }
    const installPrompt = promptRef.current;
    if (!installPrompt) {
      setShowHelp((current) => !current);
      return;
    }
    try {
      await installPrompt.prompt();
      const choice = await installPrompt.userChoice;
      if (choice.outcome === 'accepted') {
        setInstalled(true);
        promptRef.current = null;
      } else {
        setShowHelp(true);
      }
    } catch {
      setShowHelp(true);
    }
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    dragRef.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      left: position?.left ?? rect.left,
      top: position?.top ?? rect.top,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const deltaX = event.clientX - drag.pointerX;
    const deltaY = event.clientY - drag.pointerY;
    if (Math.abs(deltaX) + Math.abs(deltaY) > 4) drag.moved = true;
    if (!drag.moved) return;
    setPosition({
      left: Math.max(8, Math.min(window.innerWidth - 58, drag.left + deltaX)),
      top: Math.max(82, Math.min(window.innerHeight - 66, drag.top + deltaY)),
    });
  };

  const handlePointerUp = () => {
    const drag = dragRef.current;
    if (!drag) return;
    dragRef.current = null;
    if (drag.moved) {
      draggedRef.current = true;
      try {
        window.localStorage.setItem('mayacardio.pwaInstallPosition', JSON.stringify(position));
      } catch { /* A positioning preference is not required for installation. */ }
      window.setTimeout(() => { draggedRef.current = false; }, 150);
    }
  };

  if (installed) return null;
  const style: CSSProperties | undefined = position ? { left: `${position.left}px`, top: `${position.top}px`, right: 'auto', bottom: 'auto' } : undefined;
  return (
    <div className="pwa-install-float" style={style}>
      {showHelp && <div className="pwa-install-help" role="status">
        <strong>Install MayaCardio</strong>
        <p>If your browser has not offered installation yet, open the browser menu and choose <b>Apps</b> or <b>Install this site as an app</b>, if available.</p>
        <button type="button" className="pwa-help-dismiss" onClick={() => setShowHelp(false)}>Got it</button>
      </div>}
      <button
        type="button"
        className="pwa-install-button"
        aria-label="Install MayaCardio as an app. Drag to move this button."
        title="Install MayaCardio (drag to move)"
        onClick={() => void handleInstall()}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
      >
        <Download size={19} aria-hidden="true" />
      </button>
      <span className="pwa-install-caption" aria-hidden="true">Install app</span>
    </div>
  );
}

function InfoPage({ kind }: { kind: 'architecture' | 'security' | 'docs' }) {
  const content = {
    architecture: {
      eyebrow: 'SYSTEM DESIGN', title: 'A pipeline designed around durable boundaries.', intro: 'The UI is an observer, not the source of truth. Acquisition, local persistence, processing, and remote storage remain in the Python service.',
      cards: [
        { title: '01 · Acquisition', text: 'The collector talks to the synthetic sensor over TCP, validates the reply checksum, and tracks sessions, indices, duplicates, and reported gaps.' },
        { title: '02 · Local persistence', text: 'SQLite is the local record for accepted samples and explicit loss records. Transaction commits form the application’s persistence boundary.' },
        { title: '03 · Processing', text: 'One-second windows are calculated with the shared processing implementation. The same defined rules are used for online and offline results.' },
        { title: '04 · Synchronization', text: 'The device service sends durable batches to the cloud API. Retry and reconciliation behavior belongs to the backend, not the browser.' },
        { title: '05 · Presentation', text: 'The dashboard uses read-only API endpoints for summaries, session lists, results, losses, resource snapshots, and events.' },
      ],
    },
    security: {
      eyebrow: 'SECURITY & SCOPE', title: 'Clear access boundaries. Honest limits.', intro: 'This is a software engineering demonstration using synthetic biosignal data. It is not a medical device and should not be used for diagnosis, treatment, or patient care.',
      cards: [
        { title: 'Separate credentials', text: 'Device-to-cloud ingestion uses a server-side bearer token. Browser access uses a separate signed HttpOnly dashboard session when authentication is configured.' },
        { title: 'Local-only development fallback', text: 'When dashboard credentials are not configured, the dashboard API only allows loopback clients. Remote access is rejected until credentials are set.' },
        { title: 'Browser protections', text: 'The API sets baseline security headers, validates login origin, applies SameSite and HttpOnly cookie flags, and rate-limits failed sign-in attempts in process memory.' },
        { title: 'Deployment responsibility', text: 'Public deployments must either keep dashboard credentials enabled or deliberately use DASHBOARD_PUBLIC_READ_ONLY for a synthetic-only portfolio demo. Public demo mode allows dashboard reads only, blocks demo write/reset actions, and leaves device ingestion separately protected by its server-side token.' },
        { title: 'Not certified or clinically validated', text: 'No HIPAA, GDPR, clinical accuracy, regulatory approval, or medical safety certification is claimed. Formal threat modelling and deployment review are still required before public production use.' },
      ],
    },
    docs: {
      eyebrow: 'DEVELOPER RESOURCES', title: 'Built to run, inspect, and explain.', intro: 'Use the repository documentation and API reference to understand the real service contracts and the limits of the development simulation.',
      cards: [
        { title: 'README', text: 'Primary setup, local demo, command-line interface, and assessment requirements. Open README.md from the repository root.' },
        { title: 'API reference', text: 'When the FastAPI service is running locally, its interactive API reference is available at http://127.0.0.1:8000/docs.' },
        { title: 'Runbook', text: 'The Windows step-by-step guide covers virtual environment setup, running three local processes, testing, and GitHub publishing.' },
        { title: 'Assessment evidence', text: 'See docs/TEST_EVIDENCE.md for what has been tested and what still needs official mock, ARM64, power-loss, timing, and long-outage verification.' },
        { title: 'Synthetic demo only', text: 'The included demo mock is a development fixture. Final acceptance testing requires the official biosignal-mock and check_ground_truth tool.' },
      ],
    },
  }[kind];
  const Icon = kind === 'architecture' ? Layers3 : kind === 'security' ? ShieldCheck : BookOpen;
  return <PageFrame><section className="info-hero"><div className="content-width"><div className="eyebrow eyebrow-light"><Icon size={15} /> {content.eyebrow}</div><h1>{content.title}</h1><p>{content.intro}</p></div></section><section className="section content-section info-grid">{content.cards.map((card, index) => <article className="info-card" key={card.title}><span className="info-index">{String(index + 1).padStart(2, '0')}</span><h2>{card.title}</h2><p>{card.text}</p></article>)}</section><section className="section content-section info-actions"><Link className="button button-dark" to="/dashboard">Open dashboard <ArrowRight size={16} /></Link>{kind === 'docs' && (API_DOCS_ENABLED ? <a className="button button-ghost" href="/docs" target="_blank" rel="noreferrer">Open API reference <ExternalLink size={15} /></a> : <span className="muted-copy">API reference is disabled by this deployment's configuration.</span>)}</section></PageFrame>;
}

function DashboardGate() {
  const [auth, setAuth] = useState<AuthSession | null>(null);
  const [loadError, setLoadError] = useState('');
  const [checking, setChecking] = useState(true);
  const refreshAuth = useCallback(async () => {
    setChecking(true);
    try { setAuth(await getAuthSession()); setLoadError(''); }
    catch (error) { setLoadError(error instanceof Error ? error.message : 'Could not reach the API'); }
    finally { setChecking(false); }
  }, []);
  useEffect(() => { void refreshAuth(); }, [refreshAuth]);
  if (checking) return <PageFrame><div className="center-state"><RefreshCw className="spin" size={24} /><h1>Checking dashboard access…</h1></div></PageFrame>;
  if (loadError) return <PageFrame><ErrorState title="The API is not reachable" detail="Start the FastAPI cloud service, then retry. A Vite page by itself does not run the pipeline backend." onRetry={() => void refreshAuth()} /></PageFrame>;
  if (!auth?.authenticated) {
    if (auth?.needs_configuration || !auth?.configured) return <PageFrame><AuthSetupNotice /></PageFrame>;
    return <PageFrame><LoginPanel onSignedIn={() => void refreshAuth()} /></PageFrame>;
  }
  return <DashboardShell username={auth.username || 'local-development'} publicReadOnly={Boolean(auth.public_read_only)} onLogout={auth.configured ? async () => { try { await apiFetch('/api/auth/logout', { method: 'POST' }); } finally { await refreshAuth(); } } : undefined} />;
}

function AuthSetupNotice() {
  return <section className="auth-page"><div className="auth-card"><span className="auth-icon"><LockKeyhole size={23} /></span><div className="eyebrow eyebrow-light">ACCESS CONFIGURATION REQUIRED</div><h1>Dashboard access is not configured.</h1><p>This server is not allowing remote dashboard access because dashboard credentials are missing or incomplete. For local development, open the site from the same computer as the API.</p><div className="code-panel"><code>DASHBOARD_USERNAME</code><code>DASHBOARD_PASSWORD</code><code>DASHBOARD_SESSION_SECRET</code></div><p className="muted-copy">Set all three server-side variables. The session secret must contain at least 32 characters. Use HTTPS and set <code>DASHBOARD_COOKIE_SECURE=true</code> for a public deployment.</p><button className="button button-dark" onClick={() => window.location.reload()}>Check again <RefreshCw size={15} /></button></div></section>;
}

function LoginPanel({ onSignedIn }: { onSignedIn: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { await apiFetch('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }); onSignedIn(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Sign-in failed'); }
    finally { setBusy(false); }
  }
  return <section className="auth-page"><div className="auth-card"><span className="auth-icon"><ShieldCheck size={23} /></span><div className="eyebrow eyebrow-light">PROTECTED WORKSPACE</div><h1>Sign in to Signal Operations.</h1><p>Use the dashboard credentials configured by the server administrator. Device ingestion credentials are not dashboard login credentials.</p><form onSubmit={submit} className="login-form"><label htmlFor="login-username">Username</label><input id="login-username" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required maxLength={200} /><label htmlFor="login-password">Password</label><input id="login-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required maxLength={1024} />{error && <p className="form-error" role="alert"><CircleAlert size={15} />{error}</p>}<button className="button button-primary login-submit" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'} <ArrowRight size={16} /></button></form><p className="auth-footnote"><LockKeyhole size={14} /> Session cookie is HttpOnly and server-signed.</p></div></section>;
}

type DashboardData = {
  summary: Summary | null;
  sessions: SessionRow[];
  totalSessions: number;
  events: IntegrityEvent[];
  resources: ResourceSnapshot | null;
  demoStatus: DemoStatus | null;
  publicReadOnly: boolean;
  demoBusy: boolean;
  demoMessage: string;
  demoError: string;
  seedDemo: () => Promise<void>;
  resetDemo: () => Promise<void>;
  isLoading: boolean;
  lastUpdated: number | null;
  error: string;
  refresh: () => Promise<void>;
};

function DashboardShell({ username, publicReadOnly = false, onLogout }: { username: string; publicReadOnly?: boolean; onLogout?: () => void }) {
  const [activeSection, setActiveSection] = useState<DashboardSection>('overview');
  const [summary, setSummary] = useState<Summary | null>(null);
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [totalSessions, setTotalSessions] = useState(0);
  const [events, setEvents] = useState<IntegrityEvent[]>([]);
  const [resources, setResources] = useState<ResourceSnapshot | null>(null);
  const [demoStatus, setDemoStatus] = useState<DemoStatus | null>(null);
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoMessage, setDemoMessage] = useState('');
  const [demoError, setDemoError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [selectedSession, setSelectedSession] = useState('');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [refreshIntervalSeconds, setRefreshIntervalSeconds] = useState(readRefreshPreference);
  const { themeMode, setThemeMode } = useAppTheme();
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    try {
      const [summaryResponse, sessionsResponse, eventsResponse, demoResponse] = await Promise.all([getSummary(), getSessions(), getEvents(), getDemoStatus()]);
      setSummary(summaryResponse); setSessions(sessionsResponse.items); setTotalSessions(sessionsResponse.total); setEvents(eventsResponse); setDemoStatus(demoResponse);
      setSelectedSession((current) => current || (demoResponse.seeded ? demoResponse.session_id : '') || summaryResponse.device.latest_session_id || summaryResponse.cloud.latest_session_id || sessionsResponse.items[0]?.session_id || '');
      setError(''); setLastUpdated(Date.now());
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Unable to refresh dashboard';
      setError(message);
      if (caught instanceof ApiError && caught.status === 401) { navigate('/dashboard', { replace: true }); window.location.reload(); }
    } finally { setIsLoading(false); }
    try { setResources(await getResources()); } catch { /* Resource view shows unavailable rather than made-up values. */ }
  }, [navigate]);

  const seedDemo = useCallback(async () => {
    setDemoBusy(true); setDemoError(''); setDemoMessage('');
    try {
      const result = await seedDemoDataset();
      setDemoMessage(result.already_present
        ? `The saved fixture was already present. Verified ${result.sample_rows.toLocaleString()} persisted sample rows across both stores.`
        : `Stored ${result.sample_rows.toLocaleString()} deterministic sample rows, ${result.window_count} processed windows, one explicit data-gap record, and a SHA-256-verified JSONL dataset.`);
      await refresh();
      setSelectedSession(result.session_id);
    } catch (caught) {
      setDemoError(caught instanceof Error ? caught.message : 'Unable to create the synthetic demo dataset.');
    } finally { setDemoBusy(false); }
  }, [refresh]);

  const resetDemo = useCallback(async () => {
    if (!window.confirm('Remove only the fixed synthetic demo session from the local/cloud databases and delete its generated JSONL file? Other sessions will be preserved.')) return;
    setDemoBusy(true); setDemoError(''); setDemoMessage('');
    try {
      const result = await resetDemoDataset();
      setSelectedSession('');
      setDemoMessage(result.notice);
      await refresh();
    } catch (caught) {
      setDemoError(caught instanceof Error ? caught.message : 'Unable to reset the synthetic demo dataset.');
    } finally { setDemoBusy(false); }
  }, [refresh]);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => { void refresh(); }, refreshIntervalSeconds * 1000);
    return () => window.clearInterval(interval);
  }, [refresh, refreshIntervalSeconds]);

  useEffect(() => {
    try {
      window.localStorage.setItem('mayacardio.refreshIntervalSeconds', String(refreshIntervalSeconds));
    } catch { /* Preferences remain active for this page load if storage is unavailable. */ }
  }, [refreshIntervalSeconds]);

  const data: DashboardData = { summary, sessions, totalSessions, events, resources, demoStatus, publicReadOnly, demoBusy, demoMessage, demoError, seedDemo, resetDemo, isLoading, lastUpdated, error, refresh };
  const navItems: { id: DashboardSection; label: string; icon: ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <Gauge size={17} /> },
    { id: 'sessions', label: 'Sessions', icon: <Layers3 size={17} /> },
    { id: 'results', label: 'Processing results', icon: <Activity size={17} /> },
    { id: 'integrity', label: 'Data integrity', icon: <ShieldCheck size={17} /> },
    { id: 'resources', label: 'Host resources', icon: <Server size={17} /> },
    { id: 'settings', label: 'Settings & help', icon: <Settings2 size={17} /> },
  ];
  const choose = (section: DashboardSection) => { setActiveSection(section); setMobileNavOpen(false); };

  return (
    <div className={`dashboard-layout ${themeMode === 'dark' ? 'dashboard-theme-dark' : ''}`}>
      <header className="dashboard-topbar"><div className="dashboard-brand-wrap"><Brand compact /><span className="workspace-divider" /><span className="workspace-label">Operations console</span></div><div className="topbar-right"><span className="environment-pill"><span className="live-dot" /> Synthetic environment</span><span className="user-chip"><span className="avatar-dot">{username.slice(0, 1).toUpperCase()}</span><span>{username}</span></span><ThemeToggle compact />{onLogout && <button className="icon-button logout-button" onClick={onLogout} aria-label="Sign out" title="Sign out"><LogOut size={17} /></button>}<Link to="/" className="button button-outline dashboard-home-link" aria-label="Go to Home page" title="Go to Home page"><Home size={15} aria-hidden="true" /><span>Home</span></Link></div></header>
      <div className="dashboard-body">
        <aside className={`dashboard-sidebar ${mobileNavOpen ? 'sidebar-open' : ''}`}>
          <div className="sidebar-caption">WORKSPACE</div>
          <div className="sidebar-nav" role="navigation" aria-label="Dashboard sections">
            {navItems.map((item) => <button key={item.id} className={`sidebar-link ${activeSection === item.id ? 'selected' : ''}`} onClick={() => choose(item.id)}>{item.icon}<span>{item.label}</span>{activeSection === item.id && <span className="sidebar-selected-bar" />}</button>)}
          </div>
          <div className="sidebar-bottom"><div className="sidebar-health-icon"><ShieldCheck size={17} /></div><strong>Integrity is visible.</strong><p>The dashboard reports what the API can verify, and flags what is unavailable.</p><Link to="/security">Security notes <ArrowRight size={13} /></Link><div className="sidebar-pipeline"><span className="live-dot" /> Pipeline API <span>v0.2</span></div></div>
        </aside>
        {mobileNavOpen && <button className="sidebar-scrim" aria-label="Close dashboard navigation" onClick={() => setMobileNavOpen(false)} />}
        <main className="dashboard-main">
          <button className="mobile-dashboard-menu button button-outline" onClick={() => setMobileNavOpen((open) => !open)}><Menu size={16} /> Sections <ChevronDown size={15} /></button>
          {error && <div className="alert-banner" role="alert"><CircleAlert size={17} /><div><strong>Dashboard refresh failed</strong><span>{error}. Showing the last successfully loaded values, if any.</span></div><button className="button button-sm button-outline" onClick={() => void refresh()}>Retry</button></div>}
          {activeSection === 'overview' && <OverviewView data={data} sessions={sessions} onChooseSession={(id) => { setSelectedSession(id); choose('results'); }} />}
          {activeSection === 'sessions' && <SessionsView data={data} selectedSession={selectedSession} setSelectedSession={setSelectedSession} onViewResults={(id) => { setSelectedSession(id); choose('results'); }} />}
          {activeSection === 'results' && <ResultsView data={data} sessions={sessions} selectedSession={selectedSession} setSelectedSession={setSelectedSession} />}
          {activeSection === 'integrity' && <IntegrityView data={data} selectedSession={selectedSession} setSelectedSession={setSelectedSession} sessions={sessions} />}
          {activeSection === 'resources' && <ResourcesView data={data} />}
          {activeSection === 'settings' && <SettingsView data={data} refreshIntervalSeconds={refreshIntervalSeconds} setRefreshIntervalSeconds={setRefreshIntervalSeconds} themeMode={themeMode} setThemeMode={setThemeMode} />}
          <div className="dashboard-footnote"><span><LockKeyhole size={13} /> {publicReadOnly ? 'Public read-only demo · actions that modify the dataset are disabled' : 'Monitoring views are read-only; demo controls affect only the fixed synthetic fixture'}</span><span>Auto-refresh every {refreshIntervalSeconds} seconds{data.lastUpdated ? ` · Updated ${formatRelative(data.lastUpdated / 1000)}` : ''}</span></div>
        </main>
      </div>
    </div>
  );
}

function PageTitle({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <div className="dashboard-page-title"><div><div className="eyebrow eyebrow-light">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action && <div className="page-title-actions">{action}</div>}</div>;
}

function OverviewView({ data, sessions, onChooseSession }: { data: DashboardData; sessions: SessionRow[]; onChooseSession: (id: string) => void }) {
  const latestSession = data.demoStatus?.seeded ? data.demoStatus.session_id : data.summary?.device.latest_session_id || data.summary?.cloud.latest_session_id || sessions[0]?.session_id || '';
  const [results, setResults] = useState<WindowResult[]>([]);
  useEffect(() => { let current = true; if (latestSession) void getResults(latestSession).then((body) => { if (current) setResults(body.items.slice(-120)); }).catch(() => { if (current) setResults([]); }); else setResults([]); return () => { current = false; }; }, [latestSession, data.lastUpdated]);
  const chartRows = results.map((row) => ({ window: row.window_index, heartRate: row.heart_rate, missing: row.missing_1 + row.missing_2, complete: row.complete ? 1 : 0 }));
  const device = data.summary?.device;
  const cloud = data.summary?.cloud;
  const demo = data.demoStatus?.seeded ? data.demoStatus : null;
  const deviceSamples = demo ? demo.device.sample_rows : device?.available ? device.samples : null;
  const cloudSamples = demo ? demo.cloud.sample_rows : cloud?.samples;
  const backlog = demo ? demo.device.pending_samples : device?.available ? device.backlog : null;
  const processedWindows = demo ? demo.cloud.results : cloud?.results;
  const lossCount = demo ? demo.cloud.loss_records : cloud?.losses;
  const syncedPercentage = deviceSamples !== null && deviceSamples !== undefined && deviceSamples > 0 && backlog !== null && backlog !== undefined ? Math.max(0, Math.min(100, ((deviceSamples - backlog) / Math.max(1, deviceSamples)) * 100)) : null;
  return <>
    <div className="dashboard-heading-row"><PageTitle eyebrow="OPERATIONS / OVERVIEW" title="System overview" description="A live view of sample persistence, cloud ingestion, processing activity, and data quality." /><div className="heading-status"><span className={`status-dot ${data.error ? 'status-dot-danger' : 'status-dot-success'}`} />{data.error ? 'API unavailable' : 'API reachable'}<button className="icon-button refresh-button" title="Refresh now" aria-label="Refresh dashboard" onClick={() => void data.refresh()}><RefreshCw size={16} /></button></div></div>
    <div className="demo-notice"><Signal size={17} /><div><strong>{data.demoStatus?.seeded ? 'Deterministic demo dataset persisted' : 'Synthetic demonstration environment'}</strong><span>{data.demoStatus?.seeded ? `Session ${data.demoStatus.session_id} is stored in the device SQLite store and the cloud-service SQLite database on this local demo. Source file: data/${data.demoStatus.dataset_file}. Every chart and table below reads records from these stores; offline labels are staged fixture metadata, not a claim of a live outage.` : data.demoStatus?.bundled_fixture_available ? 'The checked-in seed-7 synthetic source is ready. Load it once to create the runtime JSONL file and populate both SQLite stores, then inspect the same session across every dashboard page.' : 'No dashboard-only placeholder metrics are injected. Load a repeatable seed-7 dataset to populate the local file and both SQLite stores, then inspect the same session across every dashboard page.'}</span></div>{data.demoStatus?.enabled && (data.demoStatus.seeded ? <a className="button button-outline demo-action-button" href="/api/dashboard/demo/download"><ArrowDownToLine size={14} /> Download JSONL</a> : !data.publicReadOnly && <button className="button button-dark demo-action-button" disabled={data.demoBusy} onClick={() => void data.seedDemo()}>{data.demoBusy ? <RefreshCw size={14} className="spin" /> : <Database size={14} />}{data.demoBusy ? 'Storing dataset…' : 'Load demo dataset'}</button>)}<span className="notice-label">{data.demoStatus?.seeded ? 'STORED' : 'DEMO'}</span></div>
    {data.demoError && <div className="alert-banner" role="alert"><CircleAlert size={17} /><div><strong>Demo data action failed</strong><span>{data.demoError}</span></div><button className="button button-sm button-outline" onClick={() => void data.refresh()}>Retry status</button></div>}
    {data.demoMessage && <div className="demo-feedback" role="status"><CheckCircle2 size={16} /><span>{data.demoMessage}</span></div>}
    {data.demoStatus?.enabled && <div className="demo-fixture-meta"><div><span className="small-key">{data.demoStatus.seeded ? 'PERSISTED FIXTURE' : 'REPRODUCIBLE FIXTURE'}</span><strong>{data.demoStatus.duration_seconds} seconds · {data.demoStatus.sample_rate_hz} Hz · seed {data.demoStatus.seed}</strong><span>{formatCount(data.demoStatus.sample_rows)} expected sample rows ({formatCount(data.demoStatus.sensor_1_sample_count)} Sensor 1 · {formatCount(data.demoStatus.sensor_2_sample_count)} Sensor 2) · {data.demoStatus.window_count} derived windows · Sensor {data.demoStatus.controlled_gap.sensor} gap at {data.demoStatus.controlled_gap.from_index.toLocaleString()}-{data.demoStatus.controlled_gap.to_index.toLocaleString()} · offline windows {data.demoStatus.offline_windows.join(', ')}</span></div><span className="fixture-hash-note">{data.demoStatus.seeded ? 'Loaded from local JSONL + both SQLite stores' : data.demoStatus.bundled_fixture_available ? 'Bundled source → runtime file + both stores' : 'Generated with fixed seed and persisted'}</span></div>}
    <div className="metric-grid">
      <MetricCard label={demo ? 'Demo session · device rows' : 'Samples on device'} value={deviceSamples} icon={<Database size={18} />} detail={demo ? 'Persisted rows for the selected fixture' : device?.available ? `${formatCount(device.backlog)} awaiting upload` : 'Device database not available on this host'} tone="teal" />
      <MetricCard label={demo ? 'Demo session · cloud rows' : 'Samples in cloud'} value={cloudSamples} icon={<Cloud size={18} />} detail={demo ? 'Same fixture in the local cloud-service SQLite store' : `${formatCount(cloud?.sessions)} sessions recorded`} tone="blue" />
      <MetricCard label={demo ? 'Demo session · pending rows' : 'Upload backlog'} value={backlog} icon={<ArrowDownToLine size={18} />} detail={demo ? 'Preloaded in both stores; not a live-sync timing measurement' : backlog === 0 ? 'No local sample rows pending' : backlog === null ? 'Unavailable from this host' : 'Sample rows not yet acknowledged'} tone={backlog === 0 ? 'green' : 'amber'} />
      <MetricCard label={demo ? 'Demo session · windows' : 'Processed windows'} value={processedWindows} icon={<Activity size={18} />} detail={demo ? `${formatCount(lossCount)} explicit loss record in this fixture` : `${formatCount(lossCount)} loss records in cloud`} tone="violet" />
    </div>
    <div className="dashboard-columns"><section className="panel chart-panel"><div className="panel-heading"><div><h2>Recent processing</h2><p>{latestSession ? `Session ${latestSession}` : 'No session available yet'}</p></div><span className="panel-pill">ACTUAL RESULTS</span></div>{chartRows.length ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={255}><LineChart data={chartRows} margin={{ top: 8, right: 15, left: -17, bottom: 2 }}><CartesianGrid strokeDasharray="3 5" stroke="#e9eff2" vertical={false} /><XAxis dataKey="window" tick={{ fill: '#72818f', fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis yAxisId="left" tick={{ fill: '#72818f', fontSize: 11 }} axisLine={false} tickLine={false} width={38} /><YAxis yAxisId="right" orientation="right" tick={{ fill: '#72818f', fontSize: 11 }} axisLine={false} tickLine={false} width={35} /><Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #e2eaf0', boxShadow: '0 10px 30px rgba(18,38,54,.08)' }} /><Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} /><Line yAxisId="left" type="monotone" dataKey="heartRate" name="Heart rate (bpm)" stroke="#199f8b" strokeWidth={2.5} dot={false} connectNulls={false} activeDot={{ r: 4 }} /><Line yAxisId="right" type="monotone" dataKey="missing" name="Missing samples" stroke="#e09b43" strokeWidth={1.8} dot={false} activeDot={{ r: 3 }} /></LineChart></ResponsiveContainer></div> : <EmptyState icon={<Activity />} title="No processing results to chart" detail="Start a sensor session and allow the pipeline to produce window results. This chart never uses made-up metrics." />}</section>
      <section className="panel state-panel"><div className="panel-heading"><div><h2>Pipeline state</h2><p>Most recent known state</p></div><span className="panel-icon"><Gauge size={18} /></span></div><div className="state-line"><span>Device database</span><StatusPill state={device?.available ? 'available' : 'unavailable'} label={device?.available ? 'Available' : 'Unavailable'} /></div><div className="state-line"><span>Processing mode</span><StatusPill state={demo ? 'online' : device?.mode === 'online' ? 'online' : device?.mode === 'offline' ? 'offline' : 'unknown'} label={demo ? 'Mixed windows' : device?.mode || 'Unknown'} /></div>{demo && <div className="state-line"><span>Window modes</span><strong>{demo.window_count - demo.offline_windows.length} online · {demo.offline_windows.length} offline</strong></div>}<div className="state-line"><span>Last sample received</span><strong>{formatTime(device?.last_sample_at ?? cloud?.last_sample_at)}</strong></div><div className="state-line"><span>Latest known session</span><strong className="truncate-value" title={latestSession}>{latestSession || '-'}</strong></div><div className="sync-summary"><div className="sync-summary-head"><span>Device rows acknowledged</span><strong>{syncedPercentage === null ? '-' : `${syncedPercentage.toFixed(1)}%`}</strong></div><div className="progress-track"><div className="progress-fill" style={{ width: `${syncedPercentage ?? 0}%` }} /></div><p>{syncedPercentage === null ? 'Requires the device database on this host.' : 'Derived from local sample count and current upload backlog.'}</p></div><Link className="panel-link" to="/architecture">Understand the data flow <ArrowRight size={15} /></Link></section></div>
    <section className="panel table-panel"><div className="panel-heading"><div><h2>Recent sessions</h2><p>Sessions found in local and cloud storage, when available.</p></div><button className="button button-outline button-sm" onClick={() => onChooseSession(sessions[0]?.session_id || latestSession)} disabled={!sessions.length && !latestSession}>View results <ArrowRight size={14} /></button></div><SessionsTable sessions={sessions.slice(0, 5)} onViewResults={onChooseSession} /></section>
    <div className="supporting-note"><CircleHelp size={16} /><p>Missing device metrics are intentionally shown as unavailable when the API host cannot access the local device database. Host metrics are separate from constrained Raspberry Pi measurements.</p></div>
  </>;
}

function MetricCard({ label, value, icon, detail, tone }: { label: string; value: number | null | undefined; icon: ReactNode; detail: string; tone: string }) {
  return <article className="metric-card"><div className="metric-card-top"><span className={`metric-icon metric-${tone}`}>{icon}</span><span className="metric-card-indicator"><span className="status-dot status-dot-muted" /> Verified API field</span></div><div className="metric-label">{label}</div><div className="metric-value">{formatCount(value)}</div><div className="metric-detail">{detail}</div></article>;
}

function StatusPill({ state, label }: { state: string; label: string }) {
  return <span className={`status-pill status-${state}`}><span />{label}</span>;
}

function SessionsView({ data, selectedSession, setSelectedSession, onViewResults }: { data: DashboardData; selectedSession: string; setSelectedSession: (id: string) => void; onViewResults: (id: string) => void }) {
  const [search, setSearch] = useState('');
  const filtered = useMemo(() => sessionsFilter(data.sessions, search), [data.sessions, search]);
  return <><PageTitle eyebrow="OPERATIONS / SESSIONS" title="Sessions" description="Browse known sessions and inspect the sample, loss, and result counts the API can verify." action={<button className="button button-outline" onClick={() => void data.refresh()}><RefreshCw size={15} /> Refresh</button>} /><div className="session-toolbar"><div className="search-box"><Search size={17} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search session ID…" aria-label="Search sessions" /></div><span className="result-count">{filtered.length} shown · {data.totalSessions} total</span></div><section className="panel table-panel">{filtered.length ? <SessionsTable sessions={filtered} onViewResults={(id) => { setSelectedSession(id); onViewResults(id); }} selectedSession={selectedSession} /> : data.sessions.length ? <EmptyState icon={<Search />} title="No matching sessions" detail="Try a shorter search term or clear the search box." /> : <div className="empty-state"><span className="empty-icon"><Layers3 /></span><h3>No sessions found</h3><p>Start the official/development sensor mock and pipeline, or load the deterministic demo fixture to inspect a persisted session. The fixture is generated once, saved to JSONL and SQLite, and reused by the results and integrity views.</p>{data.demoStatus?.enabled && !data.publicReadOnly && <button className="button button-primary" onClick={() => void data.seedDemo()} disabled={data.demoBusy}>{data.demoBusy ? 'Storing dataset…' : 'Load persistent demo dataset'}</button>}</div>}</section><div className="supporting-note"><InfoIcon /> <p>Session timestamps reflect application storage records. The API may not retain a complete wall-clock timeline for every sample.</p></div></>;
}

function sessionsFilter(rows: SessionRow[], search: string) {
  const term = search.trim().toLowerCase();
  return term ? rows.filter((row) => row.session_id.toLowerCase().includes(term)) : rows;
}

function SessionsTable({ sessions, onViewResults, selectedSession }: { sessions: SessionRow[]; onViewResults: (id: string) => void; selectedSession?: string }) {
  if (!sessions.length) return <EmptyState icon={<Layers3 />} title="No sessions found" detail="No session rows were returned by the API." />;
  return <div className="table-scroll"><table className="data-table"><thead><tr><th>Session ID</th><th>Device samples</th><th>Cloud samples</th><th>Loss records</th><th>Windows</th><th>Last seen</th><th><span className="sr-only">Action</span></th></tr></thead><tbody>{sessions.map((session) => <tr key={session.session_id} className={selectedSession === session.session_id ? 'row-selected' : ''}><td><button className="session-id-button" onClick={() => onViewResults(session.session_id)} title="Inspect processing results">{session.session_id}</button><div className="table-subline">{session.ended ? 'Ended session' : 'Known session'}</div></td><td className="numeric-cell">{formatCount(session.samples_device)}</td><td className="numeric-cell">{formatCount(session.samples_cloud)}</td><td><span className={session.losses ? 'loss-count loss-count-warning' : 'loss-count'}>{formatCount(session.losses)}</span></td><td className="numeric-cell">{formatCount(session.results)}</td><td>{formatTime(session.last_seen_at)}</td><td><button className="row-action" onClick={() => onViewResults(session.session_id)} aria-label={`View results for ${session.session_id}`}><ArrowUpRight size={16} /></button></td></tr>)}</tbody></table></div>;
}

function ResultsView({ data, sessions, selectedSession, setSelectedSession }: { data: DashboardData; sessions: SessionRow[]; selectedSession: string; setSelectedSession: (id: string) => void }) {
  const [results, setResults] = useState<WindowResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [modeFilter, setModeFilter] = useState('all');
  const [completeFilter, setCompleteFilter] = useState('all');
  const [loadError, setLoadError] = useState('');
  useEffect(() => { let active = true; if (!selectedSession) { setResults([]); return () => { active = false; }; } setBusy(true); getResults(selectedSession).then((body) => { if (active) { setResults(body.items); setLoadError(''); } }).catch((err) => { if (active) { setLoadError(err instanceof Error ? err.message : 'Could not load results'); setResults([]); } }).finally(() => { if (active) setBusy(false); }); return () => { active = false; }; }, [selectedSession, data.lastUpdated]);
  const filtered = results.filter((row) => (modeFilter === 'all' || row.mode === modeFilter) && (completeFilter === 'all' || String(row.complete) === completeFilter));
  function downloadJson() { downloadBlob(JSON.stringify(filtered, null, 2), `mayacardio-results-${safeFileName(selectedSession)}.json`, 'application/json'); }
  return <><PageTitle eyebrow="OPERATIONS / PROCESSING" title="Processing results" description="Inspect per-window statistics returned by the existing processing engine. Null values are preserved as null." action={<button className="button button-outline" onClick={downloadJson} disabled={!filtered.length}><ArrowDownToLine size={15} /> Export JSON</button>} /><div className="filter-toolbar"><label className="select-label">Session<select value={selectedSession} onChange={(event) => setSelectedSession(event.target.value)}><option value="">Select a session</option>{sessions.map((session) => <option key={session.session_id} value={session.session_id}>{session.session_id}</option>)}</select></label><label className="select-label">Mode<select value={modeFilter} onChange={(event) => setModeFilter(event.target.value)}><option value="all">All modes</option><option value="online">Online</option><option value="offline">Offline</option></select></label><label className="select-label">Completeness<select value={completeFilter} onChange={(event) => setCompleteFilter(event.target.value)}><option value="all">All windows</option><option value="true">Complete only</option><option value="false">Incomplete only</option></select></label><span className="result-count">{filtered.length} windows</span></div>{loadError && <div className="alert-banner"><CircleAlert size={17} /><div><strong>Could not load results</strong><span>{loadError}</span></div></div>}<div className="metric-grid metric-grid-three"><MetricCard label="Windows loaded" value={results.length} icon={<Activity size={18} />} detail="Combined local and cloud records" tone="violet" /><MetricCard label="Complete windows" value={results.filter((row) => row.complete).length} icon={<CheckCircle2 size={18} />} detail="Both sensors have all expected samples" tone="green" /><MetricCard label="Incomplete windows" value={results.filter((row) => !row.complete).length} icon={<CircleAlert size={18} />} detail="Review missing counts before interpretation" tone="amber" /></div><section className="panel table-panel"><div className="panel-heading"><div><h2>Window detail</h2><p>One row per known session/window/mode result.</p></div><span className="panel-pill">{busy ? 'LOADING' : 'API DATA'}</span></div>{busy ? <LoadingState label="Loading window results…" /> : <ResultsTable rows={filtered} />}</section></>;
}

function ResultsTable({ rows }: { rows: WindowResult[] }) {
  if (!rows.length) return <EmptyState icon={<Activity />} title="No window results available" detail="Select a session with processed data. A rate or statistic may legitimately be null when the assessment's rules do not permit a valid result." />;
  return <div className="table-scroll"><table className="data-table results-table"><thead><tr><th>Window</th><th>Sample range</th><th>Mode</th><th>Complete</th><th>Missing S1</th><th>Missing S2</th><th>Magnitude</th><th>Heart rate</th></tr></thead><tbody>{rows.map((row) => <tr key={`${row.session_id}-${row.window_index}-${row.mode}`}><td className="numeric-cell">{row.window_index}</td><td><span className="range-text">{row.start_index?.toLocaleString()}-{row.end_index?.toLocaleString()}</span></td><td><StatusPill state={row.mode} label={row.mode} /></td><td>{row.complete ? <span className="inline-good"><Check size={14} /> Complete</span> : <span className="inline-warn"><CircleAlert size={14} /> Incomplete</span>}</td><td className="numeric-cell">{row.missing_1}</td><td className="numeric-cell">{row.missing_2}</td><td className="numeric-cell">{formatDecimal(row.magnitude)}</td><td className="numeric-cell">{row.heart_rate === null ? '-' : `${formatDecimal(row.heart_rate)} bpm`}</td></tr>)}</tbody></table></div>;
}

function IntegrityView({ data, selectedSession, setSelectedSession, sessions }: { data: DashboardData; selectedSession: string; setSelectedSession: (id: string) => void; sessions: SessionRow[] }) {
  const [losses, setLosses] = useState<LossRecord[]>([]);
  const [lossLoading, setLossLoading] = useState(false);
  useEffect(() => { let active = true; if (!selectedSession) { setLosses([]); return () => { active = false; }; } setLossLoading(true); getLosses(selectedSession).then((rows) => { if (active) setLosses(rows); }).catch(() => { if (active) setLosses([]); }).finally(() => { if (active) setLossLoading(false); }); return () => { active = false; }; }, [selectedSession, data.lastUpdated]);
  function downloadJson() { downloadBlob(JSON.stringify({ session_id: selectedSession, losses, events: data.events }, null, 2), `mayacardio-integrity-${safeFileName(selectedSession || 'all')}.json`, 'application/json'); }
  return <><PageTitle eyebrow="OPERATIONS / INTEGRITY" title="Data integrity" description="Review explicitly recorded data loss and diagnostic events. Unknown loss is not represented as zero loss." action={<button className="button button-outline" onClick={downloadJson}><ArrowDownToLine size={15} /> Export records</button>} /><div className="filter-toolbar"><label className="select-label">Session<select value={selectedSession} onChange={(event) => setSelectedSession(event.target.value)}><option value="">Select a session</option>{sessions.map((session) => <option key={session.session_id} value={session.session_id}>{session.session_id}</option>)}</select></label><span className="result-count">{losses.length} loss records · {data.events.length} recent events</span></div><div className="metric-grid metric-grid-three"><MetricCard label="Recorded loss ranges" value={losses.length} icon={<CircleAlert size={18} />} detail="Known ranges with stated reason" tone={losses.length ? 'amber' : 'green'} /><MetricCard label="Integrity events" value={data.events.length} icon={<Bell size={18} />} detail="Most recent API event records" tone="blue" /><MetricCard label="Sessions with losses" value={sessions.filter((session) => session.losses > 0).length} icon={<ShieldCheck size={18} />} detail="Across sessions visible to the API" tone="violet" /></div><section className="panel table-panel"><div className="panel-heading"><div><h2>Loss ledger</h2><p>Each row preserves the sensor, missing index range, and recorded reason.</p></div><span className="panel-pill">{lossLoading ? 'LOADING' : 'RECONCILED RECORDS'}</span></div>{lossLoading ? <LoadingState label="Loading loss records…" /> : !losses.length ? <EmptyState icon={<CheckCircle2 />} title="No loss records returned for this session" detail={selectedSession ? 'This means no loss records were returned by the queried stores for this session; it is not a guarantee that every assessment test has passed.' : 'Choose a session to inspect its loss ledger.'} /> : <div className="table-scroll"><table className="data-table"><thead><tr><th>Sensor</th><th>From index</th><th>To index</th><th>Reason</th><th>Source</th><th>Recorded at</th></tr></thead><tbody>{losses.map((loss, index) => <tr key={`${loss.sensor}-${loss.from_index}-${loss.to_index}-${index}`}><td>Sensor {loss.sensor}</td><td className="numeric-cell">{loss.from_index.toLocaleString()}</td><td className="numeric-cell">{loss.to_index === null ? 'Unknown' : loss.to_index.toLocaleString()}</td><td>{loss.reason}</td><td><StatusPill state={loss.source} label={loss.source} /></td><td>{formatTime(loss.recorded_at)}</td></tr>)}</tbody></table></div>}</section><section className="panel table-panel events-panel"><div className="panel-heading"><div><h2>Recent integrity events</h2><p>Diagnostic events reported by local and cloud stores, when available.</p></div></div>{data.events.length ? <div className="event-list">{data.events.slice(0, 30).map((event) => <div className="event-row" key={event.id}><span className="event-symbol"><Activity size={16} /></span><div className="event-body"><strong>{event.event_type.replaceAll('_', ' ')}</strong><p>{event.detail}</p><small>{event.session_id || 'No session'} · {formatTime(event.created_at)}</small></div><StatusPill state={event.source} label={event.source} /></div>)}</div> : <EmptyState icon={<Bell />} title="No recent events returned" detail="The event view only shows event records stored by the API." />}</section></>;
}

function SettingsView({
  data, refreshIntervalSeconds, setRefreshIntervalSeconds, themeMode, setThemeMode,
}: {
  data: DashboardData;
  refreshIntervalSeconds: number;
  setRefreshIntervalSeconds: (value: number) => void;
  themeMode: ThemeMode;
  setThemeMode: (value: ThemeMode) => void;
}) {
  function resetPreferences() {
    setRefreshIntervalSeconds(10);
    setThemeMode('light');
    try {
      window.localStorage.removeItem('mayacardio.refreshIntervalSeconds');
      window.localStorage.removeItem('mayacardio.theme');
    } catch { /* Current-page preferences still reset if storage is disabled. */ }
  }
  return <>
    <PageTitle eyebrow="WORKSPACE / PREFERENCES" title="Settings & help" description="Personal display preferences and troubleshooting guidance. These settings do not alter the device collector, cloud credentials, or processing rules." action={<button className="button button-outline" onClick={resetPreferences}>Reset preferences</button>} />
    <div className="settings-grid">
      <section className="panel settings-panel demo-data-settings">
        <div className="panel-heading"><div><h2>Persistent synthetic demo dataset</h2><p>One reproducible fixture, stored once and reused across dashboard views.</p></div><Database size={18} /></div>
        <div className="state-line"><span>Seed</span><strong>{data.demoStatus?.seed ?? 7}</strong></div>
        <div className="state-line"><span>Session</span><strong className="truncate-value" title={data.demoStatus?.session_id}>{data.demoStatus?.session_id || 'Not loaded'}</strong></div>
        <div className="state-line"><span>Device SQLite rows</span><strong>{formatCount(data.demoStatus?.device.sample_rows)}</strong></div>
        <div className="state-line"><span>Cloud-service SQLite rows</span><strong>{formatCount(data.demoStatus?.cloud.sample_rows)}</strong></div>
        <div className="state-line"><span>Runtime JSONL file</span><strong>{data.demoStatus?.dataset_file_exists ? 'Stored' : 'Not created yet'}</strong></div>
        <div className="state-line"><span>Bundled source fixture</span><strong>{data.demoStatus?.bundled_fixture_available ? 'Included' : 'Not included'}</strong></div>
        <p className="settings-helper">The fixture is generated from a fixed seed and a documented algorithm. A controlled sensor-2 gap is explicitly recorded; three windows are marked offline to demonstrate the processing-mode field. This is not the official biosignal-mock or acceptance-test evidence.</p>
        <div className="settings-links">{data.demoStatus?.enabled && !data.demoStatus.seeded && !data.publicReadOnly && <button className="button button-primary" onClick={() => void data.seedDemo()} disabled={data.demoBusy}>{data.demoBusy ? 'Storing…' : data.demoStatus?.bundled_fixture_available ? 'Load and store bundled fixture' : 'Generate and store fixture'}</button>}{data.demoStatus?.seeded && <><a className="button button-outline" href="/api/dashboard/demo/download"><ArrowDownToLine size={15} /> Download JSONL</a>{!data.publicReadOnly && <button className="button button-danger-outline" onClick={() => void data.resetDemo()} disabled={data.demoBusy}>Reset demo session</button>}</>}{!data.demoStatus?.enabled && <span className="api-docs-disabled-note">Synthetic fixture management is disabled for this deployment.</span>}</div>
        {data.demoError && <p className="form-error" role="alert">{data.demoError}</p>}{data.demoMessage && <p className="demo-feedback" role="status"><CheckCircle2 size={15} />{data.demoMessage}</p>}
      </section>
      <section className="panel settings-panel">
        <div className="panel-heading"><div><h2>Display preferences</h2><p>Saved in this browser only; no credentials are stored here.</p></div><Settings2 size={18} /></div>
        <label className="setting-row"><span><strong>Dashboard refresh</strong><small>How often the page requests current API metrics.</small></span><select value={refreshIntervalSeconds} onChange={(event) => setRefreshIntervalSeconds(Number(event.target.value))}><option value={10}>Every 10 seconds</option><option value={15}>Every 15 seconds</option><option value={30}>Every 30 seconds</option></select></label>
        <label className="setting-row"><span><strong>Appearance</strong><small>Change the appearance across the website and dashboard.</small></span><select value={themeMode} onChange={(event) => setThemeMode(event.target.value as ThemeMode)}><option value="light">Light</option><option value="dark">Dark</option></select></label>
        <div className="supporting-note"><InfoIcon /><p>Appearance is shared by the public website and dashboard. Other preferences are saved in this browser only. Server-side credentials, collection settings, cloud URLs, and signal-processing rules must be configured by the operator on the server.</p></div>
      </section>
      <section className="panel settings-panel">
        <div className="panel-heading"><div><h2>Application information</h2><p>Version and connection information reported by the running application.</p></div><Activity size={18} /></div>
        <div className="state-line"><span>Website version</span><strong>1.0.0</strong></div>
        <div className="state-line"><span>API version</span><strong>{data.summary?.service.version || 'Unavailable'}</strong></div>
        <div className="state-line"><span>API status</span><StatusPill state={data.error ? 'unavailable' : data.summary ? 'available' : 'unknown'} label={data.error ? 'Error' : data.summary ? 'Reachable' : 'Unknown'} /></div>
        <div className="state-line"><span>Last successful refresh</span><strong>{formatTime(data.lastUpdated ? data.lastUpdated / 1000 : null)}</strong></div>
        <div className="state-line"><span>Data mode</span><strong>Synthetic demonstration</strong></div>
      </section>
      <section className="panel settings-panel settings-help-panel">
        <div className="panel-heading"><div><h2>Quick troubleshooting</h2><p>Common issues when running the local full stack.</p></div><CircleHelp size={18} /></div>
        <div className="help-item"><strong>Dashboard says API unavailable</strong><p>Start the FastAPI service on port 8000 and check <a href="/health" target="_blank" rel="noreferrer">the health endpoint</a>.</p></div>
        <div className="help-item"><strong>No sessions or samples are shown</strong><p>Start the synthetic mock immediately before the device pipeline, then allow the collector to send samples to the cloud API.</p></div>
        <div className="help-item"><strong>Device metrics are unavailable</strong><p>The API host must be able to access the device database. On a separate cloud host, device-local counts may correctly remain unavailable.</p></div>
        <div className="help-item"><strong>Production access is blocked</strong><p>Configure all server-side dashboard credentials, use HTTPS, and keep the local demo token off public hosts.</p></div>
        <div className="settings-links"><Link to="/docs" className="button button-outline"><BookOpen size={15} /> Project documentation</Link>{API_DOCS_ENABLED ? <a href="/docs" target="_blank" rel="noreferrer" className="button button-outline"><ExternalLink size={15} /> API reference</a> : <span className="api-docs-disabled-note">API reference disabled for this deployment</span>}<Link to="/security" className="button button-outline"><ShieldCheck size={15} /> Security notes</Link></div>
      </section>
    </div>
  </>;
}

function ResourcesView({ data }: { data: DashboardData }) {
  const resource = data.resources;
  return <><PageTitle eyebrow="OPERATIONS / RESOURCES" title="Host resources" description="Resource values sampled from the host running this FastAPI service. They are not automatically measurements of the constrained sensor device." action={<button className="button button-outline" onClick={() => void data.refresh()}><RefreshCw size={15} /> Refresh</button>} /><div className="scope-banner"><Server size={19} /><div><strong>Measurement scope matters</strong><p>{resource?.scope || 'Resource metrics have not yet been returned by the API. These values must not be reported as Raspberry Pi measurements unless measured on that device.'}</p></div></div>{resource ? <><div className="resource-grid"><ResourceCard title="CPU utilization" value={`${resource.cpu_percent.toFixed(1)}%`} percent={resource.cpu_percent} icon={<Gauge />} /><ResourceCard title="Memory utilization" value={`${resource.memory.percent.toFixed(1)}%`} percent={resource.memory.percent} detail={`${formatBytes(resource.memory.used_bytes)} of ${formatBytes(resource.memory.total_bytes)}`} icon={<Layers3 />} /><ResourceCard title="Disk utilization" value={`${resource.disk.percent.toFixed(1)}%`} percent={resource.disk.percent} detail={`${formatBytes(resource.disk.free_bytes)} free`} icon={<HardDrive />} /></div><section className="panel resource-details"><div className="panel-heading"><div><h2>Measurement metadata</h2><p>Details returned by the host metrics endpoint.</p></div></div><div className="state-line"><span>Process ID</span><strong>{resource.pid}</strong></div><div className="state-line"><span>Observation time</span><strong>{formatTime(resource.observed_at)}</strong></div><div className="state-line"><span>Memory used</span><strong>{formatBytes(resource.memory.used_bytes)}</strong></div><div className="state-line"><span>Disk used</span><strong>{formatBytes(resource.disk.used_bytes)}</strong></div><div className="state-line"><span>Disk free</span><strong>{formatBytes(resource.disk.free_bytes)}</strong></div></section></> : <EmptyState icon={<Server />} title="Resource measurements unavailable" detail="The API did not return a valid host resource snapshot. The dashboard will not substitute fabricated metrics." />}</>;
}

function ResourceCard({ title, value, percent, detail, icon }: { title: string; value: string; percent: number; detail?: string; icon: ReactNode }) {
  return <article className="resource-card"><div className="resource-card-header"><span className="metric-icon metric-blue">{icon}</span><span>{title}</span></div><strong>{value}</strong><div className="progress-track"><div className={`progress-fill ${percent > 85 ? 'progress-warning' : ''}`} style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} /></div><p>{detail || 'Point-in-time host sample'}</p></article>;
}

function EmptyState({ icon, title, detail }: { icon: ReactNode; title: string; detail: string }) {
  return <div className="empty-state"><span className="empty-icon">{icon}</span><h3>{title}</h3><p>{detail}</p></div>;
}

function LoadingState({ label }: { label: string }) {
  return <div className="loading-state"><RefreshCw size={18} className="spin" /><span>{label}</span></div>;
}

function ErrorState({ title, detail, onRetry }: { title: string; detail: string; onRetry: () => void }) {
  return <section className="error-page"><span className="error-icon"><CircleAlert size={25} /></span><h1>{title}</h1><p>{detail}</p><button className="button button-primary" onClick={onRetry}><RefreshCw size={16} /> Retry connection</button><p className="muted-copy">For local development, start the FastAPI service in another terminal using the repository instructions.</p></section>;
}

function NotFoundPage() {
  return <PageFrame><section className="error-page"><span className="error-code">404</span><h1>This route does not exist.</h1><p>Use the navigation to return to the project overview or monitoring dashboard.</p><Link to="/" className="button button-primary">Return home <ArrowRight size={16} /></Link></section></PageFrame>;
}

function InfoIcon() { return <CircleHelp size={16} />; }

function formatCount(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? '-' : Math.trunc(value).toLocaleString();
}
function formatDecimal(value: number | null | undefined) {
  return value === null || value === undefined || !Number.isFinite(value) ? '-' : value.toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 0 });
}
function formatTime(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-';
  const date = new Date(value * 1000);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function formatRelative(value: number) {
  const age = Math.max(0, Math.round(Date.now() / 1000 - value));
  if (age < 5) return 'just now';
  if (age < 60) return `${age}s ago`;
  return `${Math.floor(age / 60)}m ago`;
}
function formatBytes(value: number) {
  if (!Number.isFinite(value) || value < 0) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let amount = value; let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit += 1; }
  return `${amount.toLocaleString(undefined, { maximumFractionDigits: 1 })} ${units[unit]}`;
}
function safeFileName(value: string) { return value.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 100) || 'session'; }
function downloadBlob(content: string, name: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.rel = 'noopener';
  document.body.appendChild(anchor); anchor.click(); anchor.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function MetadataManager() {
  const location = useLocation();
  useEffect(() => {
    const hashPath = location.pathname;
    const pages: Record<string, { title: string; description: string; robots: string }> = {
      '/': { title: 'MayaCardio - Signal Operations', description: 'An observable synthetic biosignal pipeline built around durable data capture, online/offline processing, and transparent recovery.', robots: 'index,follow' },
      '/dashboard': { title: 'Monitoring Dashboard | MayaCardio', description: 'Inspect synthetic pipeline status, persisted samples, processing results, data loss records, and service host metrics.', robots: 'noindex,nofollow' },
      '/architecture': { title: 'System Architecture | MayaCardio', description: 'Learn how the synthetic biosignal pipeline collects, persists, processes, and synchronizes data.', robots: 'index,follow' },
      '/security': { title: 'Security and Scope | MayaCardio', description: 'Security boundaries, synthetic-data scope, and deployment responsibilities for the MayaCardio engineering demonstration.', robots: 'index,follow' },
      '/docs': { title: 'Developer Documentation | MayaCardio', description: 'Setup, API reference, testing, and implementation documentation for the MayaCardio pipeline.', robots: 'index,follow' },
    };
    const page = pages[hashPath] || { title: 'Page not found | MayaCardio', description: 'The requested MayaCardio page was not found.', robots: 'noindex,nofollow' };
    document.title = page.title;
    const upsertMeta = (selector: string, attr: string, value: string) => {
      let element = document.head.querySelector<HTMLMetaElement>(selector);
      if (!element) { element = document.createElement('meta'); document.head.appendChild(element); }
      element.setAttribute(attr, value);
    };
    upsertMeta('meta[name=description]', 'content', page.description);
    upsertMeta('meta[name=robots]', 'content', page.robots);
    upsertMeta('meta[property="og:title"]', 'content', page.title);
    upsertMeta('meta[property="og:description"]', 'content', page.description);
    upsertMeta('meta[name="twitter:title"]', 'content', page.title);
    upsertMeta('meta[name="twitter:description"]', 'content', page.description);
    const siteUrl = import.meta.env.VITE_PUBLIC_SITE_URL?.trim().replace(/\/$/, '');
    if (siteUrl) {
      upsertMeta('meta[property="og:image"]', 'content', `${siteUrl}/og-mayacardio.png`);
      upsertMeta('meta[name="twitter:image"]', 'content', `${siteUrl}/og-mayacardio.png`);
      if (hashPath === '/') upsertMeta('meta[property="og:url"]', 'content', `${siteUrl}/`);
    } else {
      upsertMeta('meta[property="og:image"]', 'content', '/og-mayacardio.png');
      upsertMeta('meta[name="twitter:image"]', 'content', '/og-mayacardio.png');
    }
    let canonical = document.head.querySelector<HTMLLinkElement>('link[rel=canonical]');
    if (siteUrl && hashPath === '/') {
      if (!canonical) { canonical = document.createElement('link'); canonical.rel = 'canonical'; document.head.appendChild(canonical); }
      canonical.href = `${siteUrl}/`;
    } else if (canonical) canonical.remove();
  }, [location.pathname]);
  return null;
}

export default function App() {
  const [themeMode, setThemeMode] = useState<ThemeMode>(readThemePreference);
  const themeContext = useMemo(() => ({ themeMode, setThemeMode }), [themeMode]);

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode;
    const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    themeColor?.setAttribute('content', themeMode === 'dark' ? '#091722' : '#f5f8fa');
    try { window.localStorage.setItem('mayacardio.theme', themeMode); }
    catch { /* Theme continues to work for the active page if storage is unavailable. */ }
  }, [themeMode]);

  return (
    <ThemeContext.Provider value={themeContext}>
      <MetadataManager />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/dashboard" element={<DashboardGate />} />
        <Route path="/architecture" element={<InfoPage kind="architecture" />} />
        <Route path="/security" element={<InfoPage kind="security" />} />
        <Route path="/docs" element={<InfoPage kind="docs" />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </ThemeContext.Provider>
  );
}
