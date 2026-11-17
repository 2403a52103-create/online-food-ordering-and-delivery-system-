import os
import re
import secrets
import sqlite3

import click
from flask import Flask, redirect, render_template, url_for
from werkzeug.security import generate_password_hash

from database.db import get_db, init_app as init_database
from routes.auth import auth
from routes.admin import admin
from routes.customer import ActionForm, customer
from routes.delivery import delivery


FOODS = [
    {
        "id": 1,
        "name": "Margherita Pizza",
        "category": "pizza",
        "description": "Stone-baked, bubbling with mozzarella and basil.",
        "price": 299,
        "image": "https://images.unsplash.com/photo-1574071318508-1cdbab80d002",
        "rating": "4.9",
        "badge": "Bestseller",
    },
    {
        "id": 2,
        "name": "Classic Smash Burger",
        "category": "burger",
        "description": "Juicy grilled patty, cheddar, and house sauce.",
        "price": 249,
        "image": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd",
        "rating": "4.8",
        "badge": "Popular",
    },
    {
        "id": 3,
        "name": "Chicken Dum Biryani",
        "category": "biryani",
        "description": "Fragrant basmati rice, slow-cooked with spices.",
        "price": 329,
        "image": "https://images.unsplash.com/photo-1589302168068-964664d93dc0",
        "rating": "4.9",
        "badge": "Chef's pick",
    },
    {
        "id": 4,
        "name": "Crispy Chilli Paneer",
        "category": "chinese",
        "description": "Crispy paneer tossed in a tangy Indo-Chinese sauce.",
        "price": 279,
        "image": "https://images.unsplash.com/photo-1563245372-f21724e3856d",
        "rating": "4.7",
        "badge": "Veg favorite",
    },
    {
        "id": 5,
        "name": "Chocolate Lava Cake",
        "category": "desserts",
        "description": "Warm chocolate cake with a gooey molten center.",
        "price": 169,
        "image": "https://images.unsplash.com/photo-1578985545062-69928b1d9587",
        "rating": "4.8",
        "badge": "Sweet treat",
    },
    {
        "id": 6,
        "name": "Garden Veggie Pizza",
        "category": "pizza",
        "description": "A colorful mix of garden vegetables and cheese.",
        "price": 319,
        "image": "https://images.unsplash.com/photo-1513104890138-7c749659a591",
        "rating": "4.6",
        "badge": "Fresh pick",
    },
    {
        "id": 7,
        "name": "Masala Dosa",
        "category": "south-indian",
        "description": "Golden rice crepe filled with spiced potato, served with chutney.",
        "price": 199,
        "image": "https://images.unsplash.com/photo-1668236543090-82eba5ee5976",
        "rating": "4.8",
        "badge": "South Indian favorite",
    },
]

ADDITIONAL_FOODS = {
    "pizza": (
        ("Farmhouse Pizza", 349),
        ("Pepperoni Pizza", 399),
        ("Four Cheese Pizza", 379),
        ("BBQ Chicken Pizza", 389),
        ("Peri Peri Chicken Pizza", 379),
        ("Paneer Tikka Pizza", 359),
        ("Mushroom Truffle Pizza", 399),
        ("Mexican Fiesta Pizza", 349),
        ("Double Cheese Margherita Pizza", 339),
        ("Roasted Veggie Pizza", 329),
        ("Pesto Corn Pizza", 319),
        ("Spinach Feta Pizza", 359),
        ("Tandoori Chicken Pizza", 389),
        ("Smoky Chicken Sausage Pizza", 369),
        ("Classic Neapolitan Pizza", 329),
        ("Garlic Mushroom Pizza", 339),
        ("Sweet Corn Capsicum Pizza", 299),
        ("Fiery Chicken Pizza", 389),
    ),
    "burger": (
        ("Crispy Veg Burger", 179),
        ("Double Smash Burger", 329),
        ("Crispy Chicken Burger", 229),
        ("Spicy Chicken Burger", 249),
        ("Paneer Crunch Burger", 219),
        ("BBQ Chicken Burger", 269),
        ("Mushroom Swiss Burger", 259),
        ("Aloo Tikki Burger", 149),
        ("Peri Peri Veg Burger", 199),
        ("Classic Cheeseburger", 239),
        ("Chicken Club Burger", 279),
        ("Tandoori Paneer Burger", 229),
        ("Smoky BBQ Burger", 259),
        ("Crispy Fish Burger", 289),
        ("Jalapeno Cheese Burger", 249),
        ("Loaded Veggie Burger", 209),
        ("Double Chicken Stack", 319),
        ("Avocado Garden Burger", 279),
        ("Chilli Garlic Chicken Burger", 259),
    ),
    "biryani": (
        ("Hyderabadi Chicken Dum Biryani", 359),
        ("Lucknowi Mutton Biryani", 429),
        ("Vegetable Dum Biryani", 279),
        ("Egg Biryani", 259),
        ("Paneer Tikka Biryani", 299),
        ("Prawn Biryani", 449),
        ("Kolkata Chicken Biryani", 369),
        ("Mushroom Biryani", 289),
        ("Andhra Spicy Chicken Biryani", 379),
        ("Mutton Keema Biryani", 419),
        ("Jackfruit Dum Biryani", 309),
        ("Chicken 65 Biryani", 389),
        ("Malabar Chicken Biryani", 369),
        ("Soya Chaap Biryani", 289),
        ("Cashew Vegetable Biryani", 319),
        ("Fish Biryani", 399),
        ("Boneless Chicken Biryani", 389),
        ("Paneer Butter Masala Biryani", 319),
        ("Gongura Chicken Biryani", 389),
    ),
    "chinese": (
        ("Vegetable Hakka Noodles", 229),
        ("Chicken Hakka Noodles", 279),
        ("Schezwan Fried Rice", 249),
        ("Vegetable Manchurian", 239),
        ("Chilli Chicken", 319),
        ("Vegetable Spring Rolls", 189),
        ("Chicken Spring Rolls", 239),
        ("Honey Chilli Potato", 219),
        ("Paneer Manchurian", 269),
        ("Garlic Noodles", 239),
        ("Triple Schezwan Rice", 299),
        ("Chilli Garlic Prawns", 369),
        ("Crispy Corn Pepper Salt", 219),
        ("Chicken Lollipop", 329),
        ("Kung Pao Chicken", 329),
        ("Stir-Fried Mixed Vegetables", 249),
        ("Paneer Chilli Dry", 279),
        ("Schezwan Chicken Noodles", 299),
        ("Burnt Garlic Fried Rice", 249),
    ),
    "desserts": (
        ("Classic New York Cheesecake", 229),
        ("Fudgy Chocolate Brownie", 149),
        ("Red Velvet Pastry", 179),
        ("Tiramisu Cup", 219),
        ("Gulab Jamun (4 pcs)", 129),
        ("Rasmalai (2 pcs)", 149),
        ("Mango Mousse", 169),
        ("Belgian Chocolate Waffle", 199),
        ("Caramel Custard", 139),
        ("Blueberry Cheesecake", 239),
        ("Choco Chip Cookie Sundae", 189),
        ("Pistachio Kulfi", 119),
        ("Strawberry Panna Cotta", 179),
        ("Brownie Fudge Sundae", 219),
        ("Coconut Ladoo (4 pcs)", 109),
        ("Apple Crumble", 189),
        ("Classic Vanilla Cupcake", 129),
        ("Molten Chocolate Brownie", 169),
        ("Kesar Phirni", 149),
    ),
    "south-indian": (
        ("Mysore Masala Dosa", 229),
        ("Rava Masala Dosa", 219),
        ("Plain Dosa", 149),
        ("Ghee Roast Dosa", 189),
        ("Onion Uttapam", 169),
        ("Mixed Vegetable Uttapam", 189),
        ("Idli Sambar (4 pcs)", 129),
        ("Medu Vada (4 pcs)", 139),
        ("Podi Idli", 159),
        ("Pesarattu", 179),
        ("Appam with Vegetable Stew", 199),
        ("Ven Pongal", 159),
        ("Lemon Rice", 149),
        ("Curd Rice", 139),
        ("Tomato Onion Uttapam", 179),
        ("Cheese Masala Dosa", 229),
        ("Ragi Dosa", 179),
        ("Mini Idli Sambar", 139),
        ("Coconut Rice", 169),
    ),
}

FOOD_DESCRIPTIONS = {
    "pizza": "Freshly baked with generous toppings and a golden, cheesy finish.",
    "burger": "A satisfying stack with fresh toppings and our signature sauce.",
    "biryani": "Fragrant basmati rice layered with aromatic spices and slow-cooked flavor.",
    "chinese": "An Indo-Chinese favorite, freshly prepared with a savory, balanced sauce.",
    "desserts": "A delightful sweet treat, freshly prepared for the perfect finish.",
    "south-indian": "A South Indian classic, served fresh with traditional flavors.",
}

ADDITIONAL_FOOD_IMAGES = {
    "pizza": (
        "photo-1769458313988-2cd932ab2777",
        "photo-1593504049359-74330189a345",
        "photo-1776810250102-7459c4e0edc9",
        "photo-1613564834361-9436948817d1",
        "photo-1534308983496-4fabb1a015ee",
        "photo-1593560708920-61dd98c46a4e",
        "photo-1628840042765-356cda07504e",
        "photo-1565299624946-b28f40a0ae38",
        "photo-1769521140317-5c6dcd1266e7",
        "photo-1604382354936-07c5d9983bd3",
        "photo-1786175525568-913cedb21fff",
        "photo-1772494047822-d0375853f7fd",
        "photo-1579751626657-72bc17010498",
        "photo-1611915365928-565c527a0590",
        "photo-1544982503-9f984c14501a",
        "photo-1541745537411-b8046dc6d66c",
        "photo-1542834369-f10ebf06d3e0",
        "photo-1662938979428-ab8f34fff816",
    ),
    "burger": (
        "photo-1757834787931-ddd70f3379a5",
        "photo-1586190848861-99aa4a171e90",
        "photo-1572802419224-296b0aeee0d9",
        "photo-1550547660-d9450f859349",
        "photo-1767065703549-000399981385",
        "photo-1713330801172-03f8d1c0dde7",
        "photo-1767065703793-7012f5fced19",
        "photo-1610440042657-612c34d95e9f",
        "photo-1763689389824-dd2cea2e5772",
        "photo-1776260486895-a35357e2505b",
        "photo-1607013251379-e6eecfffe234",
        "photo-1571091718767-18b5b1457add",
        "photo-1603064752734-4c48eff53d05",
        "photo-1549611016-3a70d82b5040",
        "photo-1783099500460-15db4038e4a0",
        "photo-1610970878459-a0e464d7592b",
        "photo-1766589221281-661e1398e721",
        "photo-1499028344343-cd173ffc68a9",
        "photo-1547584370-2cc98b8b8dc8",
    ),
    "biryani": (
        "photo-1631515243349-e0cb75fb8d3a",
        "photo-1782541370275-6761522e39d1",
        "photo-1705174299330-939dd03cc864",
        "photo-1563379091339-03b21ab4a4f8",
        "photo-1787555220215-44df44188c07",
        "photo-1633945274405-b6c8069047b0",
        "photo-1719239885399-f87d992e0f18",
        "photo-1771796992969-05bb88a0516a",
        "photo-1697155406055-2db32d47ca07",
        "photo-1779231127187-fe90c5d669c9",
        "photo-1774669063671-1f34847a661d",
        "photo-1716550781939-beb7d7247aae",
        "photo-1633945274309-2c16c9682a8c",
        "photo-1736680056325-ba2ade6250a3",
        "photo-1630851840633-f96999247032",
        "photo-1691171047462-66025ecd5efc",
        "photo-1599043513900-ed6fe01d3833",
        "photo-1642821373181-696a54913e93",
        "photo-1710091691777-3115088962c4",
    ),
    "chinese": (
        "photo-1585032226651-759b368d7246",
        "photo-1569718212165-3a8278d5f624",
        "photo-1780375578952-854c9ef62c36",
        "photo-1787691684812-365ed2c7daf4",
        "photo-1707013533606-62919aa3aa29",
        "photo-1635685296916-95acaf58471f",
        "photo-1530569112985-108dc2578ec2",
        "photo-1555126634-323283e090fa",
        "photo-1780375578961-ef93d67592a8",
        "photo-1771339140258-17f090ef6007",
        "photo-1496116218417-1a781b1c416c",
        "photo-1623689048105-a17b1e1936b8",
        "photo-1780375578105-e4c938ce2c38",
        "photo-1526318896980-cf78c088247c",
        "photo-1517499414974-3b42addf2d86",
        "photo-1622643944007-450264a5f9a9",
        "photo-1623689046286-01d812cc8bad",
        "photo-1624067046879-cca70a7cf79c",
        "photo-1710508787399-e3dc878838a8",
    ),
    "desserts": (
        "photo-1551024601-bec78aea704b",
        "photo-1783171375542-444b30048e52",
        "photo-1563729784474-d77dbb933a9e",
        "photo-1588195538326-c5b1e9f80a1b",
        "photo-1759146233677-292a2f1a2236",
        "photo-1558326567-98ae2405596b",
        "photo-1563805042-7684c019e1cb",
        "photo-1783171375537-af3cca3ba347",
        "photo-1587314168485-3236d6710814",
        "photo-1761637604927-e3656dc81383",
        "photo-1783624276842-40d0a7c4e1b9",
        "photo-1606890737304-57a1ca8a5b62",
        "photo-1551024506-0bccd828d307",
        "photo-1495147466023-ac5c588e2e94",
        "photo-1606313564200-e75d5e30476c",
        "photo-1548741448-9f4e87b7f7ab",
        "photo-1673912402587-57ac40f1b4a5",
        "photo-1584820673525-e77c7b799c01",
        "photo-1681723609766-cbca4ccc327e",
    ),
    "south-indian": (
        "photo-1625398407796-82650a8c135f",
        "photo-1786227905994-235e1799292e",
        "photo-1694849789325-914b71ab4075",
        "photo-1771541897176-44a3e01dc484",
        "photo-1786222084052-fb6f27bfb135",
        "photo-1633383718081-22ac93e3db65",
        "photo-1683533678033-f5d60f0a3437",
        "photo-1787024231387-edccb8c44700",
        "photo-1589301760014-d929f3979dbc",
        "photo-1767114915989-c6ab3c8fc42e",
        "photo-1465014925804-7b9ede58d0d7",
        "photo-1683533678059-63c6a0e9e3ef",
        "photo-1680359871322-aabe6b33eff5",
        "photo-1657196118354-f25f29fe636d",
        "photo-1708146464361-5c5ce4f9abb6",
        "photo-1665660710687-b44c50751054",
        "photo-1743517894265-c86ab035adef",
        "photo-1665206221363-568ea2f7b195",
        "photo-1668236499396-a62d2d1cb0cf",
    ),
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.path.join(app.instance_path, "foodexpress.sqlite3"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        SESSION_PERMANENT=False,
        DEMO_AUTO_PROGRESS_ORDERS=os.environ.get(
            "DEMO_AUTO_PROGRESS_ORDERS", "1"
        ) == "1",
        DEMO_ORDER_PROGRESS_SECONDS=(60, 120, 180, 300),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    database_directory = os.path.dirname(app.config["DATABASE"])
    if database_directory:
        os.makedirs(database_directory, exist_ok=True)
    init_database(app)
    app.register_blueprint(auth)
    app.register_blueprint(customer)
    app.register_blueprint(admin)
    app.register_blueprint(delivery)
    with app.app_context():
        database = get_db()
        database.executemany(
            """
            INSERT OR IGNORE INTO food_items
                (id, name, category, description, price, image, rating, badge)
            VALUES
                (:id, :name, :category, :description, :price, :image, :rating, :badge)
            """,
            FOODS,
        )
        additional_foods = [
            {
                "name": name,
                "category": category,
                "description": FOOD_DESCRIPTIONS[category],
                "price": price,
                "image": f"https://images.unsplash.com/{ADDITIONAL_FOOD_IMAGES[category][index]}",
                "rating": "4.6",
                "badge": "Popular",
            }
            for category, foods in ADDITIONAL_FOODS.items()
            for index, (name, price) in enumerate(foods)
        ]
        database.executemany(
            """
            INSERT INTO food_items
                (name, category, description, price, image, rating, badge)
            SELECT :name, :category, :description, :price, :image, :rating, :badge
            WHERE NOT EXISTS (
                SELECT 1 FROM food_items WHERE name = :name AND category = :category
            )
            """,
            additional_foods,
        )
        database.executemany(
            """
            UPDATE food_items
            SET image = :image
            WHERE name = :name AND category = :category
            """,
            additional_foods,
        )
        database.commit()

    @app.cli.command("create-staff")
    @click.option("--role", type=click.Choice(["admin", "delivery"]), prompt=True)
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--phone", prompt=True)
    def create_staff(role, name, email, phone):
        """Create an admin or delivery account without public registration."""
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        if len(password) < 8 or len(password) > 128:
            raise click.ClickException("Password must be between 8 and 128 characters.")
        if not name.strip() or len(name.strip()) > 80:
            raise click.ClickException("Name must contain 1 to 80 characters.")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()) or len(email.strip()) > 254:
            raise click.ClickException("Enter a valid email address.")
        if (
            len(phone.strip()) > 20
            or not re.fullmatch(r"\+?[0-9][0-9 ()-]*", phone.strip())
            or not 7 <= sum(character.isdigit() for character in phone) <= 15
        ):
            raise click.ClickException("Phone number must contain 7 to 15 digits.")
        database = get_db()
        try:
            database.execute(
                """
                INSERT INTO users (name, email, phone, password_hash, role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name.strip(),
                    email.strip().lower(),
                    phone.strip(),
                    generate_password_hash(password),
                    role,
                ),
            )
            database.commit()
        except sqlite3.IntegrityError as error:
            database.rollback()
            if "UNIQUE constraint failed" in str(error):
                raise click.ClickException("An account with that email already exists.") from error
            raise
        click.echo(f"Created {role} account for {email.strip().lower()}.")

    @app.cli.command("promote-customer-to-admin")
    @click.option("--email", prompt=True)
    def promote_customer_to_admin(email):
        """Promote an existing customer account to an administrator."""
        normalized_email = email.strip().lower()
        if (
            len(normalized_email) > 254
            or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized_email)
        ):
            raise click.ClickException("Enter a valid email address.")

        database = get_db()
        user = database.execute(
            "SELECT id, role FROM users WHERE email = ? COLLATE NOCASE",
            (normalized_email,),
        ).fetchone()
        if user is None:
            raise click.ClickException("No account exists with that email address.")
        if user["role"] != "customer":
            raise click.ClickException("Only customer accounts can be promoted.")

        click.confirm(
            f"Promote {normalized_email} to administrator?",
            abort=True,
        )
        cursor = database.execute(
            "UPDATE users SET role = 'admin' WHERE id = ? AND role = 'customer'",
            (user["id"],),
        )
        if cursor.rowcount != 1:
            database.rollback()
            raise click.ClickException("The account role changed before promotion.")
        database.commit()
        click.echo(
            f"Promoted {normalized_email} to admin. Sign in with the existing password."
        )

    @app.route("/")
    def home():
        foods = get_db().execute(
            "SELECT * FROM food_items WHERE active = 1 ORDER BY id"
        ).fetchall()
        return render_template("index.html", foods=foods, add_form=ActionForm())

    @app.route("/menu")
    def menu():
        database = get_db()
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
        return render_template(
            "customer/menu.html",
            foods=foods,
            categories=categories,
            add_form=ActionForm(),
        )

    @app.route("/about")
    def about():
        return redirect(url_for("home") + "#about")

    @app.route("/contact")
    def contact():
        return redirect(url_for("home") + "#contact")

    return app


app = create_app()


if __name__ == "__main__":
    app.run()