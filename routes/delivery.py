from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, session, url_for
from flask_wtf import FlaskForm
from werkzeug.security import check_password_hash
from wtforms import SelectField, SubmitField
from wtforms.fields.choices import SelectChoice
from wtforms.validators import DataRequired

from database.db import get_db
from routes.auth import LoginForm, LogoutForm


delivery = Blueprint("delivery", __name__, url_prefix="/delivery")
LEGACY_STATUS = {
    "Out for Delivery": "Out for delivery",
    "Delivered": "Delivered",
}


class DeliveryStatusForm(FlaskForm):
    status = SelectField("Update delivery", validators=[DataRequired()])
    submit = SubmitField("Update status")


def delivery_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id is None:
            return redirect(url_for("delivery.login"))

        g.delivery_person = get_db().execute(
            "SELECT id, name, email, role FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if g.delivery_person is None:
            session.clear()
            return redirect(url_for("delivery.login"))
        if g.delivery_person["role"] != "delivery":
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view


@delivery.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        user = get_db().execute(
            "SELECT role FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()
        if user and user["role"] == "delivery":
            return redirect(url_for("delivery.dashboard"))
        if user and user["role"] == "admin":
            return redirect(url_for("admin.dashboard"))
        if user:
            return redirect(url_for("customer.dashboard"))
        session.clear()

    form = LoginForm()
    if form.validate_on_submit():
        user = get_db().execute(
            "SELECT id, password_hash, role FROM users WHERE email = ? COLLATE NOCASE",
            (form.email.data.lower(),),
        ).fetchone()
        if user is None or user["role"] != "delivery" or not check_password_hash(
            user["password_hash"], form.password.data
        ):
            flash("Email or password is incorrect.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("delivery.dashboard"))
    return render_template("delivery/login.html", form=form)


@delivery.route("/dashboard")
@delivery_required
def dashboard():
    database = get_db()
    assigned_orders = database.execute(
        """
        SELECT o.id, o.order_number, o.tracking_status, o.total, o.created_at,
               o.delivery_address, o.delivery_phone,
               u.name AS customer_name, u.phone AS customer_phone
        FROM orders AS o
        JOIN users AS u ON u.id = o.user_id AND u.role = 'customer'
        WHERE o.assigned_to = ?
          AND o.tracking_status NOT IN ('Delivered', 'Cancelled')
        ORDER BY o.created_at ASC, o.id ASC
        """,
        (g.delivery_person["id"],),
    ).fetchall()
    completed_orders = database.execute(
        """
        SELECT o.id, o.order_number, o.tracking_status, o.total, o.created_at,
               o.delivery_address, o.delivery_phone,
               u.name AS customer_name, u.phone AS customer_phone
        FROM orders AS o
        JOIN users AS u ON u.id = o.user_id AND u.role = 'customer'
        WHERE o.assigned_to = ? AND o.tracking_status = 'Delivered'
        ORDER BY o.created_at DESC, o.id DESC
        """,
        (g.delivery_person["id"],),
    ).fetchall()
    order_ids = [order["id"] for order in assigned_orders + completed_orders]
    items_by_order = {}
    if order_ids:
        placeholders = ",".join("?" for _ in order_ids)
        items = database.execute(
            f"""
            SELECT order_id, food_name, unit_price, quantity,
                   unit_price * quantity AS line_total
            FROM order_items
            WHERE order_id IN ({placeholders})
            ORDER BY id
            """,
            order_ids,
        ).fetchall()
        for item in items:
            items_by_order.setdefault(item["order_id"], []).append(item)

    status_forms = {}
    for order in assigned_orders:
        if order["tracking_status"] == "Ready for Pickup":
            choices = [SelectChoice(value="Out for Delivery", label="Out for Delivery")]
        elif order["tracking_status"] == "Out for Delivery":
            choices = [SelectChoice(value="Delivered", label="Delivered")]
        else:
            choices = []
        form = DeliveryStatusForm(status=choices[0].value if choices else "")
        form.status.choices = choices
        status_forms[order["id"]] = form

    return render_template(
        "delivery/dashboard.html",
        delivery_person=g.delivery_person,
        assigned_orders=assigned_orders,
        completed_orders=completed_orders,
        items_by_order=items_by_order,
        status_forms=status_forms,
        logout_form=LogoutForm(),
    )


@delivery.route("/orders/<int:order_id>/status", methods=["POST"])
@delivery_required
def update_order_status(order_id):
    database = get_db()
    form = DeliveryStatusForm()
    current_order = database.execute(
        """
        SELECT tracking_status FROM orders
        WHERE id = ? AND assigned_to = ?
        """,
        (order_id, g.delivery_person["id"]),
    ).fetchone()
    if current_order is None:
        abort(404)
    next_status = {
        "Ready for Pickup": "Out for Delivery",
        "Out for Delivery": "Delivered",
    }.get(current_order["tracking_status"])
    form.status.choices = (
        [SelectChoice(value=next_status, label=next_status)]
        if next_status
        else []
    )
    if not form.validate_on_submit():
        flash("Choose a valid delivery status and try again.", "error")
        return redirect(url_for("delivery.dashboard"))

    database.execute("BEGIN IMMEDIATE")
    order = database.execute(
        """
        SELECT tracking_status FROM orders
        WHERE id = ? AND assigned_to = ?
        """,
        (order_id, g.delivery_person["id"]),
    ).fetchone()
    if order is None:
        database.rollback()
        abort(404)

    if next_status is None or form.status.data != next_status:
        database.rollback()
        flash("That delivery status transition is not allowed.", "error")
        return redirect(url_for("delivery.dashboard"))

    cursor = database.execute(
        """
        UPDATE orders
        SET tracking_status = ?, status = ?, demo_auto_progress = 0
        WHERE id = ? AND assigned_to = ? AND tracking_status = ?
        """,
        (
            next_status,
            LEGACY_STATUS[next_status],
            order_id,
            g.delivery_person["id"],
            order["tracking_status"],
        ),
    )
    if cursor.rowcount != 1:
        database.rollback()
        flash("Order status changed before your update. Refresh and try again.", "error")
        return redirect(url_for("delivery.dashboard"))
    database.commit()
    flash(f"Order #{order_id} updated to {next_status}.", "success")
    return redirect(url_for("delivery.dashboard"))


@delivery.route("/logout", methods=["POST"])
@delivery_required
def logout():
    form = LogoutForm()
    if not form.validate_on_submit():
        flash("Your session expired. Please try again.", "error")
        return redirect(url_for("delivery.dashboard"))
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("delivery.login"))
