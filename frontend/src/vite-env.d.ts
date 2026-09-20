/// <reference types="vite/client" />

/**
 * Vite client type shims for import.meta.env.
 * Architectural responsibility: typed non-secret frontend env access.
 */

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** Non-secret build/version stamp (set at image build time). */
  readonly VITE_APP_VERSION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
