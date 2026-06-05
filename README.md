# Canteen Food Ordering System

A real-time food ordering platform designed for school and university canteens. Students and faculty can browse menus, place orders, and track their order status live via WebSockets — all from their mobile or desktop browser.

## Features

- **Role-based registration** — Students and faculty register using their school ID, validated against a pre-seeded whitelist
- **Menu browsing** — Browse canteen items filtered by category (Rice Meals, Noodles, Drinks, Snacks, Desserts)
- **Cart management** — Add, update, and remove items before checkout
- **Order placement** — Convert your cart into an order with a unique order number
- **Real-time tracking** — Track order status live via WebSockets (Received → Preparing → Ready for Pick-Up → Completed)
- **Feedback system** — Rate and review completed orders
- **JWT authentication** — Token-based auth with automatic refresh
- **Mobile-responsive** — Built with Bootstrap 5, works on any device

## Tech Stack

| Technology | Purpose |
|---|---|
| **Python 3.14** | Runtime |
| **Django 6.0** | Web framework |
| **Django REST Framework** | REST API |
| **SimpleJWT** | JWT authentication |
| **Django Channels** | WebSocket support |
| **SQLite** | Database |
| **Bootstrap 5.3** | Frontend UI |
| **Vanilla JavaScript** | Client-side logic |

## Project Structure

```
food-ordering/
├── canteen/                        # Placeholder app (future cashier panel)
├── customer/                       # Main app
│   ├── admin.py                    # Django admin registrations
│   ├── consumers.py                # WebSocket consumer
│   ├── models.py                   # 9 models (User, Order, MenuItem, etc.)
│   ├── serializers.py              # 13 serializers
│   ├── urls.py                     # 22 URL patterns
│   └── views.py                    # API + page view functions
├── food_ordering/                  # Django project config
│   ├── asgi.py                     # ASGI (HTTP + WebSocket routing)
│   ├── settings.py
│   └── urls.py
├── static/
│   ├── css/style.css
│   └── js/app.js                   # JWT management, API helpers
├── templates/                      # 9 Django templates
│   ├── base.html
│   ├── landing.html
│   ├── login.html
│   ├── register.html
│   ├── menu.html
│   ├── cart_review.html
│   ├── order_confirmation.html
│   ├── order_tracking.html
│   ├── feedback.html
│   └── my_orders.html
├── manage.py
└── db.sqlite3
```

## Models

| Model | Description |
|---|---|
| `User` | Custom user with `user_type` (student/faculty), `student_faculty_id`, email-based auth |
| `ValidID` | Whitelist of valid school IDs for registration |
| `MenuItem` | Canteen items with name, price, category, availability |
| `Cart` | One cart per user |
| `CartItem` | Individual items in a cart |
| `Order` | Placed orders with status tracking |
| `OrderItem` | Snapshotted items within an order |
| `OrderStatusHistory` | Full status change audit trail |
| `Feedback` | Rating and comments for completed orders |

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register/` | Register with valid school ID |
| POST | `/api/auth/login/` | Login via email/password |
| POST | `/api/auth/token/refresh/` | Refresh JWT token |
| GET | `/api/auth/me/` | Get current user profile |

### Menu
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/menu/?category=` | List available menu items |

### Cart
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/cart/` | Get cart with items and totals |
| POST | `/api/cart/add/` | Add item to cart |
| PATCH | `/api/cart/item/{id}/` | Update item quantity |
| DELETE | `/api/cart/clear/` | Clear entire cart |

### Orders
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/orders/` | List user's orders |
| POST | `/api/orders/place/` | Place order from cart |
| GET | `/api/orders/{id}/` | Order detail |
| GET | `/api/orders/{id}/track/` | Order tracking info |

### Feedback
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/feedback/` | Submit feedback for completed order |

### Admin
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/admin/orders/{id}/status/` | Advance order status |

### Seed Data
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/seed/menu/` | Populate 15 menu items |
| POST | `/api/seed/ids/` | Populate 5 valid school IDs |

## WebSocket

Connect to `ws://host/ws/orders/` with session auth to receive real-time order status updates. Falls back to polling every 15 seconds.

## Getting Started

### Prerequisites
- Python 3.14+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/food-ordering.git
cd food-ordering

# Create and activate virtual environment
python -m venv venv

# Windows
.\venv\Scripts\Activate.ps1

# macOS/Linux
# source venv/bin/activate

# Install dependencies
pip install django djangorestframework djangorestframework-simplejwt django-cors-headers channels

# Run migrations
python manage.py migrate

# Seed sample data
python manage.py shell -c "from django.test import Client; Client().post('/api/seed/menu/'); Client().post('/api/seed/ids/')"

# Create admin user
python manage.py createsuperuser

# Run the server (ASGI for WebSocket support)
uvicorn food_ordering.asgi:application --reload

# Or run with Daphne
# daphne -p 8000 food_ordering.asgi:application
```

Visit `http://localhost:8000/` to start using the application.

### Django Admin

Access the admin dashboard at `/admin/` to manage users, menu items, orders, and feedback.

## Order Status Flow

```
Received → Preparing → Ready for Pick-Up → Completed
                                                      
Any status → Cancelled
```

## License

This project is for educational purposes.
