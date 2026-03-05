"""REST API and WebSocket server module.

Public API::

    from ios_gps_spoofer.api import create_app, run_server

    app = create_app()
    run_server(app, host="127.0.0.1", port=8456)
"""

from ios_gps_spoofer.api.server import create_app, run_server

__all__ = [
    "create_app",
    "run_server",
]
