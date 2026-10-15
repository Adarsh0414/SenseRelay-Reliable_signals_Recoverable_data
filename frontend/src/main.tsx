import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import App from './App';
import './styles.css';

// Apply the stored appearance before React paints to avoid a light-theme flash.
try {
  document.documentElement.dataset.theme = window.localStorage.getItem('mayacardio.theme') === 'dark' ? 'dark' : 'light';
} catch {
  document.documentElement.dataset.theme = 'light';
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Required #root application element was not found.');
}

createRoot(rootElement).render(
  <StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </StrictMode>,
);

// Register the PWA service worker on production hosts and localhost development.
// API routes are excluded from caching by the worker.
if ('serviceWorker' in navigator) {
  const isLocalhost = ['localhost', '127.0.0.1'].includes(window.location.hostname);
  if (import.meta.env.PROD || isLocalhost) {
    window.addEventListener('load', () => {
      void navigator.serviceWorker.register('/sw.js').catch(() => {
        // PWA installation is optional; the core dashboard remains usable if registration fails.
      });
    });
  }
}
