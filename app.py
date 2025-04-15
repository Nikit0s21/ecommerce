import uuid

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, make_response
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func
from functools import wraps
from extensions import db, login_manager
from models import User, Product, Order, OrderItem, Visit
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'


@app.route('/')
def index():
    # Получаем статистику посещений за сегодня
    today = datetime.utcnow().date()
    visit_stats = {
        'today': Visit.query.filter(db.func.date(Visit.created_at) == today).count(),
        'total': Visit.query.count()
    }

    featured_products = Product.query.order_by(Product.created_at.desc()).limit(4).all()
    return render_template('index.html',
                           featured_products=featured_products,
                           visit_stats=visit_stats)


@app.route('/catalog')
def catalog():
    # Получаем список категорий (используем getlist вместо get)
    categories_selected = request.args.getlist('category[]')
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')
    sort = request.args.get('sort')
    search = request.args.get('search')

    query = Product.query

    # Фильтр по категориям (теперь обрабатываем список)
    if categories_selected:
        query = query.filter(Product.category.in_(categories_selected))

    # Остальные фильтры остаются без изменений
    if min_price:
        try:
            query = query.filter(Product.price >= float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            query = query.filter(Product.price <= float(max_price))
        except ValueError:
            pass
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))

    # Сортировка (без изменений)
    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort == 'name_asc':
        query = query.order_by(Product.name.asc())
    elif sort == 'name_desc':
        query = query.order_by(Product.name.desc())
    elif sort == 'newest':
        query = query.order_by(Product.created_at.desc())

    products = query.all()
    categories = db.session.query(Product.category.distinct()).all()

    return render_template('catalog.html',
                         products=products,
                         categories=categories,
                         selected_categories=categories_selected)

def get_visit_stats():
    today = datetime.utcnow().date()
    return {
        'today': Visit.query.filter(db.func.date(Visit.created_at) == today).count(),
        'total': Visit.query.count()
    }

def with_visit_stats(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        response = view_func(*args, **kwargs)
        if isinstance(response, str):
            return response
        visit_stats = get_visit_stats()
        if isinstance(response, dict):
            response['visit_stats'] = visit_stats
            return render_template(response.get('template'), **response)
        return response
    return wrapped_view

@app.context_processor
def inject_visit_stats():
    return {'visit_stats': get_visit_stats()}

@app.route('/sales_stats')
@login_required
def sales_stats():
    if not current_user.is_admin:  # Нужно добавить поле is_admin в модель User
        abort(403)

    # Статистика по категориям
    category_stats = db.session.query(
        Product.category,
        func.sum(OrderItem.quantity).label('total_quantity'),
        func.sum(OrderItem.price * OrderItem.quantity).label('total_revenue')
    ).join(OrderItem.product).group_by(Product.category).all()

    # Статистика по времени
    time_stats = db.session.query(
        func.date_trunc('day', Order.created_at).label('day'),
        func.count(Order.id).label('order_count'),
        func.sum(Order.total).label('daily_revenue')
    ).group_by('day').order_by('day').all()

    return render_template('sales_stats.html',
                           category_stats=category_stats,
                           time_stats=time_stats)


from datetime import datetime


@app.before_request
def track_visits():
    if 'visits' not in session:
        session['visits'] = 1
    else:
        session['visits'] += 1

    # Логирование в файл
    with open('visits.log', 'a') as f:
        f.write(f"{datetime.now()},{request.path},{session.get('user_id')}\n")

# Страница товара
@app.route('/product/<int:id>')
def product(id):
    product = Product.query.get_or_404(id)
    return render_template('product.html', product=product)


@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    if request.method == 'POST':
        current_user.first_name = request.form.get('first_name')
        current_user.last_name = request.form.get('last_name')
        current_user.email = request.form.get('email')
        current_user.phone = request.form.get('phone')

        db.session.commit()
        flash('Профиль успешно обновлен', 'success')
        return redirect(url_for('account'))

    return redirect(url_for('account'))

@app.route('/cart')
def cart():
    # Получаем корзину из сессии или создаем пустую
    cart = session.get('cart', {})

    # Подготавливаем данные для отображения
    products = []
    total_price = 0
    total_items = 0

    # Получаем информацию о каждом товаре в корзине
    for product_id, quantity in cart.items():
        product = db.session.get(Product, int(product_id))
        if product:
            item_total = product.price * quantity
            total_price += item_total
            total_items += quantity

            products.append({
                'id': product.id,
                'name': product.name,
                'price': product.price,
                'quantity': quantity,
                'total': item_total,
                'image': product.image_url,
                'stock': product.stock
            })

    return render_template(
        'cart.html',
        cart_items=products,
        total_price=total_price,
        total_items=total_items
    )


@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']
    product = Product.query.get_or_404(product_id)

    # Проверяем доступное количество
    if str(product_id) in cart:
        if cart[str(product_id)] >= product.stock:
            flash('Недостаточно товара в наличии', 'warning')
            return redirect(request.referrer)

    cart[str(product_id)] = cart.get(str(product_id), 0) + 1
    session['cart'] = cart
    flash(f'Товар "{product.name}" добавлен в корзину', 'success')
    return redirect(request.referrer)


@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'cart' not in session:
        return redirect(url_for('cart'))

    cart = session['cart']
    product = Product.query.get_or_404(product_id)

    remove_all = request.args.get('remove_all', 'false').lower() == 'true'
    reduce_by = int(request.args.get('reduce_by', 1))

    if str(product_id) in cart:
        if remove_all or cart[str(product_id)] <= reduce_by:
            del cart[str(product_id)]
            flash(f'Товар "{product.name}" удален из корзины', 'info')
        else:
            cart[str(product_id)] -= reduce_by
            flash(f'Количество товара "{product.name}" уменьшено', 'info')

    session['cart'] = cart
    return redirect(url_for('cart'))

@app.route('/add_address', methods=['POST'])
@login_required
def add_address():
    if request.method == 'POST':
        address = request.form.get('address')
        if address:
            current_user.address = address
            db.session.commit()
            flash('Адрес успешно добавлен', 'success')
        else:
            flash('Пожалуйста, введите адрес', 'warning')
    return redirect(url_for('account', _anchor='addresses'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    if 'cart' not in session or not session['cart']:
        return redirect(url_for('cart'))

    cart = session.get('cart', {})
    products = []
    total = 0

    # Получаем товары из корзины
    for product_id, quantity in cart.items():
        product = db.session.get(Product, int(product_id))
        if product:
            item_total = product.price * quantity
            total += item_total
            products.append({
                'product': product,
                'quantity': quantity,
                'total': item_total
            })

    if request.method == 'POST':
        # Валидация обязательных полей
        required_fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'payment_method']
        if not all(field in request.form for field in required_fields):
            flash('Пожалуйста, заполните все обязательные поля', 'danger')
            return redirect(url_for('checkout'))

        try:
            # Создаем заказ
            new_order = Order(
                user_id=current_user.id,
                total=total,
                status='processing',
                address=request.form['address'],
                payment_method=request.form['payment_method']
            )
            db.session.add(new_order)
            db.session.flush()  # Получаем ID заказа

            # Добавляем товары в заказ
            for item in products:
                order_item = OrderItem(
                    order_id=new_order.id,
                    product_id=item['product'].id,
                    quantity=item['quantity'],
                    price=item['product'].price
                )
                db.session.add(order_item)

            # Обновляем данные пользователя
            current_user.first_name = request.form['first_name']
            current_user.last_name = request.form['last_name']
            current_user.phone = request.form['phone']
            current_user.address = request.form['address']

            db.session.commit()
            session.pop('cart', None)

            flash(f'Заказ успешно оформлен! Номер вашего заказа: #{new_order.id}', 'success')
            return redirect(url_for('account'))

        except Exception as e:
            db.session.rollback()
            flash(f'Произошла ошибка при оформлении заказа: {str(e)}', 'danger')
            return redirect(url_for('checkout'))

    return render_template(
        'checkout.html',
        cart_items=products,
        total=total
    )


# Личный кабинет
@app.route('/account')
@login_required
def account():
    # Получаем заказы пользователя
    orders = Order.query.filter_by(user_id=current_user.id) \
        .options(db.joinedload(Order.items)) \
        .order_by(Order.created_at.desc()).all()

    # Статистика заказов
    order_stats = {
        'total_orders': len(orders),
        'total_spent': sum(order.total for order in orders),
        'avg_order': sum(order.total for order in orders) / len(orders) if orders else 0
    }

    # Статистика посещений
    today = datetime.utcnow().date()
    visit_stats = {
        'today': Visit.query.filter(
            Visit.created_at >= today
        ).count(),
        'total': Visit.query.count()
    }

    return render_template('account.html',
                           orders=orders,
                           order_stats=order_stats,
                           visit_stats=visit_stats)


@app.route('/repeat_order/<int:order_id>', methods=['GET', 'POST'])
@login_required
def repeat_order(order_id):
    # Получаем заказ из базы данных
    order = db.session.get(Order, order_id)

    # Проверяем, что заказ существует и принадлежит текущему пользователю
    if not order or order.user_id != current_user.id:
        flash('Заказ не найден', 'danger')
        return redirect(url_for('account'))

    # Очищаем текущую корзину
    session['cart'] = {}

    # Добавляем товары из заказа в корзину
    for item in order.items:
        session['cart'][str(item.product_id)] = item.quantity
        session.modified = True

    flash('Товары из заказа добавлены в корзину', 'success')
    return redirect(url_for('cart'))


@app.before_request
def track_visit():
    # Пропускаем статические файлы
    if request.endpoint == 'static':
        return

    try:
        visitor_id = request.cookies.get('visitor_id')
        if not visitor_id:
            visitor_id = str(uuid.uuid4())

        today = datetime.utcnow().date()

        # Проверяем, есть ли уже сегодняшний визит от этого пользователя
        existing_visit = Visit.query.filter(
            Visit.visitor_id == visitor_id,
            db.func.date(Visit.created_at) == today
        ).first()

        if not existing_visit:
            visit = Visit(
                visitor_id=visitor_id,
                user_id=current_user.id if current_user.is_authenticated else None,
                ip_address=request.remote_addr,
                page_url=request.url
            )
            db.session.add(visit)
            db.session.commit()

        # Установка cookie
        if not request.cookies.get('visitor_id'):
            response = make_response()
            response.set_cookie('visitor_id', visitor_id, max_age=60 * 60 * 24 * 30)  # 30 дней
            return response

    except Exception as e:
        app.logger.error(f"Error tracking visit: {str(e)}")

@app.route('/order_details/<int:order_id>')
@login_required
def order_details(order_id):
    order = db.session.get(Order, order_id)

    if not order or order.user_id != current_user.id:
        flash('Заказ не найден', 'danger')
        return redirect(url_for('account'))

    return render_template('order_details.html', order=order)

# Регистрация
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Проверка на существующего пользователя
        if User.query.filter_by(username=username).first():
            flash('Это имя пользователя уже занято', 'danger')
            return redirect(url_for('register'))

        if User.query.filter_by(email=email).first():
            flash('Этот email уже используется', 'danger')
            return redirect(url_for('register'))

        # Создание нового пользователя
        new_user = User(
            username=username,
            email=email,
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name')
        )
        new_user.set_password(password)

        db.session.add(new_user)
        db.session.commit()

        flash('Регистрация прошла успешно! Теперь вы можете войти.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


# Вход
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash('Неверное имя пользователя или пароль', 'danger')
            return redirect(url_for('login'))

        login_user(user, remember=remember)
        flash('Вы успешно вошли в систему', 'success')

        next_page = request.args.get('next')
        return redirect(next_page) if next_page else redirect(url_for('index'))

    return render_template('login.html')


# Выход
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # Добавляем тестовые товары, если их нет
        if not Product.query.first():
            test_products = [
                Product(
                    name="Смартфон Samsung Galaxy S22",
                    description="6.1'' Dynamic AMOLED 2X, 8 ГБ ОЗУ, 128 ГБ памяти, аккумулятор 3700 мАч",
                    price=79990,
                    category="Смартфоны",
                    image_url="galaxy_s22.jpg",
                    stock=12,
                    rating=4.8,
                    reviews_count=45,
                    discount=5
                ),
                Product(
                    name="Ноутбук Apple MacBook Air M1",
                    description="13.3'' Retina, Apple M1, 8 ГБ ОЗУ, 256 ГБ SSD, macOS",
                    price=89990,
                    category="Ноутбуки",
                    image_url="macbook_air.webp",
                    stock=8,
                    rating=4.9,
                    reviews_count=62
                ),
                Product(
                    name="Наушники Sony WH-1000XM4",
                    description="Беспроводные, с шумоподавлением, до 30 часов работы",
                    price=24990,
                    category="Аксессуары",
                    image_url="sony_xm4.webp",
                    stock=15,
                    rating=4.7,
                    reviews_count=38,
                    discount=10
                ),
                Product(
                    name="Фотоаппарат Canon EOS R6",
                    description="Беззеркальная камера, 20 Мп, 4K видео, Wi-Fi/Bluetooth",
                    price=159990,
                    category="Фототехника",
                    image_url="canon_r6.webp",
                    stock=5,
                    rating=4.6,
                    reviews_count=27
                ),
                Product(
                    name="Умные часы Apple Watch Series 7",
                    description="45 мм, GPS + Cellular, экран Retina, мониторинг здоровья",
                    price=42990,
                    category="Гаджеты",
                    image_url="apple_watch.jpeg",
                    stock=20,
                    rating=4.5,
                    reviews_count=53,
                    discount=7
                ),
                Product(
                    name="Игровая консоль PlayStation 5",
                    description="825 ГБ SSD, 4K UHD Blu-ray, беспроводной геймпад",
                    price=69990,
                    category="Игровые консоли",
                    image_url="ps5.webp",
                    stock=3,
                    rating=4.9,
                    reviews_count=89
                ),
                Product(
                    name="Телевизор LG OLED C1",
                    description="55'' 4K Smart TV, OLED, HDR, процессор α9 Gen4",
                    price=99990,
                    category="Телевизоры",
                    image_url="lg_oled.webp",
                    stock=7,
                    rating=4.8,
                    reviews_count=41
                )
            ]

            db.session.bulk_save_objects(test_products)
            db.session.commit()
            print("Добавлено 7 тестовых товаров")

    app.run(debug=True)
