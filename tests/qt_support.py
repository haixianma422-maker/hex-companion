"""Shared Qt fixtures: one QGuiApplication for the test process, and event pumping."""
import time

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QGuiApplication


def qt_app():
    return QGuiApplication.instance() or QGuiApplication([])


def pump(seconds=0., until=None, timeout=5.):
    """Process events for `seconds`, or until `until()` is true (failing after `timeout`)."""
    app = qt_app()
    deadline = time.monotonic() + (timeout if until else seconds)
    while True:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        if until and until():
            return True
        if time.monotonic() >= deadline:
            if until:
                raise AssertionError('condition not reached within %.1fs' % timeout)
            return True
        time.sleep(.005)


def settle_assets(app):
    """Wait for the panel's worker-thread image checks, then for the repaint they cause."""
    pump(until=lambda: not app.panel.assets.busy())
    pump(.02)


def new_companion(store, preview=True, services=False):
    from aram_demo.companion import CompanionApp
    qt_app()
    app = CompanionApp(store, preview=preview, services=services)
    app.panel.set_motion(False)
    app.bubble.set_motion(False)
    return app


def close_companion(app):
    app.close()
    pump(.02)
