# KaonISU — AGENTS.md

## Quick start

```bash
# Full Windows setup (venv + install + migrate + seed + superuser)
.\setup.bat

# Dev server (HTTP only)
.\venv\Scripts\python manage.py runserver

# Dev server with WebSocket support (requires Memurai/Redis on :6379)
.\venv\Scripts\uvicorn food_ordering.asgi:application --reload
```

## Architecture

- **Single app** `customer/` holds all models, views, serializers, consumers, URLs, and templates.
- **`food_ordering/`** is the Django project config (settings, ASGI, root URLs).
- **`canteen/`** is a placeholder app (not yet used).
- **ASGI entrypoint**: `food_ordering.asgi:application` — routes HTTP to Django, WebSocket to `AuthMiddlewareStack(URLRouter(customer.routing.websocket_urlpatterns))`.
- **WebSocket**: connect to `ws://host/ws/orders/?token=<JWT>`. JWT passed as query param (not session auth). Channel groups: `user_{uuid}`, `admin`, `menu_updates`.
- **Custom User model** (`customer.User`): PK is `user_id` (UUID), `USERNAME_FIELD = 'email'`. When calling `create_user`, pass both `username=data['email']` and `email=data['email']` — Django requires `username` even though login uses email.
- **Models**: UUID PKs for `User`, `Cart`, `CartItem`, `Order`, `OrderItem`, `OrderStatusHistory`, `Feedback`, `Notification`, `DiscountUsage`. Auto-increment PKs for `MenuItem`, `Store`, `ItemVariation`, `Discount`, `BundleDeal`, `ValidID`.
- **Time zone**: `Asia/Manila` in settings.
- **DB**: SQLite (`db.sqlite3`).
- **Templates** in `templates/` (landing, login, register, menu, cart, orders, tracking, feedback, store dashboard, admin dashboard).
- **Static files** in `static/` (css/style.css, js/app.js).

## Auth & registration

- **4 user types**: `student`, `faculty`, `store_owner`, `admin`.
- Student/faculty registration validates against `ValidID` whitelist and sets `is_active=False` (admin must approve). Faculty can upload ID image.
- Store owner registration requires DTI permit upload (`dti_permit`). Admin must approve via `POST /api/seed/admin/` or admin panel.
- User must be activated before they can log in.
- JWT: 30-min access tokens, 7-day refresh, rotation enabled. Header: `Authorization: Bearer <token>`.
- Users created with `register` view set `is_active=False`; admin must toggle active.

## Commands

```bash
# Migrations
python manage.py makemigrations
python manage.py migrate

# Seed data
python manage.py shell -c "from django.test import Client; c=Client(); c.post('/api/seed/menu/'); c.post('/api/seed/ids/')"

# Admin user
python manage.py createsuperuser
```

## Tests

No tests exist (`customer/tests.py` is empty). No test runner or CI configured. Do not assume pytest or any testing framework.

## Linting / formatting

No linter or formatter config in the repo. Do not assume ruff, black, flake8, or similar.

## Operational quirks

- **Memurai** (Windows Redis) must be running on `127.0.0.1:6379` for WebSocket/Channels — hard requirement, no fallback channel layer configured.
- Image uploads are auto-compressed to JPEG via `compress_image()` in views (Pillow).
- Gmail SMTP credentials are hardcoded in `settings.py` — do not commit changes to those values.
- Registration sets `is_active=False` — new users cannot log in until an admin activates them.
- `full_name` must match format `Surname, First Name M.` (validated by regex in serializers).
- `Order.status` choices: `pending`, `store_accepted`, `store_rejected`, `preparing`, `ready_for_pickup`, `completed`, `cancelled`. Flow: `pending → store_accepted → preparing → ready_for_pickup → completed`, with cancel from any state.
- `MenuItem.is_available` is auto-set from `stock > 0` in the model's `save()`.
- No `.gitignore` at root level (only auto-generated under `venv/`).
