/** Demo sign-out clears volatile profile/HR/draft state by starting a fresh document. */
export function endDemoSession() {
  try {
    sessionStorage.removeItem("mesh-demo-ui");
    sessionStorage.removeItem("mesh-demo-tenant");
  } catch {
    // A fresh document still clears in-memory private state if storage is unavailable.
  }
  window.location.assign("/login");
}
