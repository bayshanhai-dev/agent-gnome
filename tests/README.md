# GNOME GUI acceptance tests

This suite exercises the two control layers documented by this skill against
real applications in a GNOME session:

- `test_calculator_atspi.py` uses the AT-SPI accessibility tree to activate
  Calculator buttons by accessible name and verifies the displayed result.
- `test_drawio_cdp.py` uses a loopback-only Chromium DevTools Protocol
  connection to inspect Drawio's visible DOM, send mouse and text input to the
  visible canvas, and verify the resulting shape and label.

## Requirements

- Linux with a running GNOME session, or Xvfb plus `dbus-run-session` and
  `gnome-session --session=ubuntu` for headless execution.
- Python 3 with `pyatspi` and `scrot` for the Calculator test.
- `gnome-calculator`.
- `drawio` and Node.js for the Drawio test. Drawio is optional: if it is not
  installed, that test reports `SKIP` and the suite does not treat it as a
  fake pass.

Run the suite from the repository checkout:

```sh
tests/run-all.sh
```

The runner uses the current display/session when one is available. Otherwise
it starts an Xvfb display and a private D-Bus GNOME session, then cleans up
only the processes it started. Individual tests can also be run directly from
an already-running GNOME session.

## Evidence

Every passing scenario writes a fresh PNG beneath `tests/evidence/` using the
test name as its stem. The files are screenshots of the real app state after
the assertion succeeds. A test never reports PASS merely because a screenshot
was produced.

## Results

The runner prints one result for each scenario and exits non-zero if any test
fails. Exit status 77 is reserved for an intentional optional-app skip. A
missing optional app is therefore `SKIP`, never `PASS`; infrastructure or
assertion problems remain `FAIL`.
