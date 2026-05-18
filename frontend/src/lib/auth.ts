// ================================================================
// NexusCare — Auth Helpers
// Two-token JWT flow: selection_token -> access_token.
// ================================================================
//
// TODO(Stage 3): Implement auth helpers.
//   - login(): POST /api/v1/auth/login -> selection_token + memberships.
//   - selectWorkspace(): POST /api/v1/auth/select-workspace -> access_token.
//   - logout(): clear HttpOnly cookies, reset the auth store.
//   - Token storage is HttpOnly cookies set via Next.js middleware /
//     Route Handlers — never localStorage.

export {};
