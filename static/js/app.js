const API_BASE = '';

function getToken() {
    return localStorage.getItem('access_token');
}

function getRefreshToken() {
    return localStorage.getItem('refresh_token');
}

function setTokens(access, refresh) {
    localStorage.setItem('access_token', access);
    localStorage.setItem('refresh_token', refresh);
}

function clearTokens() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
}

function isAuthenticated() {
    return !!getToken();
}

function getUser() {
    try {
        return JSON.parse(localStorage.getItem('user'));
    } catch {
        return null;
    }
}

function setUser(user) {
    localStorage.setItem('user', JSON.stringify(user));
}

async function apiRequest(url, options = {}) {
    const token = getToken();
    const headers = options.headers || {};

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(`${API_BASE}${url}`, {
        ...options,
        headers,
    });

    if (response.status === 401 && getRefreshToken()) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
            headers['Authorization'] = `Bearer ${getToken()}`;
            const retryResponse = await fetch(`${API_BASE}${url}`, {
                ...options,
                headers,
            });
            return retryResponse;
        } else {
            clearTokens();
            window.location.href = '/login/';
            return null;
        }
    }

    return response;
}

async function refreshAccessToken() {
    const refresh = getRefreshToken();
    if (!refresh) return false;

    try {
        const response = await fetch(`${API_BASE}/api/auth/token/refresh/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh }),
        });

        if (response.ok) {
            const data = await response.json();
            if (data.access) {
                setTokens(data.access, refresh);
                return true;
            }
        } else {
            clearTokens();
            window.location.href = '/login/';
        }
    } catch (e) {
        console.error('Token refresh failed', e);
    }
    return false;
}

function showAlert(message, type = 'danger') {
    const container = document.getElementById('alertContainer');
    if (!container) return;

    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    container.appendChild(alert);

    setTimeout(() => {
        alert.classList.remove('show');
        setTimeout(() => alert.remove(), 300);
    }, 5000);
}

async function apiGet(url) {
    const response = await apiRequest(url);
    if (!response) return null;
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        showAlert(err.error || err.detail || 'Request failed', 'danger');
        return null;
    }
    return response.json();
}

async function apiPost(url, data) {
    const response = await apiRequest(url, {
        method: 'POST',
        body: JSON.stringify(data),
    });
    if (!response) return null;
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        showAlert(result.error || JSON.stringify(result) || 'Request failed', 'danger');
        return null;
    }
    return result;
}

async function apiPatch(url, data) {
    const response = await apiRequest(url, {
        method: 'PATCH',
        body: JSON.stringify(data),
    });
    if (!response) return null;
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        showAlert(result.error || 'Request failed', 'danger');
        return null;
    }
    return result;
}

async function apiDelete(url) {
    const response = await apiRequest(url, { method: 'DELETE' });
    if (!response) return null;
    return response.json().catch(() => ({}));
}

document.addEventListener('DOMContentLoaded', function () {
    const logoutBtn = document.getElementById('logoutBtn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', function (e) {
            e.preventDefault();
            clearTokens();
            window.location.href = '/';
        });
    }

    updateNavbar();
});

function updateNavbar() {
    const user = getUser();
    if (user && isAuthenticated()) {
        document.querySelectorAll('.nav-guest').forEach(el => el.style.display = 'none');
        document.querySelectorAll('.nav-authenticated').forEach(el => el.style.display = 'block');
    } else {
        document.querySelectorAll('.nav-guest').forEach(el => el.style.display = 'block');
        document.querySelectorAll('.nav-authenticated').forEach(el => el.style.display = 'none');
    }
}
