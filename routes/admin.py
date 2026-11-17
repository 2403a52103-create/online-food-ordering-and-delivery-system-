from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from wtforms import (
    FloatField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.fields.choices import SelectChoice
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)
from werkzeug.security import check_password_hash

from database.db import get_db
from routes.auth import LogoutForm, strip_text


admin = Blueprint("admin", __name__, url_prefix="/admin")

CATEGORIES = (
    SelectChoice(value="pizza", label="Pizza"),
    SelectChoice(value="burger", label="Burger"),
    SelectChoice(value="biryani", label="Biryani"),
    SelectChoice(value="chinese", label="Chinese"),
    SelectChoice(value="south-indian", label="South Indian"),
    SelectChoice(value="desserts", label="Desserts"),
)
ORDER_STATUSES = (
    "Order Accepted",
    "Preparing",
    "Ready for Pickup",
    "Out for Delivery",
    "Delivered",
    "Cancelled",
)
LEGACY_STATUS = {
    "Order Accepted": "Preparing",
    "Preparing": "Preparing",
    "Ready for Pickup": "Preparing",
    "Out for Delivery": "Out for delivery",
    "Delivered": "Delivered",
    "Cancelled": "Cancelled",
}


class AdminLoginForm(FlaskForm):
    email = StringField(
        "Email address",
        filters=[strip_text],
        validators=[DataRequired(), Length(max=254), Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")],
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    submit = SubmitField("Sign in")


class FoodForm(FlaskForm):
    name = StringField(
        "Food name",
        filters=[strip_text],
        validators=[DataRequired(), Length(min=2, max=100)],
    )
    description = TextAreaField(
        "Description",
        filters=[strip_text],
        validators=[Optional(), Length(max=500)],
    )
    price = IntegerField(
        "Price (₹)",
        validators=[InputRequired(), NumberRange(min=0, max=1000000)],
    )
    rating = FloatField(
        "Rating (optional, 0–5)",
        validators=[Optional(), NumberRange(min=0, max=5)],
    )
    stock_quantity = IntegerField(
        "Stock quantity",
        validators=[InputRequired(), NumberRange(min=0, max=1000000)],
        default=20,
    )
    category = SelectField("Category", choices=CATEGORIES, validators=[DataRequired()])
    image = StringField(
        "Image URL or /static path (optional)",
        filters=[strip_text],
        validators=[Optional(), Length(max=500)],
    )
    submit = SubmitField("Save food item")

    def validate_image(self, field):
        image = field.data
        if not image:
            return
        parsed = urlparse(image)
        if image.startswith("/static/"):
            return
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValidationError("Enter an http(s) image URL or a path beginning with /static/.")


class OrderStatusForm(FlaskForm):
    status = SelectField(
        "Order status",
        choices=[SelectChoice(value=status, label=status) for status in ORDER_STATUSES],
        validators=[DataRequired()],
    )
    submit = SubmitField("Update status")


class StockUpdateForm(FlaskForm):
    stock_quantity = IntegerField(
        "Available stock",
        validators=[InputRequired(), NumberRange(min=0, max=1000000)],
    )
    submit = SubmitField("Update stock")


class AssignOrderForm(FlaskForm):
    delivery_person_id = SelectField("Delivery person", coerce=int, validators=[InputRequired()])
    submit = SubmitField("Assign")


class AdminLogoutForm(FlaskForm):
    submit = SubmitField("Log out")


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return redirect(url_for("admin.login"))
        g.admin_user = get_db().execute(
            "SELECT id, name, email, role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if g.admin_user is None:
            session.clear()
            abort(403)
        if g.admin_user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


def load_delivery_people():
    return get_db().execute(
        "SELECT id, name FROM users WHERE role = 'delivery' ORDER BY name COLLATE NOCASE"
    ).fetchall()


def form_for_order(order, delivery_people):
    status_form = OrderStatusForm(status=order["tracking_status"])
    assignment_form = AssignOrderForm(
        delivery_person_id=order["assigned_to"] or 0,
    )
    assignment_form.delivery_person_id.choices = [SelectChoice(value="0", label="Unassigned")] + [
        SelectChoice(value=str(person["id"]), label=person["name"])
        for person in delivery_people
    ]
    return status_form, assignment_form


@admin.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        user = get_db().execute(
            "SELECT role FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()
        if user and user["role"] == "admin":
            return redirect(url_for("admin.dashboard"))
        if user and user["role"] == "delivery":
            return redirect(url_for("delivery.dashboard"))
        if user is None:
            session.clear()

    form = AdminLoginForm()
    if form.validate_on_submit():
        user = get_db().execute(
            "SELECT id, password_hash, role FROM users WHERE email = ? COLLATE NOCASE",
            (form.email.data.lower(),),
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], form.password.data):
            flash("Email or password is incorrect.", "error")
        elif user["role"] != "admin":
            flash(
                "This account is not an administrator. Accounts created through customer registration "
                "must be promoted before they can use the admin dashboard.",
                "error",
            )
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("admin.dashboard"))
    return render_template("admin/login.html", form=form)


@admin.route("/logout", methods=["POST"])
@admin_required
def logout():
    form = AdminLogoutForm()
    if not form.validate_on_submit():
        flash("Your session expired. Please try again.", "error")
        return redirect(url_for("admin.dashboard"))
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin.login"))


@admin.route("/")
@admin.route("/dashboard")
@admin_required
def dashboard():
    database = get_db()
    stats = database.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM food_items WHERE active = 1) AS total_products,
            (SELECT COALESCE(SUM(stock_quantity), 0)
             FROM food_items WHERE active = 1) AS available_stock,
            (SELECT COUNT(*) FROM orders
             WHERE tracking_status = 'Delivered') AS completed_orders,
            (SELECT COUNT(*) FROM orders
             WHERE tracking_status NOT IN ('Delivered', 'Cancelled')) AS pending_orders
        """
    ).fetchone()
    low_stock_items = database.execute(
        """
        SELECT id, name, category, stock_quantity
        FROM food_items
        WHERE active = 1 AND stock_quantity <= 10
        ORDER BY stock_quantity, name COLLATE NOCASE
        LIMIT 8
        """
    ).fetchall()
    recent_orders = database.execute(
        """
        SELECT o.id, o.order_number, o.tracking_status, o.total, o.created_at,
               u.name AS customer_name, d.name AS delivery_name
        FROM orders AS o
        JOIN users AS u ON u.id = o.user_id
        LEFT JOIN users AS d ON d.id = o.assigned_to AND d.role = 'delivery'
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT 8
        """
    ).fetchall()
    report_rows = database.execute(
        """
        SELECT substr(created_at, 1, 10) AS day, COALESCE(SUM(total), 0) AS revenue
        FROM orders
        WHERE tracking_status != 'Cancelled'
          AND created_at >= date('now', '-6 days')
        GROUP BY substr(created_at, 1, 10)
        ORDER BY day
        """
    ).fetchall()
    return render_template(
        "admin/dashboard.html",
        admin_user=g.admin_user,
        stats=stats,
        recent_orders=recent_orders,
        low_stock_items=low_stock_items,
        report_days=[row["day"] for row in report_rows],
        report_revenue=[row["revenue"] for row in report_rows],
        logout_form=AdminLogoutForm(),
    )


@admin.route("/products")
@admin.route("/menu")
@admin_required
def menu():
    database = get_db()
    foods = database.execute(
        """
        SELECT id, name, description, price, category, image, rating, stock_quantity
        FROM food_items WHERE active = 1 ORDER BY id DESC
        """
    ).fetchall()
    categories = database.execute(
        """
        SELECT DISTINCT category FROM food_items
        WHERE active = 1 ORDER BY category COLLATE NOCASE
        """
    ).fetchall()
    return render_template(
        "admin/menu.html",
        admin_user=g.admin_user,
        foods=foods,
        categories=categories,
        food_form=FoodForm(),
        logout_form=AdminLogoutForm(),
    )


@admin.route("/stock")
@admin_required
def stock():
    database = get_db()
    foods = database.execute(
        """
        SELECT id, name, category, image, stock_quantity
        FROM food_items
        WHERE active = 1
        ORDER BY stock_quantity, name COLLATE NOCASE
        """
    ).fetchall()
    categories = database.execute(
        """
        SELECT DISTINCT category FROM food_items
        WHERE active = 1 ORDER BY category COLLATE NOCASE
        """
    ).fetchall()
    stock_forms = {
        food["id"]: StockUpdateForm(stock_quantity=food["stock_quantity"])
        for food in foods
    }
    return render_template(
        "admin/stock.html",
        admin_user=g.admin_user,
        foods=foods,
        categories=categories,
        stock_forms=stock_forms,
        logout_form=AdminLogoutForm(),
    )


@admin.route("/stock/<int:food_id>", methods=["POST"])
@admin_required
def update_stock(food_id):
    form = StockUpdateForm()
    if not form.validate_on_submit():
        flash("Enter a stock quantity from 0 to 1,000,000.", "error")
        return redirect(url_for("admin.stock"))

    database = get_db()
    cursor = database.execute(
        """
        UPDATE food_items SET stock_quantity = ?
        WHERE id = ? AND active = 1
        """,
        (form.stock_quantity.data, food_id),
    )
    database.commit()
    if not cursor.rowcount:
        flash("Product was not found.", "error")
    else:
        flash("Stock quantity updated.", "success")
    return redirect(url_for("admin.stock"))


@admin.route("/menu/add", methods=["POST"])
@admin_required
def add_food():
    form = FoodForm()
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(error, "error")
        return redirect(url_for("admin.menu"))
    database = get_db()
    database.execute(
        """
        INSERT INTO food_items
            (name, description, price, category, image, rating, badge, stock_quantity)
        VALUES (?, ?, ?, ?, ?, ?, 'Admin pick', ?)
        """,
        (
            form.name.data,
            form.description.data or "",
            form.price.data,
            form.category.data,
            form.image.data or "",
            f"{form.rating.data:g}" if form.rating.data is not None else "",
            form.stock_quantity.data,
        ),
    )
    database.commit()
    flash("Food item added.", "success")
    return redirect(url_for("admin.menu"))


@admin.route("/menu/<int:food_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_food(food_id):
    database = get_db()
    food = database.execute(
        "SELECT * FROM food_items WHERE id = ? AND active = 1", (food_id,)
    ).fetchone()
    if food is None:
        abort(404)
    form = FoodForm(obj=food)
    if form.validate_on_submit():
        database.execute(
            """
            UPDATE food_items
            SET name = ?, description = ?, price = ?, category = ?, image = ?,
                rating = ?, stock_quantity = ?
            WHERE id = ? AND active = 1
            """,
            (
                form.name.data,
                form.description.data or "",
                form.price.data,
                form.category.data,
                form.image.data or "",
                f"{form.rating.data:g}" if form.rating.data is not None else "",
                form.stock_quantity.data,
                food_id,
            ),
        )
        database.commit()
        flash("Food item updated.", "success")
        return redirect(url_for("admin.menu"))
    return render_template(
        "admin/food_form.html",
        admin_user=g.admin_user,
        form=form,
        food=food,
        logout_form=AdminLogoutForm(),
    )


@admin.route("/menu/<int:food_id>/delete", methods=["POST"])
@admin_required
def delete_food(food_id):
    form = FlaskForm()
    if not form.validate_on_submit():
        flash("Your session expired. Refresh and try again.", "error")
        return redirect(url_for("admin.menu"))
    database = get_db()
    database.execute("BEGIN IMMEDIATE")
    cursor = database.execute(
        "UPDATE food_items SET active = 0 WHERE id = ? AND active = 1",
        (food_id,),
    )
    if cursor.rowcount:
        database.execute("DELETE FROM cart_items WHERE food_id = ?", (food_id,))
        database.commit()
        flash("Food item removed from the menu.", "success")
    else:
        database.rollback()
        flash("Food item was not found.", "error")
    return redirect(url_for("admin.menu"))


@admin.route("/customers")
@admin_required
def customers():
    customer_rows = get_db().execute(
        """
        SELECT u.id, u.name, u.email, u.phone, u.created_at,
               COUNT(o.id) AS order_count
        FROM users AS u
        LEFT JOIN orders AS o ON o.user_id = u.id
        WHERE u.role = 'customer'
        GROUP BY u.id
        ORDER BY u.created_at DESC, u.id DESC
        """
    ).fetchall()
    return render_template(
        "admin/customers.html",
        admin_user=g.admin_user,
        customers=customer_rows,
        logout_form=AdminLogoutForm(),
    )


@admin.route("/orders")
@admin_required
def orders():
    database = get_db()
    delivery_people = load_delivery_people()
    status_counts = database.execute(
        """
        SELECT COUNT(*) AS all_orders,
               COALESCE(SUM(CASE WHEN tracking_status NOT IN
                    ('Delivered', 'Cancelled') THEN 1 ELSE 0 END), 0) AS pending_orders,
               COALESCE(SUM(CASE WHEN tracking_status = 'Delivered'
                    THEN 1 ELSE 0 END), 0) AS completed_orders
        FROM orders
        """
    ).fetchone()
    order_filter = request.args.get("status", "all")
    filter_conditions = {
        "all": "1 = 1",
        "pending": "o.tracking_status NOT IN ('Delivered', 'Cancelled')",
        "completed": "o.tracking_status = 'Delivered'",
    }
    if order_filter not in filter_conditions:
        order_filter = "all"
    order_rows = database.execute(
        f"""
        SELECT o.id, o.order_number, o.tracking_status, o.total, o.created_at,
               o.delivery_address, u.name AS customer_name, u.email AS customer_email,
               d.name AS delivery_name, o.assigned_to
        FROM orders AS o
        JOIN users AS u ON u.id = o.user_id
        LEFT JOIN users AS d ON d.id = o.assigned_to AND d.role = 'delivery'
        WHERE {filter_conditions[order_filter]}
        ORDER BY o.created_at DESC, o.id DESC
        """
    ).fetchall()
    items = database.execute(
        """
        SELECT oi.order_id, oi.food_name, oi.quantity
        FROM order_items AS oi
        JOIN orders AS o ON o.id = oi.order_id
        ORDER BY oi.id
        """
    ).fetchall()
    items_by_order = {}
    for item in items:
        items_by_order.setdefault(item["order_id"], []).append(item)
    order_forms = {}
    for order in order_rows:
        order_forms[order["id"]] = form_for_order(order, delivery_people)
    return render_template(
        "admin/orders.html",
        admin_user=g.admin_user,
        orders=order_rows,
        items_by_order=items_by_order,
        order_forms=order_forms,
        delivery_people=delivery_people,
        order_filter=order_filter,
        status_counts=status_counts,
        logout_form=AdminLogoutForm(),
    )


@admin.route("/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    form = OrderStatusForm()
    if not form.validate_on_submit():
        flash("Choose a valid order status.", "error")
        return redirect(url_for("admin.orders", status=request.args.get("status", "all")))
    database = get_db()
    cursor = database.execute(
        """
        UPDATE orders
        SET tracking_status = ?, status = ?, demo_auto_progress = 0
        WHERE id = ?
        """,
        (form.status.data, LEGACY_STATUS[form.status.data], order_id),
    )
    database.commit()
    if not cursor.rowcount:
        flash("Order was not found.", "error")
    else:
        flash("Order status updated.", "success")
    return redirect(url_for("admin.orders", status=request.args.get("status", "all")))


@admin.route("/orders/<int:order_id>/assign", methods=["POST"])
@admin_required
def assign_delivery(order_id):
    form = AssignOrderForm()
    delivery_people = load_delivery_people()
    form.delivery_person_id.choices = [SelectChoice(value="0", label="Unassigned")] + [
        SelectChoice(value=str(person["id"]), label=person["name"])
        for person in delivery_people
    ]
    if not form.validate_on_submit():
        flash("Choose a valid delivery person.", "error")
        return redirect(url_for("admin.orders", status=request.args.get("status", "all")))
    person_id = form.delivery_person_id.data
    database = get_db()
    if person_id:
        person = database.execute(
            "SELECT id FROM users WHERE id = ? AND role = 'delivery'",
            (person_id,),
        ).fetchone()
        if person is None:
            abort(400)
    cursor = database.execute(
        "UPDATE orders SET assigned_to = ? WHERE id = ?",
        (person_id or None, order_id),
    )
    database.commit()
    if not cursor.rowcount:
        flash("Order was not found.", "error")
    else:
        flash("Delivery assignment updated.", "success")
    return redirect(url_for("admin.orders", status=request.args.get("status", "all")))


@admin.route("/reports")
@admin_required
def reports():
    rows = get_db().execute(
        """
        SELECT substr(created_at, 1, 10) AS day,
               COUNT(*) AS order_count,
               COALESCE(SUM(total), 0) AS revenue
        FROM orders
        WHERE tracking_status != 'Cancelled'
        GROUP BY substr(created_at, 1, 10)
        ORDER BY day DESC
        LIMIT 30
        """
    ).fetchall()
    return render_template(
        "admin/reports.html",
        admin_user=g.admin_user,
        reports=rows,
        chart_days=[row["day"] for row in reversed(rows)],
        chart_revenue=[row["revenue"] for row in reversed(rows)],
        logout_form=AdminLogoutForm(),
    )
