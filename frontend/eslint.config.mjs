import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';

const browserGlobals = {
  window: 'readonly', document: 'readonly', navigator: 'readonly', location: 'readonly',
  fetch: 'readonly', URL: 'readonly', Blob: 'readonly', Response: 'readonly', Request: 'readonly',
  RequestInit: 'readonly', AbortController: 'readonly', FormData: 'readonly', HTMLElement: 'readonly',
  setTimeout: 'readonly', clearTimeout: 'readonly', setInterval: 'readonly', clearInterval: 'readonly',
  console: 'readonly', globalThis: 'readonly',
};
const nodeGlobals = { process: 'readonly', URL: 'readonly', console: 'readonly' };
const serviceWorkerGlobals = {
  self: 'readonly', caches: 'readonly', URL: 'readonly', fetch: 'readonly', Response: 'readonly',
};

export default [
  { ignores: ['dist/**', 'node_modules/**', 'coverage/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['public/sw.js'],
    languageOptions: { globals: serviceWorkerGlobals },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: { globals: browserGlobals },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'no-undef': 'off',
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
    },
  },
  {
    files: ['*.ts', '*.mjs'],
    languageOptions: { globals: nodeGlobals },
    rules: { 'no-undef': 'off' },
  },
  {
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: nodeGlobals },
  },
];
