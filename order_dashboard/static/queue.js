// Behavior for the order queue page. Lives here because the page's security
// header (Content-Security-Policy, default-src 'self') blocks inline scripts
// and onclick attributes: the select-all box and the submit confirm used to
// be inline and never ran in production.
(function () {
  // Select all / none.
  var all = document.getElementById('select-all');
  if (all) {
    all.addEventListener('change', function () {
      document.querySelectorAll('input[name="order_ids"]').forEach(function (cb) {
        cb.checked = all.checked;
      });
    });
  }

  // Confirm before a batch submit; refuse an empty one.
  var submit = document.getElementById('batch-submit');
  if (submit) {
    submit.addEventListener('click', function (ev) {
      var n = document.querySelectorAll('input[name="order_ids"]:checked').length;
      if (n === 0) {
        ev.preventDefault();
        alert('No orders selected.');
        return;
      }
      if (!confirm('Submit ' + n + ' order(s) to Sage?')) ev.preventDefault();
    });
  }

  // Reload every 60 seconds so new orders appear without a manual refresh.
  // Skips the reload while the tab is hidden (nothing to see) or while any
  // order is ticked for batch submit (a reload would clear the ticks). The
  // reload keeps the current sort, since it is in the address.
  var EVERY_MS = 60 * 1000;
  setInterval(function () {
    if (document.hidden) return;
    if (document.querySelector('input[name="order_ids"]:checked')) return;
    window.location.reload();
  }, EVERY_MS);
})();
