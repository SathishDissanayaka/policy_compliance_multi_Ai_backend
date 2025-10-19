
from flask import Flask
from flask_cors import CORS
from routes.document_routes import document_bp
from routes.query_routes import query_bp
from routes.recommendation_routes import recommendation_bp
from routes.policy_routes import policy_bp
from routes.chat_routes import chat_bp
from routes.user_routes import user_bp

def create_app():
    app = Flask(__name__)

    # Enable CORS
    CORS(app, resources={
        r"/*": {
            "origins": ["http://localhost:5173"],
            "methods": ["GET", "POST", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],  # Add Authorization
            "expose_headers": ["Authorization"]
        }
    })

    # Register blueprints
    app.register_blueprint(document_bp, url_prefix="/documents")
    app.register_blueprint(query_bp, url_prefix="/queries")
    app.register_blueprint(recommendation_bp, url_prefix="/recommendations")
    app.register_blueprint(chat_bp, url_prefix="/chat")
    app.register_blueprint(policy_bp, url_prefix="/policies")
    app.register_blueprint(user_bp, url_prefix="/user")
    

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)