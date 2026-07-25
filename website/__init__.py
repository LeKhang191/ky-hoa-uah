import os
from flask import Flask
from flask_login import LoginManager


def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-change-me')

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads')
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024

    from .models import init_db
    init_db()

    from .views import views
    from .auth import auth
    from .admin_setup import admin_setup

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')
    app.register_blueprint(admin_setup, url_prefix='/')

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from .models import get_db_connection, User
        conn = get_db_connection()
        user_data = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        conn.close()
        if user_data:
            return User(
                id=user_data['id'],
                username=user_data['username'],
                fullname=user_data['fullname'],
                role=user_data['role'],
                avatar=user_data['avatar'],
            )
        return None

    return app
