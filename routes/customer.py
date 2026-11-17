from datetime import date
from functools import wraps
import secrets

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf import FlaskForm
from wtforms import HiddenField, IntegerField, StringField, SubmitField, TextAreaField
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Regexp,
    ValidationError,
)

from database.db import get_db
from routes.auth import LogoutForm


customer = Blueprint("customer", __name__, url_prefix="/customer")
DELIVERY_FEE = 40
PHONE_PATTERN = r"^\+?[0-9][0-9 ()-]*$"
ORDER_STAGES = (
    "Order Accepted",
    "Preparing",
    "Ready for Pickup",
    "Out for Delivery",
    "Delivered",
)


class ActionForm(FlaskForm):
    submit = SubmitField()


class CartUpdateForm(FlaskForm):
    item_id = HiddenField(validators=[InputRequired()])
    quantity = IntegerField(validators=[InputRequired(), NumberRange(min=1, max=99)])
    submit = SubmitField("Update")


class CheckoutForm(FlaskForm):
    delivery_address = TextAreaField(
        "Delivery address",
        filters=[lambda value: value.strip() if isinstance(value, str) else value],
        validators=[DataRequired(), Length(min=8, max=500)],
    )
    delivery_phone = StringField(
        "Delivery phone",
        filters=[lambda value: value.strip() if isinstance(value, str) else value],
        validators=[
            DataRequired(),
            Length(max=20),
            Regexp(PHONE_PATTERN, message="Enter a valid phone number."),
        ],
    )
    submit = SubmitField("Place order")

    def validate_delivery_phone(self, field):
        if not 7 <= sum(character.isdigit() for character in field.data) <= 15:
            raise ValidationError("Phone number must contain 7 to 15 digits.")


def load_cart_items(user_id):
    return get_db().execute(
        """
        SELECT ci.id, ci.quantity, fi.id AS food_id, fi.name, fi.description,
               fi.category, fi.price, fi.image, fi.stock_quantity,
               (ci.quantity * fi.price) AS line_total
        FROM cart_items AS ci
        JOIN food_items AS fi ON fi.id = ci.food_id
        WHERE ci.user_id = ? AND fi.active = 1
        ORDER BY ci.id
        """,
        (user_id,),
    ).fetchall()


def render_cart_page(form=None, status=200):
    items = load_cart_items(g.customer["id"])
    subtotal = sum(item["line_total"] for item in items)
    if form is None:
        form = CheckoutForm(delivery_phone=g.customer["phone"])
    return (
        render_template(
            "customer/cart.html",
            customer=g.customer,
            cart_items=items,
            cart_count=sum(item["quantity"] for item in items),
            subtotal=subtotal,
            delivery_fee=DELIVERY_FEE if items else 0,
            total=subtotal + (DELIVERY_FEE if items else 0),
            checkout_form=form,
            update_form=CartUpdateForm(),
            remove_form=ActionForm(),
        ),
        status,
    )


def customer_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return redirect(url_for("auth.login"))

        g.customer = get_db().execute(
            "SELECT id, name, email, phone FROM users WHERE id = ? AND role = 'customer'",
            (user_id,),
        ).fetchone()
        if g.customer is None:
            session.clear()
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped_view


def cart_item_count(user_id):
    row = get_db().execute(
        "SELECT COALESCE(SUM(quantity), 0) AS item_count FROM cart_items WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return row["item_count"]


def order_for_customer(order_id, customer_id):
    database = get_db()
    order = database.execute(
        """
        SELECT id, order_number, status, tracking_status, subtotal, delivery_fee,
               total, delivery_address, delivery_phone, created_at
        FROM orders
        WHERE id = ? AND user_id = ?
        """,
        (order_id, customer_id),
    ).fetchone()
    if order is None:
        return None

    order = dict(order)
    order["stage_index"] = (
        ORDER_STAGES.index(order["tracking_status"])
        if order["tracking_status"] in ORDER_STAGES
        else -1
    )
    order["items"] = database.execute(
        """
        SELECT food_name, unit_price, quantity, unit_price * quantity AS line_total
        FROM order_items
        WHERE order_id = ?
        ORDER BY id
        """,
        (order_id,),
    ).fetchall()
    return order


@customer.route("/dashboard")
@customer_required
def dashboard():
    database = get_db()
    customer_id = g.customer["id"]
    foods = database.execute(
        "SELECT * FROM food_items WHERE active = 1 ORDER BY id"
    ).fetchall()
    categories = database.execute(
        """
        SELECT DISTINCT category
        FROM food_items
        WHERE active = 1
        ORDER BY CASE category
            WHEN 'pizza' THEN 1
            WHEN 'burger' THEN 2
            WHEN 'biryani' THEN 3
            WHEN 'chinese' THEN 4
            WHEN 'south-indian' THEN 5
            WHEN 'desserts' THEN 6
            ELSE 7
        END, category COLLATE NOCASE
        """
    ).fetchall()
    cart_items = load_cart_items(customer_id)
    cart_total = sum(item["line_total"] for item in cart_items)
    orders = [
        dict(order)
        for order in database.execute(
            """
            SELECT id, order_number, tracking_status, total, created_at
            FROM orders
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 10
            """,
            (customer_id,),
        ).fetchall()
    ]
    for order in orders:
        order["stage_index"] = (
            ORDER_STAGES.index(order["tracking_status"])
            if order["tracking_status"] in ORDER_STAGES
            else -1
        )
    order_items = database.execute(
        """
        SELECT oi.order_id, oi.food_name, oi.unit_price, oi.quantity
        FROM order_items AS oi
        JOIN orders AS o ON o.id = oi.order_id
        WHERE o.user_id = ? AND o.id IN (
            SELECT id FROM orders WHERE user_id = ?
            ORDER BY created_at DESC, id DESC LIMIT 10
        )
        ORDER BY oi.id
        """,
        (customer_id, customer_id),
    ).fetchall()
    items_by_order = {}
    for item in order_items:
        items_by_order.setdefault(item["order_id"], []).append(item)

    return render_template(
        "customer/dashboard.html",
        customer=g.customer,
        today=date.today(),
        foods=foods,
        categories=categories,
        cart_items=cart_items,
        cart_total=cart_total,
        delivery_fee=DELIVERY_FEE,
        cart_count=cart_item_count(customer_id),
        orders=orders,
        items_by_order=items_by_order,
        order_stages=ORDER_STAGES,
        demo_auto_progress=current_app.config["DEMO_AUTO_PROGRESS_ORDERS"],
        add_form=ActionForm(),
        update_form=CartUpdateForm(),
        remove_form=ActionForm(),
        logout_form=LogoutForm(),
    )


@customer.route("/orders")
@customer_required
def orders():
    database = get_db()
    customer_id = g.customer["id"]
    order_rows = database.execute(
        """
        SELECT id, order_number, tracking_status, subtotal, delivery_fee,
               total, delivery_address, delivery_phone, created_at
        FROM orders
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (customer_id,),
    ).fetchall()
    order_items = database.execute(
        """
        SELECT oi.order_id, oi.food_name, oi.unit_price, oi.quantity,
               oi.unit_price * oi.quantity AS line_total
        FROM order_items AS oi
        JOIN orders AS o ON o.id = oi.order_id
        WHERE o.user_id = ?
        ORDER BY oi.id
        """,
        (customer_id,),
    ).fetchall()
    items_by_order = {}
    for item in order_items:
        items_by_order.setdefault(item["order_id"], []).append(item)

    order_list = []
    for row in order_rows:
        order = dict(row)
        order["stage_index"] = (
            ORDER_STAGES.index(order["tracking_status"])
            if order["tracking_status"] in ORDER_STAGES
            else -1
        )
        order["items"] = items_by_order.get(order["id"], [])
        order_list.append(order)
    return render_template(
        "customer/orders.html",
        customer=g.customer,
        orders=order_list,
        order_stages=ORDER_STAGES,
        demo_auto_progress=current_app.config["DEMO_AUTO_PROGRESS_ORDERS"],
    )


@customer.route("/orders/status")
@customer_required
def order_statuses():
    database = get_db()
    if current_app.config["DEMO_AUTO_PROGRESS_ORDERS"]:
        elapsed_times = current_app.config["DEMO_ORDER_PROGRESS_SECONDS"]
        database.execute("BEGIN IMMEDIATE")
        rows_to_progress = database.execute(
            """
            SELECT id, tracking_status,
                   CAST((julianday('now') - julianday(created_at)) * 86400 AS INTEGER)
                       AS age_seconds
            FROM orders
            WHERE user_id = ? AND demo_auto_progress = 1
            """,
            (g.customer["id"],),
        ).fetchall()
        for order in rows_to_progress:
            if order["tracking_status"] in ("Delivered", "Cancelled"):
                continue
            target_index = sum(
                order["age_seconds"] >= elapsed_time
                for elapsed_time in elapsed_times
            )
            current_index = (
                ORDER_STAGES.index(order["tracking_status"])
                if order["tracking_status"] in ORDER_STAGES
                else -1
            )
            if target_index <= current_index:
                continue
            next_status = ORDER_STAGES[target_index]
            legacy_status = {
                "Order Accepted": "Preparing",
                "Preparing": "Preparing",
                "Ready for Pickup": "Preparing",
                "Out for Delivery": "Out for delivery",
                "Delivered": "Delivered",
            }[next_status]
            database.execute(
                """
                UPDATE orders SET tracking_status = ?, status = ?
                WHERE id = ? AND user_id = ? AND demo_auto_progress = 1
                """,
                (next_status, legacy_status, order["id"], g.customer["id"]),
            )
        database.commit()

    rows = database.execute(
        "SELECT id, tracking_status FROM orders WHERE user_id = ? ORDER BY id",
        (g.customer["id"],),
    ).fetchall()
    return {
        "statuses": [
            {"id": row["id"], "status": row["tracking_status"]}
            for row in rows
        ]
    }


@customer.route("/orders/<int:order_id>")
@customer_required
def order_detail(order_id):
    order = order_for_customer(order_id, g.customer["id"])
    if order is None:
        abort(404)
    return render_template(
        "customer/order_detail.html",
        customer=g.customer,
        order=order,
        order_stages=ORDER_STAGES,
        demo_auto_progress=current_app.config["DEMO_AUTO_PROGRESS_ORDERS"],
    )


@customer.route("/cart")
@customer_required
def cart():
    return render_cart_page()


@customer.route("/cart/add/<int:food_id>", methods=["POST"])
@customer_required
def add_to_cart(food_id):
    return_to = request.args.get("return_to")
    if return_to == "menu":
        destination = url_for("menu", _anchor="foodGrid")
    elif return_to == "home":
        destination = url_for("home", _anchor="popular")
    else:
        destination = url_for("customer.dashboard", _anchor="food-menu")
    form = ActionForm()
    if not form.validate_on_submit():
        flash("Your session expired. Please try adding that item again.", "error")
        return redirect(destination)

    database = get_db()
    database.execute("BEGIN IMMEDIATE")
    food = database.execute(
        "SELECT id, stock_quantity FROM food_items WHERE id = ? AND active = 1",
        (food_id,),
    ).fetchone()
    if food is None or food["stock_quantity"] == 0:
        database.rollback()
        flash("That menu item is unavailable.", "error")
        return redirect(destination)

    cart_item = database.execute(
        "SELECT id, quantity FROM cart_items WHERE user_id = ? AND food_id = ?",
        (g.customer["id"], food_id),
    ).fetchone()
    if cart_item and cart_item["quantity"] >= food["stock_quantity"]:
        database.rollback()
        flash(f"Only {food['stock_quantity']} of that item are available.", "error")
        return redirect(destination)
    if cart_item:
        database.execute(
            "UPDATE cart_items SET quantity = quantity + 1 WHERE id = ?",
            (cart_item["id"],),
        )
    else:
        database.execute(
            "INSERT INTO cart_items (user_id, food_id, quantity) VALUES (?, ?, 1)",
            (g.customer["id"], food_id),
        )
    database.commit()
    flash("Added to your cart.", "success")
    return redirect(destination)


@customer.route("/cart/update", methods=["POST"])
@customer_required
def update_cart():
    form = CartUpdateForm()
    if not form.validate_on_submit():
        flash("Choose a quantity between 1 and 99.", "error")
        return redirect(url_for("customer.dashboard", _anchor="cart"))

    database = get_db()
    cart_item = database.execute(
        """
        SELECT ci.id, fi.stock_quantity
        FROM cart_items AS ci
        JOIN food_items AS fi ON fi.id = ci.food_id AND fi.active = 1
        WHERE ci.id = ? AND ci.user_id = ?
        """,
        (form.item_id.data, g.customer["id"]),
    ).fetchone()
    if cart_item is None:
        flash("That cart item could not be found.", "error")
        return redirect(url_for("customer.dashboard", _anchor="cart"))
    if form.quantity.data > cart_item["stock_quantity"]:
        flash(
            f"Only {cart_item['stock_quantity']} of that item are available.",
            "error",
        )
        return redirect(url_for("customer.dashboard", _anchor="cart"))
    cursor = database.execute(
        "UPDATE cart_items SET quantity = ? WHERE id = ? AND user_id = ?",
        (form.quantity.data, form.item_id.data, g.customer["id"]),
    )
    database.commit()
    if cursor.rowcount == 0:
        flash("That cart item could not be found.", "error")
    else:
        flash("Cart updated.", "success")
    return redirect(url_for("customer.dashboard", _anchor="cart"))


@customer.route("/cart/remove/<int:item_id>", methods=["POST"])
@customer_required
def remove_from_cart(item_id):
    form = ActionForm()
    if not form.validate_on_submit():
        flash("Your session expired. Please refresh and try again.", "error")
        return redirect(url_for("customer.dashboard", _anchor="cart"))

    database = get_db()
    cursor = database.execute(
        "DELETE FROM cart_items WHERE id = ? AND user_id = ?",
        (item_id, g.customer["id"]),
    )
    database.commit()
    if cursor.rowcount == 0:
        flash("That cart item could not be found.", "error")
    else:
        flash("Item removed from your cart.", "success")
    return redirect(url_for("customer.dashboard", _anchor="cart"))


@customer.route("/checkout", methods=["POST"])
@customer_required
def checkout():
    form = CheckoutForm()
    if not form.validate_on_submit():
        if not form.errors:
            form.delivery_address.errors.append(
                "Your session expired. Please refresh your cart and try again."
            )
        return render_cart_page(form, status=400)

    database = get_db()
    customer_id = g.customer["id"]
    database.execute("BEGIN IMMEDIATE")
    items = database.execute(
        """
        SELECT ci.food_id, ci.quantity, fi.name, fi.price, fi.stock_quantity
        FROM cart_items AS ci
        JOIN food_items AS fi ON fi.id = ci.food_id
        WHERE ci.user_id = ? AND fi.active = 1
        ORDER BY ci.id
        """,
        (customer_id,),
    ).fetchall()
    if not items:
        database.rollback()
        flash("Your cart is empty. Add a dish before placing an order.", "error")
        return redirect(url_for("customer.cart"))

    unavailable_item = next(
        (item for item in items if item["quantity"] > item["stock_quantity"]),
        None,
    )
    if unavailable_item is not None:
        database.rollback()
        flash(
            f"Only {unavailable_item['stock_quantity']} "
            f"{unavailable_item['name']} are available. Update your cart and try again.",
            "error",
        )
        return redirect(url_for("customer.cart"))

    subtotal = sum(item["price"] * item["quantity"] for item in items)
    total = subtotal + DELIVERY_FEE
    order_number = secrets.token_hex(8).upper()
    cursor = database.execute(
        """
        INSERT INTO orders
            (order_number, user_id, subtotal, delivery_fee, total,
             delivery_address, delivery_phone, tracking_status, demo_auto_progress)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Order Accepted', ?)
        """,
        (
            order_number,
            customer_id,
            subtotal,
            DELIVERY_FEE,
            total,
            form.delivery_address.data,
            form.delivery_phone.data,
            int(current_app.config["DEMO_AUTO_PROGRESS_ORDERS"]),
        ),
    )
    order_id = cursor.lastrowid
    database.executemany(
        """
        INSERT INTO order_items (order_id, food_id, food_name, unit_price, quantity)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (order_id, item["food_id"], item["name"], item["price"], item["quantity"])
            for item in items
        ],
    )
    for item in items:
        inventory_update = database.execute(
            """
            UPDATE food_items
            SET stock_quantity = stock_quantity - ?
            WHERE id = ? AND active = 1 AND stock_quantity >= ?
            """,
            (item["quantity"], item["food_id"], item["quantity"]),
        )
        if inventory_update.rowcount != 1:
            database.rollback()
            flash(
                f"Stock changed for {item['name']}. Please review your cart and try again.",
                "error",
            )
            return redirect(url_for("customer.cart"))
    database.execute("DELETE FROM cart_items WHERE user_id = ?", (customer_id,))
    database.commit()
    flash(
        f"Order #{order_number} (ID {order_id}) placed successfully!",
        "success",
    )
    return redirect(url_for("customer.dashboard", _anchor="track-orders"))
