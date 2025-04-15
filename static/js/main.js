document.addEventListener('DOMContentLoaded', function() {
    // Добавление в корзину
    document.querySelectorAll('.add-to-cart').forEach(button => {
        button.addEventListener('click', function() {
            const productId = this.dataset.productId;
            addToCart(productId);
        });
    });

    // Управление количеством
    document.querySelectorAll('.quantity-btn').forEach(button => {
        button.addEventListener('click', function() {
            const input = this.parentElement.querySelector('input');
            let value = parseInt(input.value);

            if (this.classList.contains('minus') && value > 1) {
                input.value = value - 1;
            } else if (this.classList.contains('plus')) {
                input.value = value + 1;
            }
        });
    });

    // Фильтрация товаров
    const filterForm = document.getElementById('filter-form');
    if (filterForm) {
        filterForm.addEventListener('submit', function(e) {
            e.preventDefault();
            applyFilters();
        });
    }

    // Поиск товаров
    const searchBtn = document.getElementById('search-btn');
    if (searchBtn) {
        searchBtn.addEventListener('click', applyFilters);
    }
});

function addToCart(productId) {
    fetch('/add_to_cart/' + productId)
        .then(response => response.json())
        .then(data => {
            updateCartCount(data.cart_count);
            showToast('Товар добавлен в корзину');
        });
}

function updateCartCount(count) {
    const cartCount = document.querySelector('.cart-count');
    if (cartCount) {
        cartCount.textContent = count;
    }
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function applyFilters() {
    const params = new URLSearchParams();

    // Категории
    document.querySelectorAll('input[name="category"]:checked').forEach(checkbox => {
        params.append('category', checkbox.value);
    });

    // Сортировка
    const sortBy = document.getElementById('sort-by').value;
    params.append('sort', sortBy);

    // Поиск
    const searchQuery = document.getElementById('search-input').value;
    if (searchQuery) {
        params.append('search', searchQuery);
    }

    // Перенаправление с новыми параметрами
    window.location.href = '/catalog?' + params.toString();
}