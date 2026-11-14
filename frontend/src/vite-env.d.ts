/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "1" turns on synthetic mode at build time. */
  readonly VITE_SYNTHETIC?: string;
  /** Origin of a hosted backend, e.g. https://membrane-api.onrender.com. Empty = same origin (/api proxy). */
  readonly VITE_API_BASE?: string;
}
