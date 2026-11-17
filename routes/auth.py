import sqlite3

from flask import Blueprint, flash, redirect, render_template, session, url_for
from flask_wtf import FlaskForm
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp

from database.db import get_db


auth = Blueprint("auth", __name__)

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE_PATTERN = r"^\+?[0-9][0-9 ()-]*$"


def strip_text(value):
    return value.strip() if isinstance(value, str) else value


class RegistrationForm(FlaskForm):
    name = StringField(
        "Full name",
        filters=[strip_text],
        validators=[DataRequired(), Length(min=2, max=80)],
    )
    email = StringField(
        "Email address",
        filters=[strip_text],
        validators=[
            DataRequired(),
            Length(max=254),
            Regexp(EMAIL_PATTERN, message="Enter a valid email address."),
        ],
    )
    phone = StringField(
        "Phone number",
        filters=[strip_text],
        validators=[
            DataRequired(),
            Length(max=20),
            Regexp(PHONE_PATTERN, message="Enter a valid phone number."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(),
            Length(min=8, max=128, message="Use a password between 8 and 128 characters."),
        ],
    )
    submit = SubmitField("Create account")


class LoginForm(FlaskForm):
    email = StringField(
        "Email address",
        filters=[strip_text],
        validators=[
            DataRequired(),
            Length(max=254),
            Regexp(EMAIL_PATTERN, message="Enter a valid email address."),
        ],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(max=128)],
    )
    submit = SubmitField("Login")


class LogoutForm(FlaskForm):
    submit = SubmitField("Logout")


@auth.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("customer.dashboard"))

    form = RegistrationForm()
    if form.validate_on_submit():
        if not 7 <= sum(character.isdigit() for character in form.phone.data) <= 15:
            form.phone.errors.append("Phone number must contain 7 to 15 digits.")
            return render_template("auth/register.html", form=form), 400

        database = get_db()
        try:
            database.execute(
                """
                INSERT INTO users (name, email, phone, password_hash, role)
                VALUES (?, ?, ?, ?, 'customer')
                """,
                (
                    form.name.data,
                    form.email.data.lower(),
                    form.phone.data,
                    generate_password_hash(form.password.data),
                ),
            )
            database.commit()
        except sqlite3.IntegrityError:
            database.rollback()
            form.email.errors.append("An account with this email already exists.")
            return render_template("auth/register.html", form=form), 409

        flash("Your account is ready. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        user = get_db().execute(
            "SELECT role FROM users WHERE id = ?", (session["user_id"],)
        ).fetchone()
        if user is not None:
            if user["role"] == "admin":
                return redirect(url_for("admin.dashboard"))
            if user["role"] == "delivery":
                return redirect(url_for("delivery.dashboard"))
            return redirect(url_for("customer.dashboard"))
        session.clear()

    form = LoginForm()
    if form.validate_on_submit():
        user = get_db().execute(
            "SELECT id, password_hash, role FROM users WHERE email = ? COLLATE NOCASE",
            (form.email.data.lower(),),
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], form.password.data):
            flash("Email or password is incorrect.", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            if user["role"] == "admin":
                return redirect(url_for("admin.dashboard"))
            if user["role"] == "delivery":
                return redirect(url_for("delivery.dashboard"))
            return redirect(url_for("customer.dashboard"))

    return render_template("auth/login.html", form=form)


@auth.route("/logout", methods=["POST"])
def logout():
    form = LogoutForm()
    if not form.validate_on_submit():
        flash("Your session expired. Please try that again.", "error")
        return redirect(url_for("auth.login"))

    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))
