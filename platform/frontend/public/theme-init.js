/* Applies the saved theme before first paint, so a dark-mode user does not see
 * a flash of light.
 *
 * This lives in its own file rather than inline in index.html because the CSP
 * sets `script-src 'self'`, which blocks inline execution. Inlining it would
 * mean either loosening the policy with 'unsafe-inline' or pinning a SHA-256
 * hash that silently breaks the moment anyone edits a character of it. A
 * same-origin file needs neither.
 *
 * Layout.tsx seeds its theme state from the class this sets, and then persists
 * whatever it seeded. If this does not run, a saved 'dark' preference is not
 * merely ignored on load - it is overwritten with 'light'.
 */
try {
  var t = localStorage.getItem('smg-theme')
  if (t === 'dark' || (!t && window.matchMedia('(prefers-color-scheme: dark)').matches))
    document.documentElement.classList.add('dark')
} catch (e) {
  /* private mode or blocked storage: fall through to the light default */
}
