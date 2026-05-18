// ================================================================
// NexusCare — API Client
// Typed fetch wrapper around the FastAPI backend (~136 endpoints).
// ================================================================
//
// TODO(Stage 3): Implement the typed fetch wrapper.
//   - Base URL from env (http://localhost:8000 in dev).
//   - Attaches the access_token (HttpOnly cookie, sent automatically).
//   - Normalizes backend error envelopes into a typed ApiError.
//   - Surfaces 401 -> redirect to /login (see lib/auth.ts).
//   - All network calls in the app MUST go through this module.

export {};
