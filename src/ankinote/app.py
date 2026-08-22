from ankinote.utils.httpcli import close_session, init_session


class Application:
    def __init__(self):
        init_session()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Do not inspect or cancel global tasks here.  In the GUI this context
        # runs in NiceGUI's event loop, so those tasks include the server and
        # the client's websocket handler.
        await close_session()
