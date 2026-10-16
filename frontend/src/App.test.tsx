import { renderToString } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import App from './App';

function renderPath(path: string): string {
  return renderToString(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe('public website pages', () => {
  it('renders the synthetic-data landing page, theme control, and PWA install affordance', () => {
    const html = renderPath('/');
    expect(html).toContain('Reliable signals.');
    expect(html).toContain('Synthetic data only');
    expect(html).toContain('not a clinically validated monitoring or diagnostic system');
    expect(html).toContain('Home');
    expect(html).toContain('Admin');
    expect(html).toContain('href="/admin"');
    expect(html).toContain('Switch to dark mode');
    expect(html).toContain('Install MayaCardio as an app');
  });

  it('renders the architecture overview', () => {
    const html = renderPath('/architecture');
    expect(html).toContain('A pipeline designed around durable boundaries.');
    expect(html).toContain('Acquisition');
    expect(html).toContain('Synchronization');
    expect(html).toContain('Home');
  });

  it('renders the security and synthetic-data limitations page', () => {
    const html = renderPath('/security');
    expect(html).toContain('Clear access boundaries. Honest limits.');
    expect(html).toContain('No HIPAA, GDPR, clinical accuracy, regulatory approval, or medical safety certification is claimed.');
  });

  it('renders the not-found page for unknown paths', () => {
    const html = renderPath('/not-a-real-page');
    expect(html).toContain('This route does not exist.');
  });
});
