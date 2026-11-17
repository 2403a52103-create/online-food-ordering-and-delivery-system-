# Online Food Ordering and Delivery System

A beginner-friendly Flask, SQLite, HTML, CSS, and JavaScript project with a responsive FoodExpress landing page and customer, admin, and delivery-person areas.

## Project structure

```text
SESD_project/
|-- app.py
|-- config.py
|-- requirements.txt
|-- README.md
|-- .gitignore
|-- database/
|   |-- db.py
|   `-- schema.sql
|-- routes/
|   |-- __init__.py
|   |-- auth.py
|   |-- customer.py
|   |-- admin.py
|   `-- delivery.py
|-- templates/
|   |-- base.html
|   |-- index.html
|   |-- partials/
|   |   `-- food_card.html
|   |-- auth/
|   |   |-- login.html
|   |   `-- register.html
|   |-- customer/
|   |   |-- menu.html
|   |   |-- cart.html
|   |   |-- orders.html
|   |   `-- dashboard.html
|   |-- admin/
|   |   |-- dashboard.html
|   |   |-- menu.html
|   |   `-- orders.html
|   `-- delivery/
|       |-- dashboard.html
|       `-- login.html
|-- static/
|   |-- css/
|   |   `-- style.css
|   |-- js/
|   |   `-- main.js
|   `-- images/
`-- tests/
    `-- test_app.py
```

## What each file is for

| File | Purpose |
|---|---|
| `app.py` | Creates the Flask application, configures sessions and SQLite, provides sample menu data, and connects the site pages to their routes. |
| `config.py` | Reserved for future application settings; current session and database settings are initialized in `app.py`. |
| `requirements.txt` | Lists Flask, Flask-WTF, and WTForms for secure form validation and CSRF protection. |
| `README.md` | Documents the project structure and how to get started. |
| `.gitignore` | Keeps Python caches, virtual environments, and generated SQLite databases out of Git. |
| `database/db.py` | Opens and closes SQLite connections, initializes the schema, and migrates existing food and order tables for inventory and delivery tracking. |
| `database/schema.sql` | Defines users, menu items and stock, carts, orders, and order-item tables with constraints and indexes. |
| `routes/__init__.py` | Marks and describes the route modules package. |
| `routes/auth.py` | Validates registration/login forms, hashes and verifies passwords, manages sessions, and handles logout. |
| `routes/customer.py` | Loads the customer dashboard, cart, order history and order details; securely handles customer-scoped cart updates, inventory-checked checkout, and status polling. |
| `routes/admin.py` | Role-protected admin sign-in, dashboard metrics and stock alerts, food CRUD, customer and order views, order status/assignment actions, and sales reports. |
| `routes/delivery.py` | Delivery-role sign-in, assigned-order dashboard, and assigned-order status transitions. |
| `templates/base.html` | Shared navigation, footer, and HTML layout used by every page. |
| `templates/index.html` | Responsive FoodExpress home page with hero, search, categories, popular food, about, and contact sections. |
| `templates/partials/food_card.html` | Reusable food item card included on the home and menu pages. |
| `templates/auth/login.html` | CSRF-protected customer login form with field and sign-in feedback. |
| `templates/auth/register.html` | CSRF-protected registration form with field validation and feedback. |
| `templates/customer/dashboard.html` | Responsive customer dashboard with menu search/filter, cart, recent orders, tracking, profile, and logout. |
| `templates/customer/menu.html` | Menu page with searchable food cards. |
| `templates/customer/cart.html` | Responsive customer cart and checkout page with editable quantities, delivery details, and an itemized order summary. |
| `templates/customer/orders.html` | Customer-scoped order history and live status tracking page. |
| `templates/customer/order_detail.html` | Customer-scoped individual order detail and delivery tracking page. |
| `templates/partials/order_progress.html` | Shared five-stage order progress display. |
| `templates/admin/base.html` | Responsive admin navigation and shared admin page layout. |
| `templates/admin/login.html` | CSRF-protected admin-only sign-in form. |
| `templates/admin/dashboard.html` | Admin metrics, recent orders, and seven-day revenue chart. |
| `templates/admin/menu.html` | Admin product create/list/search/category filter, edit, and deactivate page. |
| `templates/admin/stock.html` | Stock levels, stock status, and CSRF-protected quantity updates. |
| `templates/admin/food_form.html` | Admin food item editing form. |
| `templates/admin/customers.html` | Registered customer directory. |
| `templates/admin/orders.html` | Order list, tracking status controls, and delivery assignment forms. |
| `templates/admin/reports.html` | Daily order/revenue table and Chart.js report. |
| `templates/delivery/login.html` | Delivery-person-only sign-in form. |
| `templates/delivery/dashboard.html` | Assigned deliveries, customer contact/address, order items, status actions, and completed deliveries. |
| `static/css/style.css` | Responsive styles, layout, and colors shared by the pages, including cart, checkout, and order tracking. |
| `static/js/main.js` | Mobile navigation, menu search and category filters, cart quantity controls, dashboard navigation, and periodic order-status refresh. |
| `tests/test_app.py` | Automated tests for page routes, authentication, validation, role access, customer and delivery-order ownership, status transitions, cart, checkout, CSRF, sessions, and logout. |

Food photos are loaded from Unsplash URLs, so they require an internet connection. The `static/images/` folder is available for local assets. The homepage, customer dashboard, and menu page load active food items from SQLite. Startup seeds at least 20 sample dishes in each category: Pizza, Burger, Biryani, Chinese, South Indian, and Desserts. Each seeded dish has its own photo; startup refreshes the sample dishes' image URLs for existing databases, and restarts do not create duplicate dishes. The menu page supports name search, category filters, and CSRF-protected add-to-cart forms. Customer registration, login, persistent customer-scoped carts, quantity changes, item removal, checkout, order history, and order-status display are implemented. Food items track stock: customers cannot add or checkout more than the available quantity, and successful checkout reserves stock. New demo orders automatically progress to Preparing at 1 minute, Ready for Pickup at 2 minutes, Out for Delivery at 3 minutes, and Delivered at 5 minutes; set `DEMO_AUTO_PROGRESS_ORDERS=0` to disable this demo behavior. Checkout validates a delivery address and phone server-side, calculates the subtotal plus a fixed ₹40 delivery fee, saves an order and item snapshots transactionally, and clears only that customer's cart. Existing SQLite databases receive stock, order detail, tracking, and delivery-assignment columns on startup.

The admin area at `/admin/login` uses an orange, white, and cream theme with a left navigation sidebar and Bootstrap styling. Its dashboard shows exactly four live summary cards: total active products, total available stock units, pending orders (excluding delivered/cancelled), and completed orders (Delivered only). The Products/Menu page supports add, edit, soft-delete, search, and category filtering. Product name, price, category, and stock are required; rating, description, and image are optional. The Stock Management page labels quantities above 10 as In Stock, 1–10 as Low Stock, and zero as Out of Stock; it accepts non-negative updates only. Order Management filters All, Pending, and Completed orders and retains status updates and delivery-person assignment. Existing customer and delivery pages are unchanged. Admin routes are role-protected; customer and delivery accounts cannot access them.

Delivery staff sign in at `/delivery/login` and see only their assigned orders at `/delivery/dashboard`; they can advance an assigned order from Ready for Pickup to Out for Delivery and then Delivered. Admin and delivery roles cannot be registered publicly. Provision them interactively with `flask --app app create-staff --role admin` or `flask --app app create-staff --role delivery`; the command prompts for account details and a password, storing only its password hash. Chart.js is loaded from a CDN for revenue charts. SQLite stores its database at `instance/foodexpress.sqlite3`.

## Run the app

Create and activate a virtual environment, then install the dependencies and start Flask:

```text
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

For local development, the app generates a random session secret when `FLASK_SECRET_KEY` is not set. This invalidates existing sessions when the app restarts. Set a long, random `FLASK_SECRET_KEY` to keep sessions stable, and set `SESSION_COOKIE_SECURE=1` when serving the app over HTTPS. Do not use Flask's development server in production.

Open `http://127.0.0.1:5000/register` to create a customer account, then log in at `http://127.0.0.1:5000/login`. Successful login opens the dashboard at `http://127.0.0.1:5000/customer/dashboard`. Add dishes to the cart and open `http://127.0.0.1:5000/customer/cart` to update quantities, remove items, enter delivery details, review the order summary, and place an order. View all orders at `http://127.0.0.1:5000/customer/orders`; open any order to see its itemized details, delivery address, and tracked status. Status updates are fetched automatically every 20 seconds. Use the profile/logout section to end the session.

To provision a new administrator or delivery account for local use, run `python -m flask --app app create-staff --role admin` or `python -m flask --app app create-staff --role delivery`, then sign in at `http://127.0.0.1:5000/admin/login`. Public registration always creates a customer account. To promote one of your existing customer accounts for local development, run `python -m flask --app app promote-customer-to-admin --email your@email.com` and confirm the prompt; then use that account's existing password at the admin sign-in page. Admin pages reject unauthenticated users and return HTTP 403 to non-admin accounts.

## Manually test the admin dashboard

1. Start the server with `python app.py`, provision an admin account using `python -m flask --app app create-staff --role admin`, and sign in at `/admin/login`.
2. Verify the dashboard shows the four live summary cards and recent orders. The counts come from the current SQLite database.
3. Open Products/Menu, add a product with name, price, category, and stock while leaving rating, description, and image blank. Confirm it appears in the list; edit its fields, then delete it and verify it is no longer active.
4. Open Stock Management and set quantities to 11, 10, and 0 on separate products. Confirm the labels become In Stock, Low Stock, and Out of Stock. Try a negative value; the server must reject it.
5. Place an order as a customer. Verify stock decreases only after checkout succeeds, and that trying to order more than available stock is rejected.
6. Open Orders and check the All, Pending, and Completed filters. Set an order to Delivered and confirm it appears in Completed; cancelled orders should not count as Pending or Completed.
7. Sign in as a customer or delivery account and try `/admin/dashboard`, `/admin/products`, and `/admin/stock`; each must be denied. Do not delete the SQLite database when testing existing records.

Delivery staff can sign in at `http://127.0.0.1:5000/delivery/login`. An administrator must assign an order to that delivery account and set its status to `Ready for Pickup` before the delivery person can advance it.

## Run the automated tests

The `tests/` folder contains isolated Flask `unittest` cases. Each test creates a temporary SQLite database and uses fictional accounts and addresses (for example, `sam@example.com` and `12 Orange Street`); it does not use real customer data. Tests cover customer registration and duplicate emails, valid and invalid sign-in, menu search controls and searchable food markup, adding/removing cart items, order totals and checkout persistence, and admin access control, along with validation, CSRF, delivery-role, and order-ownership behavior.

Run all tests from the project root with:

```text
python -m unittest discover -s tests
```

Expected result (timings may vary):

```text
Ran ... tests in ...s

OK
```

For verbose test names and individual pass/fail results, run `python -m unittest discover -s tests -v`.
