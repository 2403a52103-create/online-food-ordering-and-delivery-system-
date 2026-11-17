import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing

from app import create_app
from werkzeug.security import check_password_hash, generate_password_hash


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = f"{self.temporary_directory.name}/foodexpress_test.sqlite3"
        app = create_app(
            {
                "TESTING": True,
                "WTF_CSRF_ENABLED": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": self.database_path,
            }
        )
        self.client = app.test_client()
        self.app = app

    def tearDown(self):
        self.temporary_directory.cleanup()

    def csrf_token(self, path):
        response = self.client.get(path)
        match = re.search(rb'name="csrf_token" type="hidden" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def register_customer(self, email="sam@example.com", password="correct-horse-42"):
        return self.client.post(
            "/register",
            data={
                "csrf_token": self.csrf_token("/register"),
                "name": "Sam Customer",
                "email": email,
                "phone": "+1 (415) 555-0132",
                "password": password,
                "submit": "Create account",
            },
            follow_redirects=False,
        )

    def sign_in_customer(self, email="sam@example.com", password="correct-horse-42"):
        self.register_customer(email=email, password=password)
        return self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf_token("/login"),
                "email": email,
                "password": password,
            },
            follow_redirects=False,
        )

    def create_staff_user(self, role, email):
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                """
                INSERT INTO users (name, email, phone, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    f"Test {role.title()}",
                    email,
                    "9876543210",
                    generate_password_hash("staff-password"),
                    role,
                ),
            )
            database.commit()
            return database.execute("SELECT last_insert_rowid()").fetchone()[0]

    def sign_in_admin(self):
        self.create_staff_user("admin", "admin@example.com")
        return self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf_token("/admin/login"),
                "email": "admin@example.com",
                "password": "staff-password",
            },
        )

    def sign_in_delivery(self, email="delivery@example.com"):
        self.create_staff_user("delivery", email)
        return self.client.post(
            "/delivery/login",
            data={
                "csrf_token": self.csrf_token("/delivery/login"),
                "email": email,
                "password": "staff-password",
            },
        )

    def test_create_app_creates_missing_database_directory(self):
        nested_path = f"{self.temporary_directory.name}/nested/db/foodexpress.sqlite3"
        create_app(
            {
                "TESTING": True,
                "WTF_CSRF_ENABLED": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": nested_path,
            }
        )

        self.assertTrue(os.path.exists(os.path.dirname(nested_path)))

    def test_home_page_loads(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"FoodExpress", response.data)
        self.assertIn(b"Delicious Food", response.data)
        self.assertIn(b"Search food", response.data)
        self.assertIn(b"Crispy Chilli Paneer", response.data)

    def test_menu_page_loads_with_food_items(self):
        response = self.client.get("/menu")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Our menu", response.data)
        self.assertIn(b"Chicken Dum Biryani", response.data)
        self.assertIn(b"Masala Dosa", response.data)
        self.assertIn(b"data-food-name=", response.data)
        self.assertIn(b"Add to cart", response.data)
        category_order = (
            b'data-category-filter="pizza"',
            b'data-category-filter="burger"',
            b'data-category-filter="biryani"',
            b'data-category-filter="chinese"',
            b'data-category-filter="south-indian"',
            b'data-category-filter="desserts"',
        )
        category_positions = [response.data.index(category) for category in category_order]
        self.assertEqual(category_positions, sorted(category_positions))
        for label in (b"Pizza", b"Burger", b"Biryani", b"Chinese", b"South Indian", b"Desserts"):
            self.assertIn(label, response.data)

    def test_each_food_category_is_seeded_with_at_least_twenty_items(self):
        expected_categories = (
            "pizza",
            "burger",
            "biryani",
            "chinese",
            "south-indian",
            "desserts",
        )

        def category_counts():
            with closing(sqlite3.connect(self.database_path)) as database:
                return dict(
                    database.execute(
                        """
                        SELECT category, COUNT(*)
                        FROM food_items
                        WHERE active = 1
                        GROUP BY category
                        """
                    ).fetchall()
                )

        def image_counts():
            with closing(sqlite3.connect(self.database_path)) as database:
                return database.execute(
                    """
                    SELECT COUNT(*), COUNT(DISTINCT image)
                    FROM food_items
                    WHERE active = 1
                    """
                ).fetchone()

        first_counts = category_counts()
        for category in expected_categories:
            with self.subTest(category=category):
                self.assertGreaterEqual(first_counts.get(category, 0), 20)

        first_image_counts = image_counts()
        self.assertEqual(first_image_counts[0], first_image_counts[1])

        create_app(
            {
                "TESTING": True,
                "WTF_CSRF_ENABLED": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": self.database_path,
            }
        )
        self.assertEqual(category_counts(), first_counts)
        self.assertEqual(image_counts(), first_image_counts)

    def test_menu_displays_food_records_added_to_database(self):
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                """
                INSERT INTO food_items
                    (name, category, description, price, image, rating, badge)
                VALUES ('Test Noodle Bowl', 'chinese', 'Fresh noodles with vegetables.', 215, '/static/noodles.jpg', '4.5', 'New')
                """
            )
            database.commit()

        response = self.client.get("/menu")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Test Noodle Bowl", response.data)
        self.assertIn(b"Fresh noodles with vegetables.", response.data)
        self.assertIn("₹215".encode("utf-8"), response.data)
        self.assertIn(b'data-category="chinese"', response.data)

    def test_food_search_renders_search_input_and_searchable_food_names(self):
        response = self.client.get("/menu")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="foodSearch"', response.data)
        self.assertIn(b'aria-label="Search dishes by name"', response.data)
        self.assertIn(b'data-food-name="margherita pizza"', response.data)
        self.assertIn(b'data-food-name="chicken dum biryani"', response.data)
        self.assertIn(b'id="emptySearch"', response.data)

    def test_add_to_cart_from_menu_persists_item_and_returns_to_menu(self):
        self.sign_in_customer()
        token = self.csrf_token("/menu")

        response = self.client.post(
            "/customer/cart/add/7?return_to=menu",
            data={"csrf_token": token},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/menu#foodGrid")
        with closing(sqlite3.connect(self.database_path)) as database:
            cart_item = database.execute(
                "SELECT food_id, quantity FROM cart_items"
            ).fetchone()
        self.assertEqual(cart_item, (7, 1))

    def test_about_and_contact_links_return_home_sections(self):
        self.assertEqual(self.client.get("/about").headers["Location"], "/#about")
        self.assertEqual(self.client.get("/contact").headers["Location"], "/#contact")

    def test_account_pages_load(self):
        self.assertEqual(self.client.get("/login").status_code, 200)
        self.assertEqual(self.client.get("/register").status_code, 200)

    def test_registration_stores_hashed_password_and_redirects_to_login(self):
        response = self.register_customer(email=" Sam@Example.com ")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        with closing(sqlite3.connect(self.database_path)) as database:
            user = database.execute(
                "SELECT name, email, phone, password_hash, role FROM users"
            ).fetchone()

        self.assertEqual(user[:3], ("Sam Customer", "sam@example.com", "+1 (415) 555-0132"))
        self.assertNotEqual(user[3], "correct-horse-42")
        self.assertTrue(check_password_hash(user[3], "correct-horse-42"))
        self.assertEqual(user[4], "customer")

    def test_registration_rejects_duplicate_email_case_insensitively(self):
        self.assertEqual(self.register_customer().status_code, 302)

        response = self.client.post(
            "/register",
            data={
                "csrf_token": self.csrf_token("/register"),
                "name": "Another Customer",
                "email": "SAM@example.com",
                "phone": "4155550132",
                "password": "another-password",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn(b"An account with this email already exists.", response.data)

    def test_registration_validates_fields_and_csrf(self):
        token = self.csrf_token("/register")
        response = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "name": "A",
                "email": "not-an-email",
                "phone": "abc",
                "password": "short",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Full name</label>", response.data)
        self.assertIn(b"Enter a valid email address.", response.data)
        self.assertIn(b"Enter a valid phone number.", response.data)
        self.assertIn(b"Use a password between 8 and 128 characters.", response.data)

        short_phone_response = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "name": "Sam Customer",
                "email": "sam@example.com",
                "phone": "123",
                "password": "valid-password",
            },
        )
        self.assertEqual(short_phone_response.status_code, 400)
        self.assertIn(b"Phone number must contain 7 to 15 digits.", short_phone_response.data)

        missing_token_response = self.client.post("/register", data={"name": "Sam"})
        self.assertEqual(missing_token_response.status_code, 200)
        self.assertIn(b"CSRF", missing_token_response.data)

    def test_login_redirects_to_customer_dashboard_and_logout_clears_session(self):
        self.register_customer()
        response = self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf_token("/login"),
                "email": "SAM@example.com",
                "password": "correct-horse-42",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/customer/dashboard")
        dashboard = self.client.get("/customer/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Welcome back,", dashboard.data)
        self.assertIn(b"Sam!", dashboard.data)

        logout_response = self.client.post(
            "/logout",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(logout_response.headers["Location"], "/")
        self.assertEqual(self.client.get("/customer/dashboard").headers["Location"], "/login")

    def test_invalid_login_uses_generic_error(self):
        self.register_customer()
        response = self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf_token("/login"),
                "email": "sam@example.com",
                "password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Email or password is incorrect.", response.data)

    def test_session_cookie_is_http_only_and_same_site(self):
        response = self.client.get("/login")
        session_cookie = response.headers["Set-Cookie"]

        self.assertIn("HttpOnly", session_cookie)
        self.assertIn("SameSite=Lax", session_cookie)

    def test_customer_dashboard_shows_database_menu_and_sections(self):
        self.sign_in_customer()
        response = self.client.get("/customer/dashboard")

        self.assertEqual(response.status_code, 200)
        for expected in (
            b"Welcome back,",
            b"Food Menu",
            b"My Cart",
            b"My Orders",
            b"Track Order",
            b"Profile",
            b"Admin sign in",
            b"Margherita Pizza",
            b"Add to cart",
        ):
            self.assertIn(expected, response.data)
        self.assertNotIn(b'class="site-header"', response.data)
        self.assertNotIn(b'class="site-footer"', response.data)

    def test_dashboard_category_filters_include_database_categories(self):
        self.sign_in_customer()
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                """
                INSERT INTO food_items
                    (name, category, description, price, image, rating, badge)
                VALUES ('Garden Fresh Wrap', 'wraps', 'A fresh veggie wrap.', 199, '', '4.5', 'Fresh')
                """
            )
            database.commit()

        response = self.client.get("/customer/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-dashboard-category="wraps"', response.data)
        self.assertIn(b"Garden Fresh Wrap", response.data)

    def test_cancelled_order_is_not_shown_as_in_delivery_progress(self):
        self.sign_in_customer()
        self.client.post(
            "/customer/cart/add/1",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/dashboard"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
        )
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute("UPDATE orders SET tracking_status = 'Cancelled'")
            database.commit()

        response = self.client.get("/customer/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"This order was cancelled", response.data)
        self.assertIn(b"This order will not be delivered.", response.data)
        self.assertNotIn(b'class="tracking-steps"', response.data)

    def test_add_update_and_remove_cart_items(self):
        self.sign_in_customer()
        token = self.csrf_token("/customer/dashboard")
        response = self.client.post(
            "/customer/cart/add/1",
            data={"csrf_token": token},
        )
        self.assertEqual(response.status_code, 302)
        self.client.post("/customer/cart/add/1", data={"csrf_token": token})

        with closing(sqlite3.connect(self.database_path)) as database:
            row = database.execute(
                "SELECT id, quantity FROM cart_items WHERE food_id = 1"
            ).fetchone()
        self.assertEqual(row[1], 2)
        dashboard = self.client.get("/customer/dashboard")
        cart_counts = re.findall(rb'data-cart-count[^>]*>(\d+)<', dashboard.data)
        self.assertEqual(cart_counts, [b"2", b"2", b"2"])

        update_token = self.csrf_token("/customer/dashboard")
        self.client.post(
            "/customer/cart/update",
            data={"csrf_token": update_token, "item_id": row[0], "quantity": "3"},
        )
        with closing(sqlite3.connect(self.database_path)) as database:
            quantity = database.execute(
                "SELECT quantity FROM cart_items WHERE id = ?", (row[0],)
            ).fetchone()[0]
        self.assertEqual(quantity, 3)
        dashboard = self.client.get("/customer/dashboard")
        cart_counts = re.findall(rb'data-cart-count[^>]*>(\d+)<', dashboard.data)
        self.assertEqual(cart_counts, [b"3", b"3", b"3"])

        remove_token = self.csrf_token("/customer/dashboard")
        self.client.post(
            f"/customer/cart/remove/{row[0]}",
            data={"csrf_token": remove_token},
        )
        with closing(sqlite3.connect(self.database_path)) as database:
            remaining_items = database.execute("SELECT COUNT(*) FROM cart_items").fetchone()[0]
        self.assertEqual(remaining_items, 0)

    def test_checkout_saves_order_and_items_and_empties_cart(self):
        self.sign_in_customer()
        token = self.csrf_token("/customer/dashboard")
        self.client.post("/customer/cart/add/1", data={"csrf_token": token})
        self.client.post("/customer/cart/add/2", data={"csrf_token": token})

        response = self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"placed successfully", response.data)
        self.assertIn(b"ID 1", response.data)
        self.assertIn(b"Track your orders", response.data)
        with closing(sqlite3.connect(self.database_path)) as database:
            order = database.execute(
                """
                SELECT order_number, status, tracking_status, subtotal,
                       delivery_fee, total, delivery_address, delivery_phone
                FROM orders
                """
            ).fetchone()
            items = database.execute(
                "SELECT food_name, quantity FROM order_items ORDER BY food_name"
            ).fetchall()
            cart_count = database.execute("SELECT COUNT(*) FROM cart_items").fetchone()[0]
        self.assertEqual(
            order[1:],
            (
                "Preparing",
                "Order Accepted",
                548,
                40,
                588,
                "12 Orange Street, Central City",
                "+91 98765 43210",
            ),
        )
        self.assertEqual(len(order[0]), 16)
        self.assertEqual(items, [("Classic Smash Burger", 1), ("Margherita Pizza", 1)])
        self.assertEqual(cart_count, 0)

    def test_checkout_rejects_invalid_delivery_details_without_clearing_cart(self):
        self.sign_in_customer()
        token = self.csrf_token("/customer/dashboard")
        self.client.post("/customer/cart/add/1", data={"csrf_token": token})

        response = self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "short",
                "delivery_phone": "not-a-phone",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Delivery address", response.data)
        self.assertIn(b"Enter a valid phone number.", response.data)
        with closing(sqlite3.connect(self.database_path)) as database:
            order_count = database.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            cart_count = database.execute("SELECT COUNT(*) FROM cart_items").fetchone()[0]
        self.assertEqual(order_count, 0)
        self.assertEqual(cart_count, 1)

    def test_customer_order_history_details_and_status_refresh_are_database_backed(self):
        self.sign_in_customer()
        self.client.post(
            "/customer/cart/add/1",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
        )

        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                "UPDATE orders SET tracking_status = 'Ready for Pickup' WHERE id = 1"
            )
            database.commit()

        history = self.client.get("/customer/orders")
        status_response = self.client.get("/customer/orders/status")
        detail = self.client.get("/customer/orders/1")

        self.assertEqual(history.status_code, 200)
        self.assertIn(b"Order ID 1", history.data)
        self.assertIn(b"Ready for Pickup", history.data)
        self.assertIn(b"Margherita Pizza", history.data)
        self.assertIn(b"12 Orange Street, Central City", history.data)
        self.assertEqual(status_response.json["statuses"], [{"id": 1, "status": "Ready for Pickup"}])
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"Items in this order", detail.data)
        self.assertIn(b"Contact phone", detail.data)
        self.assertIn("₹339".encode("utf-8"), detail.data)
        for stage in (
            b"Order Accepted",
            b"Preparing",
            b"Ready for Pickup",
            b"Out for Delivery",
            b"Delivered",
        ):
            self.assertIn(stage, detail.data)

        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                "UPDATE orders SET tracking_status = 'Delivered' WHERE id = 1"
            )
            database.commit()
        updated_status = self.client.get("/customer/orders/status")
        self.assertEqual(updated_status.json["statuses"], [{"id": 1, "status": "Delivered"}])

    def test_demo_orders_progress_through_all_stages_within_five_minutes(self):
        self.sign_in_customer()
        self.client.post(
            "/customer/cart/add/5",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
        )

        with closing(sqlite3.connect(self.database_path)) as database:
            demo_order = database.execute(
                "SELECT demo_auto_progress FROM orders WHERE id = 1"
            ).fetchone()[0]
            self.assertEqual(demo_order, 1)

            for seconds, expected_status, expected_legacy_status in (
                (60, "Preparing", "Preparing"),
                (120, "Ready for Pickup", "Preparing"),
                (180, "Out for Delivery", "Out for delivery"),
                (300, "Delivered", "Delivered"),
            ):
                database.execute(
                    "UPDATE orders SET created_at = datetime('now', ?) WHERE id = 1",
                    (f"-{seconds} seconds",),
                )
                database.commit()

                response = self.client.get("/customer/orders/status")

                self.assertEqual(
                    response.json["statuses"],
                    [{"id": 1, "status": expected_status}],
                )
                stored_status = database.execute(
                    "SELECT tracking_status, status FROM orders WHERE id = 1"
                ).fetchone()
                self.assertEqual(
                    tuple(stored_status),
                    (expected_status, expected_legacy_status),
                )

        dashboard = self.client.get("/customer/dashboard")
        self.assertIn(b"Delivered at 5 min", dashboard.data)

    def test_admin_routes_require_admin_role(self):
        protected_paths = (
            "/admin/",
            "/admin/menu",
            "/admin/products",
            "/admin/stock",
            "/admin/customers",
            "/admin/orders",
            "/admin/reports",
        )
        for path in protected_paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["Location"], "/admin/login")

        self.register_customer()
        customer_login = self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf_token("/login"),
                "email": "sam@example.com",
                "password": "correct-horse-42",
            },
        )
        self.assertEqual(customer_login.status_code, 302)
        for path in protected_paths:
            self.assertEqual(self.client.get(path).status_code, 403)

        response = self.client.get("/admin/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Admin sign in", response.data)

        customer_admin_login = self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf_token("/admin/login"),
                "email": "sam@example.com",
                "password": "correct-horse-42",
            },
        )
        self.assertEqual(customer_admin_login.status_code, 200)
        self.assertIn(b"This account is not an administrator.", customer_admin_login.data)
        self.assertNotIn(b"data-dashboard=\"admin\"", customer_admin_login.data)

        self.create_staff_user("admin", "switch-to-admin@example.com")
        admin_login = self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf_token("/admin/login"),
                "email": "switch-to-admin@example.com",
                "password": "staff-password",
            },
        )
        self.assertEqual(admin_login.status_code, 302)
        self.assertEqual(admin_login.headers["Location"], "/admin/dashboard")
        admin_dashboard = self.client.get("/admin/dashboard")
        self.assertIn(b"ADMIN CONTROL CENTER", admin_dashboard.data)
        self.assertIn(b"Admin Dashboard", admin_dashboard.data)
        self.assertNotIn(b"CUSTOMER SPACE", admin_dashboard.data)

    def test_admin_login_redirects_signed_in_delivery_users_to_delivery_dashboard(self):
        delivery_id = self.create_staff_user("delivery", "driver@example.com")
        with self.client.session_transaction() as user_session:
            user_session["user_id"] = delivery_id

        response = self.client.get("/admin/login")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/delivery/dashboard")

    def test_admin_login_dashboard_and_staff_provision_command(self):
        login = self.sign_in_admin()
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.headers["Location"], "/admin/dashboard")

        for path in (
            "/admin/", "/admin/dashboard", "/admin/menu", "/admin/products",
            "/admin/stock", "/admin/customers", "/admin/orders", "/admin/reports",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        dashboard = self.client.get("/admin/dashboard")
        for expected in (
            b"Total Products",
            b"Available Stock",
            b"Pending Orders",
            b"Completed Orders",
            b"Low stock products",
            b"Recent orders",
        ):
            self.assertIn(expected, dashboard.data)
        self.assertEqual(dashboard.data.count(b'class="admin-stat admin-stat-link card"'), 4)
        self.assertIn(b'data-dashboard="admin"', dashboard.data)
        self.assertIn(b"ADMIN CONTROL CENTER", dashboard.data)
        self.assertIn(b"Admin Dashboard", dashboard.data)
        self.assertNotIn(b"CUSTOMER SPACE", dashboard.data)
        self.assertNotIn(b'class="site-header"', dashboard.data)
        self.assertNotIn(b'class="site-footer"', dashboard.data)

        runner = self.app.test_cli_runner()
        result = runner.invoke(
            args=[
                "create-staff",
                "--role",
                "delivery",
                "--name",
                "Taylor Delivery",
                "--email",
                "taylor.delivery@example.com",
                "--phone",
                "9876543211",
            ],
            input="delivery-password\ndelivery-password\n",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        with closing(sqlite3.connect(self.database_path)) as database:
            delivery_user = database.execute(
                "SELECT role, password_hash FROM users WHERE email = 'taylor.delivery@example.com'"
            ).fetchone()
        self.assertEqual(delivery_user[0], "delivery")
        self.assertTrue(check_password_hash(delivery_user[1], "delivery-password"))

    def test_existing_customer_can_be_promoted_with_cli_and_sign_in_as_admin(self):
        self.register_customer()

        result = self.app.test_cli_runner().invoke(
            args=[
                "promote-customer-to-admin",
                "--email",
                "SAM@example.com",
            ],
            input="y\n",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Promoted sam@example.com to admin.", result.output)
        with closing(sqlite3.connect(self.database_path)) as database:
            role = database.execute(
                "SELECT role FROM users WHERE email = 'sam@example.com'"
            ).fetchone()[0]
        self.assertEqual(role, "admin")

        login = self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf_token("/admin/login"),
                "email": "sam@example.com",
                "password": "correct-horse-42",
            },
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.headers["Location"], "/admin/dashboard")
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)

    def test_admin_chart_scripts_are_version_pinned_and_integrity_checked(self):
        self.sign_in_admin()
        expected_script_attributes = (
            b"chart.js@4.4.7/dist/chart.umd.min.js",
            b'integrity="sha384-vsrfeLOOY6KuIYKDlmVH5UiBmgIdB1oEf7p01YgWHuqmOHfZr374+odEv96n9tNC"',
            b'crossorigin="anonymous"',
        )
        expected_bootstrap_attributes = (
            b"bootstrap@5.3.3/dist/css/bootstrap.min.css",
            b'integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH"',
        )

        for path in ("/admin/dashboard", "/admin/reports"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                for attribute in expected_script_attributes:
                    self.assertIn(attribute, response.data)
                for attribute in expected_bootstrap_attributes:
                    self.assertIn(attribute, response.data)

    def test_admin_food_crud_validates_inputs_and_preserves_order_snapshots(self):
        self.sign_in_admin()
        menu_token = self.csrf_token("/admin/menu")
        create = self.client.post(
            "/admin/menu/add",
            data={
                "csrf_token": menu_token,
                "name": "Admin Special Bowl",
                "description": "",
                "price": "275",
                "rating": "4.7",
                "stock_quantity": "12",
                "category": "biryani",
                "image": "/static/images/test-bowl.jpg",
            },
        )
        self.assertEqual(create.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as database:
            food_id = database.execute(
                "SELECT id FROM food_items WHERE name = 'Admin Special Bowl'"
            ).fetchone()[0]

        edit = self.client.post(
            f"/admin/menu/{food_id}/edit",
            data={
                "csrf_token": self.csrf_token(f"/admin/menu/{food_id}/edit"),
                "name": "Updated Special Bowl",
                "description": "Updated description for this test bowl.",
                "price": "299",
                "rating": "4.9",
                "stock_quantity": "4",
                "category": "chinese",
                "image": "https://example.com/bowl.jpg",
            },
        )
        self.assertEqual(edit.status_code, 302)
        invalid = self.client.post(
            "/admin/menu/add",
            data={
                "csrf_token": self.csrf_token("/admin/menu"),
                "name": "Invalid Dish",
                "description": "Invalid item description.",
                "price": "-1",
                "category": "outside-menu",
                "image": "javascript:alert(1)",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Enter an http(s) image URL", invalid.data)
        with closing(sqlite3.connect(self.database_path)) as database:
            row = database.execute(
                """
                SELECT name, price, category, active, rating, stock_quantity, description
                FROM food_items WHERE id = ?
                """,
                (food_id,),
            ).fetchone()
        self.assertEqual(
            row,
            ("Updated Special Bowl", 299, "chinese", 1, "4.9", 4,
             "Updated description for this test bowl."),
        )
        self.assertIn(b"4.9", self.client.get("/admin/menu").data)
        self.assertIn(b"4", self.client.get("/admin/menu").data)

        delete = self.client.post(
            f"/admin/menu/{food_id}/delete",
            data={"csrf_token": self.csrf_token("/admin/menu")},
        )
        self.assertEqual(delete.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as database:
            active = database.execute(
                "SELECT active FROM food_items WHERE id = ?", (food_id,)
            ).fetchone()[0]
        self.assertEqual(active, 0)

    def test_admin_can_add_product_without_optional_fields(self):
        self.sign_in_admin()
        response = self.client.post(
            "/admin/menu/add",
            data={
                "csrf_token": self.csrf_token("/admin/menu"),
                "name": "Simple Test Soup",
                "price": "120",
                "stock_quantity": "8",
                "category": "chinese",
            },
        )

        self.assertEqual(response.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as database:
            row = database.execute(
                """
                SELECT name, description, rating, image, price, category, stock_quantity
                FROM food_items WHERE name = 'Simple Test Soup'
                """
            ).fetchone()
        self.assertEqual(row, ("Simple Test Soup", "", "", "", 120, "chinese", 8))

    def test_admin_dashboard_stock_boundaries_and_order_filters(self):
        self.sign_in_admin()
        customer_id = self.create_staff_user("customer", "orders@example.com")
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute("UPDATE food_items SET stock_quantity = 0")
            database.execute("UPDATE food_items SET stock_quantity = 10 WHERE id = 2")
            database.execute("UPDATE food_items SET stock_quantity = 11 WHERE id = 3")
            for order_number, tracking_status in (
                ("TEST-PENDING", "Preparing"),
                ("TEST-DELIVERED", "Delivered"),
                ("TEST-CANCELLED", "Cancelled"),
            ):
                database.execute(
                    """
                    INSERT INTO orders
                        (order_number, user_id, status, total, tracking_status, demo_auto_progress)
                    VALUES (?, ?, 'Preparing', 250, ?, 1)
                    """,
                    (order_number, customer_id, tracking_status),
                )
            database.commit()

        dashboard = self.client.get("/admin/dashboard")
        self.assertIn(b"<strong>120</strong>", dashboard.data)
        self.assertIn(b"<strong>21</strong>", dashboard.data)
        stock = self.client.get("/admin/stock")
        self.assertIn(b"Out of Stock", stock.data)
        self.assertIn(b"Low Stock", stock.data)
        self.assertIn(b"In Stock", stock.data)

        pending = self.client.get("/admin/orders?status=pending")
        completed = self.client.get("/admin/orders?status=completed")
        all_orders = self.client.get("/admin/orders?status=all")
        self.assertIn(b"TEST-PENDING", pending.data)
        self.assertNotIn(b"TEST-DELIVERED", pending.data)
        self.assertNotIn(b"TEST-CANCELLED", pending.data)
        self.assertIn(b"TEST-DELIVERED", completed.data)
        self.assertNotIn(b"TEST-PENDING", completed.data)
        self.assertNotIn(b"TEST-CANCELLED", completed.data)
        self.assertIn(b"TEST-CANCELLED", all_orders.data)

        stock_update = self.client.post(
            "/admin/stock/2",
            data={
                "csrf_token": self.csrf_token("/admin/stock"),
                "stock_quantity": "0",
            },
        )
        self.assertEqual(stock_update.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as database:
            stock_quantity = database.execute(
                "SELECT stock_quantity FROM food_items WHERE id = 2"
            ).fetchone()[0]
        self.assertEqual(stock_quantity, 0)

        invalid_stock = self.client.post(
            "/admin/stock/2",
            data={
                "csrf_token": self.csrf_token("/admin/stock"),
                "stock_quantity": "-1",
            },
        )
        self.assertEqual(invalid_stock.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as database:
            stock_quantity = database.execute(
                "SELECT stock_quantity FROM food_items WHERE id = 2"
            ).fetchone()[0]
        self.assertEqual(stock_quantity, 0)

    def test_admin_product_stock_and_order_search_controls_render(self):
        self.sign_in_admin()
        customer_id = self.create_staff_user("customer", "search-orders@example.com")
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                """
                INSERT INTO orders
                    (order_number, user_id, status, total, tracking_status)
                VALUES ('SEARCH-ORDER', ?, 'Preparing', 250, 'Preparing')
                """,
                (customer_id,),
            )
            database.commit()

        product_page = self.client.get("/admin/menu")
        self.assertIn(b'id="adminProductSearch"', product_page.data)
        self.assertIn(b'id="adminCategoryFilter"', product_page.data)
        self.assertIn(b"data-admin-product", product_page.data)

        stock_page = self.client.get("/admin/stock")
        self.assertIn(b'id="adminStockSearch"', stock_page.data)
        self.assertIn(b'id="adminStockCategoryFilter"', stock_page.data)
        self.assertIn(b"data-admin-stock", stock_page.data)
        self.assertIn(b"All categories", stock_page.data)

        order_page = self.client.get("/admin/orders")
        self.assertIn(b'id="adminOrderSearch"', order_page.data)
        self.assertIn(b"data-admin-order", order_page.data)
        self.assertIn(b"SEARCH-ORDER", order_page.data)

    def test_customer_checkout_reserves_stock_and_rejects_unavailable_quantity(self):
        self.sign_in_customer()
        token = self.csrf_token("/customer/dashboard")
        self.client.post("/customer/cart/add/1", data={"csrf_token": token})

        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                "UPDATE food_items SET stock_quantity = 0 WHERE id = 1"
            )
            database.commit()

        checkout = self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
            follow_redirects=True,
        )

        self.assertIn(b"Only 0 Margherita Pizza are available.", checkout.data)
        with closing(sqlite3.connect(self.database_path)) as database:
            order_count = database.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            cart_count = database.execute("SELECT COUNT(*) FROM cart_items").fetchone()[0]
        self.assertEqual(order_count, 0)
        self.assertEqual(cart_count, 1)

        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                "UPDATE food_items SET stock_quantity = 1 WHERE id = 1"
            )
            database.commit()
        successful_checkout = self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
            follow_redirects=True,
        )
        self.assertIn(b"Order Accepted", successful_checkout.data)
        with closing(sqlite3.connect(self.database_path)) as database:
            stock_quantity = database.execute(
                "SELECT stock_quantity FROM food_items WHERE id = 1"
            ).fetchone()[0]
        self.assertEqual(stock_quantity, 0)

    def test_admin_order_status_assignment_customers_and_reports(self):
        self.sign_in_customer()
        self.client.post(
            "/customer/cart/add/1",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
        )
        delivery_id = self.create_staff_user("delivery", "driver@example.com")
        self.client.post(
            "/logout",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        self.sign_in_admin()

        orders_page = self.client.get("/admin/orders")
        self.assertEqual(orders_page.status_code, 200)
        self.assertIn(b"Sam Customer", orders_page.data)
        self.assertIn(b"Margherita Pizza", orders_page.data)

        status_update = self.client.post(
            "/admin/orders/1/status",
            data={
                "csrf_token": self.csrf_token("/admin/orders"),
                "status": "Out for Delivery",
            },
        )
        self.assertEqual(status_update.status_code, 302)
        assign = self.client.post(
            "/admin/orders/1/assign",
            data={
                "csrf_token": self.csrf_token("/admin/orders"),
                "delivery_person_id": str(delivery_id),
            },
        )
        self.assertEqual(assign.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as database:
            order = database.execute(
                "SELECT status, tracking_status, assigned_to, demo_auto_progress FROM orders WHERE id = 1"
            ).fetchone()
        self.assertEqual(order, ("Out for delivery", "Out for Delivery", delivery_id, 0))

        customers = self.client.get("/admin/customers")
        reports = self.client.get("/admin/reports")
        dashboard = self.client.get("/admin/dashboard")
        self.assertIn(b"Sam Customer", customers.data)
        self.assertIn(b"Daily sales summary", reports.data)
        self.assertIn(b"Test Delivery", self.client.get("/admin/orders").data)
        self.assertIn(b"Revenue overview", dashboard.data)

        unassign = self.client.post(
            "/admin/orders/1/assign",
            data={
                "csrf_token": self.csrf_token("/admin/orders"),
                "delivery_person_id": "0",
            },
        )
        self.assertEqual(unassign.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as database:
            assigned_to = database.execute(
                "SELECT assigned_to FROM orders WHERE id = 1"
            ).fetchone()[0]
        self.assertIsNone(assigned_to)

    def test_delivery_login_dashboard_and_status_transitions_are_assignment_scoped(self):
        self.sign_in_customer()
        self.client.post(
            "/customer/cart/add/1",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
        )
        assigned_delivery_id = self.create_staff_user(
            "delivery", "assigned@example.com"
        )
        other_delivery_id = self.create_staff_user("delivery", "other@example.com")
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                """
                UPDATE orders SET assigned_to = ?, tracking_status = 'Ready for Pickup'
                WHERE id = 1
                """,
                (assigned_delivery_id,),
            )
            database.commit()

        self.client.post(
            "/logout",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        login = self.client.post(
            "/delivery/login",
            data={
                "csrf_token": self.csrf_token("/delivery/login"),
                "email": "assigned@example.com",
                "password": "staff-password",
            },
        )
        self.assertEqual(login.status_code, 302)
        self.assertEqual(login.headers["Location"], "/delivery/dashboard")

        dashboard = self.client.get("/delivery/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        for expected in (
            b"Sam Customer",
            b"+91 98765 43210",
            b"12 Orange Street, Central City",
            b"Margherita Pizza",
            "₹339".encode("utf-8"),
            b"Ready for Pickup",
        ):
            self.assertIn(expected, dashboard.data)

        invalid_jump = self.client.post(
            "/delivery/orders/1/status",
            data={
                "csrf_token": self.csrf_token("/delivery/dashboard"),
                "status": "Delivered",
            },
        )
        self.assertEqual(invalid_jump.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as database:
            status_after_invalid_jump = database.execute(
                "SELECT tracking_status FROM orders WHERE id = 1"
            ).fetchone()[0]
            order_number = database.execute(
                "SELECT order_number FROM orders WHERE id = 1"
            ).fetchone()[0]
        self.assertEqual(status_after_invalid_jump, "Ready for Pickup")

        with self.client.session_transaction() as user_session:
            user_session["user_id"] = other_delivery_id
        self.assertNotIn(
            b"Sam Customer",
            self.client.get("/delivery/dashboard").data,
        )
        self.assertEqual(self.client.post("/delivery/orders/1/status").status_code, 404)
        with self.client.session_transaction() as user_session:
            user_session["user_id"] = assigned_delivery_id

        start_delivery = self.client.post(
            "/delivery/orders/1/status",
            data={
                "csrf_token": self.csrf_token("/delivery/dashboard"),
                "status": "Out for Delivery",
            },
        )
        self.assertEqual(start_delivery.status_code, 302)
        with closing(sqlite3.connect(self.database_path)) as database:
            updated_status = database.execute(
                "SELECT tracking_status, status, demo_auto_progress FROM orders WHERE id = 1"
            ).fetchone()
        self.assertEqual(updated_status, ("Out for Delivery", "Out for delivery", 0))

        mark_delivered = self.client.post(
            "/delivery/orders/1/status",
            data={
                "csrf_token": self.csrf_token("/delivery/dashboard"),
                "status": "Delivered",
            },
        )
        self.assertEqual(mark_delivered.status_code, 302)
        completed_dashboard = self.client.get("/delivery/dashboard")
        self.assertIn(b"Completed deliveries", completed_dashboard.data)
        self.assertIn(order_number.encode(), completed_dashboard.data)
        self.assertNotIn(b"Start delivery", completed_dashboard.data)
        with closing(sqlite3.connect(self.database_path)) as database:
            final_status = database.execute(
                "SELECT tracking_status, status, demo_auto_progress FROM orders WHERE id = 1"
            ).fetchone()
        self.assertEqual(final_status, ("Delivered", "Delivered", 0))

        with self.client.session_transaction() as user_session:
            user_session["user_id"] = other_delivery_id
        self.assertNotIn(
            b"Sam Customer",
            self.client.get("/delivery/dashboard").data,
        )
        self.assertEqual(self.client.post("/delivery/orders/1/status").status_code, 404)

    def test_delivery_routes_and_login_enforce_delivery_role(self):
        self.assertEqual(
            self.client.get("/delivery/dashboard").headers["Location"],
            "/delivery/login",
        )
        self.register_customer()
        response = self.client.post(
            "/login",
            data={
                "csrf_token": self.csrf_token("/login"),
                "email": "sam@example.com",
                "password": "correct-horse-42",
            },
        )
        self.assertEqual(response.headers["Location"], "/customer/dashboard")
        self.assertEqual(self.client.get("/delivery/dashboard").status_code, 403)

        staff_id = self.create_staff_user("admin", "admin-role@example.com")
        with self.client.session_transaction() as user_session:
            user_session["user_id"] = staff_id
        self.assertEqual(self.client.get("/delivery/dashboard").status_code, 403)

        with self.client.session_transaction() as user_session:
            user_session.clear()
        delivery_id = self.create_staff_user(
            "delivery", "delivery-admin-check@example.com"
        )
        with self.client.session_transaction() as user_session:
            user_session["user_id"] = delivery_id
        for path in (
            "/admin/",
            "/admin/menu",
            "/admin/customers",
            "/admin/orders",
            "/admin/reports",
        ):
            self.assertEqual(self.client.get(path).status_code, 403)

        with self.client.session_transaction() as user_session:
            user_session.clear()
        self.create_staff_user("delivery", "wrong-role@example.com")
        wrong_role_login = self.client.post(
            "/delivery/login",
            data={
                "csrf_token": self.csrf_token("/delivery/login"),
                "email": "wrong-role@example.com",
                "password": "wrong-password",
            },
        )
        self.assertEqual(wrong_role_login.status_code, 200)
        self.assertIn(b"Email or password is incorrect.", wrong_role_login.data)

    def test_order_tracking_routes_do_not_expose_another_customers_orders(self):
        self.sign_in_customer()
        self.client.post(
            "/customer/cart/add/1",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
        )
        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                """
                INSERT INTO users (name, email, phone, password_hash, role)
                VALUES ('Other Customer', 'other-tracking@example.com', '9876543210', 'unused', 'customer')
                """
            )
            other_customer_id = database.execute(
                "SELECT id FROM users WHERE email = 'other-tracking@example.com'"
            ).fetchone()[0]
            database.commit()

        with self.client.session_transaction() as user_session:
            user_session["user_id"] = other_customer_id
        self.assertEqual(self.client.get("/customer/orders/1").status_code, 404)
        self.assertEqual(self.client.get("/customer/orders").status_code, 200)
        self.assertEqual(self.client.get("/customer/orders/status").json["statuses"], [])

    def test_cart_and_orders_are_scoped_to_the_signed_in_customer(self):
        self.sign_in_customer()
        self.client.post(
            "/customer/cart/add/1",
            data={"csrf_token": self.csrf_token("/customer/dashboard")},
        )
        self.client.post(
            "/customer/checkout",
            data={
                "csrf_token": self.csrf_token("/customer/cart"),
                "delivery_address": "12 Orange Street, Central City",
                "delivery_phone": "+91 98765 43210",
            },
        )

        with closing(sqlite3.connect(self.database_path)) as database:
            database.execute(
                """
                INSERT INTO users (name, email, phone, password_hash, role)
                VALUES ('Other Customer', 'other@example.com', '9876543210', 'unused', 'customer')
                """
            )
            other_customer_id = database.execute(
                "SELECT id FROM users WHERE email = 'other@example.com'"
            ).fetchone()[0]
            database.commit()

        with self.client.session_transaction() as user_session:
            user_session["user_id"] = other_customer_id
        cart_page = self.client.get("/customer/cart")
        dashboard = self.client.get("/customer/dashboard")

        self.assertEqual(cart_page.status_code, 200)
        self.assertNotIn(b"Margherita Pizza", cart_page.data)
        self.assertNotIn(b"ID 1", dashboard.data)
        with closing(sqlite3.connect(self.database_path)) as database:
            original_customer_id = database.execute(
                "SELECT id FROM users WHERE email = 'sam@example.com'"
            ).fetchone()[0]
            cart_count = database.execute(
                "SELECT COUNT(*) FROM cart_items WHERE user_id = ?",
                (original_customer_id,),
            ).fetchone()[0]
            order_count = database.execute(
                "SELECT COUNT(*) FROM orders WHERE user_id = ?",
                (original_customer_id,),
            ).fetchone()[0]
        self.assertEqual(cart_count, 0)
        self.assertEqual(order_count, 1)

    def test_existing_order_database_is_migrated_with_legacy_totals_preserved(self):
        legacy_path = f"{self.temporary_directory.name}/legacy.sqlite3"
        with closing(sqlite3.connect(legacy_path)) as database:
            database.execute(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Preparing',
                    total INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            database.execute(
                "INSERT INTO orders (order_number, user_id, total) VALUES ('LEGACY1', 1, 299)"
            )
            database.commit()

        create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test-secret-key",
                "DATABASE": legacy_path,
            }
        )

        with closing(sqlite3.connect(legacy_path)) as database:
            order = database.execute(
                """
                SELECT subtotal, delivery_fee, total, delivery_address, delivery_phone
                FROM orders WHERE order_number = 'LEGACY1'
                """
            ).fetchone()
        self.assertEqual(order, (299, 0, 299, "", ""))
        with closing(sqlite3.connect(legacy_path)) as database:
            tracking_status = database.execute(
                "SELECT tracking_status FROM orders WHERE order_number = 'LEGACY1'"
            ).fetchone()[0]
            columns = {
                row[1] for row in database.execute("PRAGMA table_info(orders)")
            }
        self.assertEqual(tracking_status, "Preparing")
        self.assertIn("assigned_to", columns)

    def test_cart_mutations_require_login_and_csrf(self):
        self.assertEqual(self.client.get("/customer/cart").headers["Location"], "/login")
        self.assertEqual(self.client.get("/customer/orders").headers["Location"], "/login")
        self.assertEqual(
            self.client.get("/customer/orders/1").headers["Location"],
            "/login",
        )
        self.assertEqual(
            self.client.post("/customer/cart/add/1").headers["Location"],
            "/login",
        )

        self.sign_in_customer()
        response = self.client.post("/customer/cart/add/1", data={})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/customer/dashboard#food-menu")
        with closing(sqlite3.connect(self.database_path)) as database:
            count = database.execute("SELECT COUNT(*) FROM cart_items").fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
