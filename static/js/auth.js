/**
 * Utilidades de autenticación
 */

// Obtener token del localStorage
function getToken() {
    return localStorage.getItem('access_token');
}

// Guardar token
function setToken(token) {
    localStorage.setItem('access_token', token);
}

// Eliminar token
function removeToken() {
    localStorage.removeItem('access_token');
}

// Verificar si está autenticado
function isAuthenticated() {
    return !!getToken();
}

// Redirigir si no está autenticado
function requireAuth() {
    if (!isAuthenticated()) {
        window.location.href = '/static/login.html';
    }
}

// Hacer petición autenticada
async function fetchWithAuth(url, options = {}) {
    const token = getToken();

    const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
        ...options.headers
    };

    const response = await fetch(url, {
        ...options,
        headers
    });

    // Si no autorizado, redirigir a login
    if (response.status === 401) {
        removeToken();
        window.location.href = '/static/login.html';
    }

    return response;
}

// Cerrar sesión
function logout() {
    removeToken();
    window.location.href = '/';
}
