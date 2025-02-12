"""Docker main module."""

from proxy_middleware import AuthHeaderMutatorMiddleware

from app.main import app

app = AuthHeaderMutatorMiddleware(app)
