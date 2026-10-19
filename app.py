import os
import secrets
import sqlite3
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.environ.get(
            "DATABASE", str(Path(app.instance_path) / "tasks.sqlite")
        ),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    def get_db():
        if "db" not in g:
            Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        get_db().executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        get_db().commit()

    @app.context_processor
    def csrf_context():
        def csrf_token():
            if "csrf_token" not in session:
                session["csrf_token"] = secrets.token_hex(32)
            return session["csrf_token"]

        return {"csrf_token": csrf_token}

    @app.before_request
    def protect_forms():
        if request.method != "POST":
            session.setdefault("csrf_token", secrets.token_hex(32))
            return
        submitted_token = request.form.get("csrf_token", "")
        session_token = session.get("csrf_token", "")
        if not session_token or not secrets.compare_digest(
            submitted_token, session_token
        ):
            abort(400, description="El formulario ha caducado. Recarga la página.")

    def login_required(view):
        @wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                flash("Inicia sesión para continuar.", "info")
                return redirect(url_for("login"))
            return view(**kwargs)

        return wrapped_view

    @app.before_request
    def load_logged_in_user():
        user_id = session.get("user_id")
        g.user = (
            get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if user_id is not None
            else None
        )

    @app.route("/")
    def index():
        if g.user is None:
            return render_template("welcome.html")
        tasks = get_db().execute(
            """
            SELECT id, title, description, completed, created_at
            FROM tasks WHERE user_id = ?
            ORDER BY completed ASC, created_at DESC, id DESC
            """,
            (g.user["id"],),
        ).fetchall()
        return render_template("dashboard.html", tasks=tasks)

    @app.route("/register", methods=("GET", "POST"))
    def register():
        if g.user is not None:
            return redirect(url_for("index"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            error = None
            if len(username) < 3 or len(username) > 30:
                error = "El nombre de usuario debe tener entre 3 y 30 caracteres."
            elif not username.replace("_", "").replace("-", "").isalnum():
                error = "Usa solo letras, números, guiones y guiones bajos."
            elif len(password) < 8:
                error = "La contraseña debe tener al menos 8 caracteres."

            if error is None:
                db = get_db()
                try:
                    cursor = db.execute(
                        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        (username, generate_password_hash(password)),
                    )
                    db.commit()
                except sqlite3.IntegrityError:
                    error = "Ese nombre de usuario ya está registrado."
                else:
                    session.clear()
                    session["user_id"] = cursor.lastrowid
                    return redirect(url_for("index"))

            flash(error, "error")
        return render_template("auth.html", mode="register")

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if g.user is not None:
            return redirect(url_for("index"))
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            user = get_db().execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            ).fetchone()
            if user is None or not check_password_hash(
                user["password_hash"], password
            ):
                flash("Usuario o contraseña incorrectos.", "error")
            else:
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("index"))
        return render_template("auth.html", mode="login")

    @app.route("/logout", methods=("POST",))
    @login_required
    def logout():
        session.clear()
        flash("Has cerrado sesión.", "success")
        return redirect(url_for("login"))

    @app.route("/tasks", methods=("POST",))
    @login_required
    def create_task():
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        if not title or len(title) > 120:
            flash("El título es obligatorio y debe tener 120 caracteres o menos.", "error")
        elif len(description) > 2000:
            flash("La descripción no puede superar los 2000 caracteres.", "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO tasks (user_id, title, description) VALUES (?, ?, ?)",
                (g.user["id"], title, description),
            )
            db.commit()
            flash("Tarea creada.", "success")
        return redirect(url_for("index"))

    @app.route("/tasks/<int:task_id>/edit", methods=("GET", "POST"))
    @login_required
    def edit_task(task_id):
        db = get_db()
        task = db.execute(
            "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, g.user["id"]),
        ).fetchone()
        if task is None:
            abort(404)

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            if not title or len(title) > 120:
                flash(
                    "El título es obligatorio y debe tener 120 caracteres o menos.",
                    "error",
                )
            elif len(description) > 2000:
                flash("La descripción no puede superar los 2000 caracteres.", "error")
            else:
                db.execute(
                    """
                    UPDATE tasks SET title = ?, description = ?
                    WHERE id = ? AND user_id = ?
                    """,
                    (title, description, task_id, g.user["id"]),
                )
                db.commit()
                flash("Tarea actualizada.", "success")
                return redirect(url_for("index"))
        return render_template("edit_task.html", task=task)

    @app.route("/tasks/<int:task_id>/toggle", methods=("POST",))
    @login_required
    def toggle_task(task_id):
        db = get_db()
        cursor = db.execute(
            """
            UPDATE tasks SET completed = 1 - completed
            WHERE id = ? AND user_id = ?
            """,
            (task_id, g.user["id"]),
        )
        if cursor.rowcount == 0:
            abort(404)
        db.commit()
        return redirect(url_for("index"))

    @app.route("/tasks/<int:task_id>/delete", methods=("POST",))
    @login_required
    def delete_task(task_id):
        db = get_db()
        cursor = db.execute(
            "DELETE FROM tasks WHERE id = ? AND user_id = ?",
            (task_id, g.user["id"]),
        )
        if cursor.rowcount == 0:
            abort(404)
        db.commit()
        flash("Tarea eliminada.", "success")
        return redirect(url_for("index"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
