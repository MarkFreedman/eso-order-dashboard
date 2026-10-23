// Reload the queue every 60 seconds so new orders appear without a manual
// refresh. Skips the reload while the tab is hidden (nothing to see) or while
// any order is ticked for batch submit (a reload would clear the ticks).
// Only the queue page loads this; the order page never auto-reloads.
(function () {
  var EVERY_MS = 60 * 1000;
  setInterval(function () {
    if (document.hidden) return;
    if (document.querySelector('input[type="checkbox"]:checked')) return;
    window.location.reload();
  }, EVERY_MS);
})();
