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
    const timeout = options.timeout || 60000;
    const controller = new AbortController();
    const timer = setTimeout(function() { controller.abort(); }, timeout);

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData)) {
        headers['Content-Type'] = 'application/json';
    }

    function doFetch() {
        return fetch(`${API_BASE}${url}`, {
            ...options,
            headers,
            signal: controller.signal,
        });
    }

    let response;
    try {
        response = await doFetch();
    } catch (e) {
        clearTimeout(timer);
        if (e.name === 'AbortError') {
            throw new Error('Request timed out. Please try again.');
        }
        throw e;
    }

    if (response.status === 401 && getRefreshToken()) {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
            headers['Authorization'] = `Bearer ${getToken()}`;
            try {
                response = await doFetch();
            } catch (e) {
                clearTimeout(timer);
                throw e;
            }
        } else {
            clearTimeout(timer);
            clearTokens();
            window.location.href = '/login/';
            return null;
        }
    }

    clearTimeout(timer);
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
    const icons = { danger: 'bi-exclamation-circle', success: 'bi-check-circle', warning: 'bi-exclamation-triangle', info: 'bi-info-circle' };
    const icon = icons[type] || icons.danger;

    const el = document.createElement('div');
    el.style.cssText = 'display:flex;align-items:center;gap:12px;position:fixed;bottom:30px;right:30px;background:#1a1a1a;color:#fff;padding:16px 20px;border-radius:16px;font-size:14px;font-weight:500;z-index:99999;box-shadow:0 4px 16px rgba(0,0,0,0.2);max-width:420px;word-wrap:break-word;line-height:1.5;';
    el.innerHTML = '<i class="' + icon + '" style="font-size:18px;flex-shrink:0;"></i><span style="flex:1;">' + message + '</span>';

    document.body.appendChild(el);

    setTimeout(function() { el.remove(); }, 5000);
}

function extractError(result) {
    if (typeof result === 'string') return result;
    if (result?.error) return result.error;
    if (result?.detail) return result.detail;
    if (result && typeof result === 'object') {
        const msgs = Object.values(result).flat().filter(Boolean);
        if (msgs.length) return msgs.join(' ');
    }
    return 'Request failed';
}

async function apiGet(url) {
    const response = await apiRequest(url);
    if (!response) return null;
    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        showAlert(extractError(err), 'danger');
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
        showAlert(extractError(result), 'danger');
        return null;
    }
    return result;
}

async function apiPostFormData(url, formData) {
    const response = await apiRequest(url, {
        method: 'POST',
        body: formData,
    });
    if (!response) return null;
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        showAlert(extractError(result), 'danger');
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
        showAlert(extractError(result), 'danger');
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
