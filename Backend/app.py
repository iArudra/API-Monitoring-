from flask import Flask, jsonify
from routes.ingest import bp as ingest_bp
from routes.query import bp as query_bp
from db import close_pool


def create_app():
    app = Flask(__name__)
    app.register_blueprint(ingest_bp)
    app.register_blueprint(query_bp)

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    @app.teardown_appcontext
    def _shutdown(exception=None):
        pass  # pool is process-lifetime, not per-request; nothing to do here

    return app


app = create_app()

if __name__ == "__main__":
    # Dev only. For anything beyond a couple of test requests, run via
    # gunicorn instead (see README) — Flask's built-in server is
    # single-threaded and will bottleneck ingestion under real load.
    app.run(host="0.0.0.0", port=5000, debug=True)
