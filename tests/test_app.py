import tempfile
import unittest
from pathlib import Path

from app import create_app


class TaskAppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret",
                "DATABASE": str(Path(self.temp_dir.name) / "test.sqlite"),
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def post_form(self, url, data=None):
        with self.client.session_transaction() as session:
            csrf_token = session.get("csrf_token")
        if csrf_token is None:
            self.client.get("/")
            with self.client.session_transaction() as session:
                csrf_token = session["csrf_token"]
        return self.client.post(
            url, data={**(data or {}), "csrf_token": csrf_token}
        )

    def register(self, username):
        return self.post_form(
            "/register", {"username": username, "password": "password123"}
        )

    def test_user_can_register_login_and_manage_tasks(self):
        response = self.register("alex")
        self.assertEqual(response.status_code, 302)
        response = self.post_form(
            "/tasks", {"title": "Comprar flores", "description": "Para el domingo"}
        )
        self.assertEqual(response.status_code, 302)
        page = self.client.get("/")
        self.assertIn(b"Comprar flores", page.data)
        self.assertIn(b"Para el domingo", page.data)

        with self.app.app_context():
            import sqlite3

            db = sqlite3.connect(self.app.config["DATABASE"])
            task_id = db.execute("SELECT id FROM tasks").fetchone()[0]
            db.close()

        response = self.post_form(f"/tasks/{task_id}/toggle")
        self.assertEqual(response.status_code, 302)
        self.assertIn(b"checked", self.client.get("/").data)
        response = self.post_form(
            f"/tasks/{task_id}/edit",
            {"title": "Flores listas", "description": "Rosas"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(b"Flores listas", self.client.get("/").data)
        response = self.post_form(f"/tasks/{task_id}/delete")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(b"Flores listas", self.client.get("/").data)

        self.post_form("/logout")
        response = self.post_form(
            "/login", {"username": "alex", "password": "password123"}
        )
        self.assertEqual(response.status_code, 302)

    def test_users_cannot_access_each_others_tasks(self):
        self.register("alex")
        self.post_form("/tasks", {"title": "Privada de Alex"})
        with self.app.app_context():
            import sqlite3

            db = sqlite3.connect(self.app.config["DATABASE"])
            task_id = db.execute("SELECT id FROM tasks").fetchone()[0]
            db.close()

        self.post_form("/logout")
        self.register("sam")
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertNotIn(b"Privada de Alex", self.client.get("/").data)
        self.assertEqual(self.client.get(f"/tasks/{task_id}/edit").status_code, 404)
        self.assertEqual(self.post_form(f"/tasks/{task_id}/delete").status_code, 404)

    def test_rejects_invalid_registration_and_missing_csrf(self):
        response = self.post_form(
            "/register", {"username": "ab", "password": "password123"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"entre 3 y 30", response.data)
        self.assertEqual(self.client.post("/register", data={}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
