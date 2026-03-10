// Agentic Control Panel - Session Management
// LOAD ORDER: #2 - Depends on: nothing (standalone)
//
// Sessions are used for collision avoidance between browser tabs.
// They are ephemeral (not persisted across page loads).

// ========================================
// SESSION ID GENERATION
// ========================================
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function getCookie(name) {
    const cookieValue = `; ${document.cookie}`;
    const parts = cookieValue.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(';').shift() || '';
    }
    return '';
}

function getCsrfToken() {
    return getCookie('csrftoken');
}

function buildSessionBeaconPayload() {
    const formData = new FormData();
    formData.append('session_id', SESSION_ID);
    const csrfToken = getCsrfToken();
    if (csrfToken) {
        formData.append('csrfmiddlewaretoken', csrfToken);
    }
    return formData;
}

function sendSessionCleanup() {
    if (!SESSION_ID) {
        return;
    }

    const url = '/agent/cleanup_session/';
    const payload = buildSessionBeaconPayload();

    if (navigator.sendBeacon) {
        navigator.sendBeacon(url, payload);
        console.log(`[Session] Cleanup beacon sent for ${SESSION_ID}`);
        return;
    }

    fetch(url, {
        method: 'POST',
        headers: getHeaders(),
        credentials: 'same-origin',
        body: payload,
        keepalive: true
    }).catch((error) => {
        console.warn('[Session] Cleanup request failed:', error);
    });
}

// Always generate fresh session ID on each page load
const SESSION_ID = generateUUID();
console.log(`[Session] Initialized with ID: ${SESSION_ID}`);

// ========================================
// SESSION CLEANUP ON PAGE UNLOAD
// ========================================
// ALWAYS clean up session pool on page unload/close.
// This fires on both reload and close - that's intentional.
window.addEventListener('pagehide', (_event) => {
    sendSessionCleanup();
});

// Also cleanup on beforeunload for browsers that don't fire pagehide reliably
window.addEventListener('beforeunload', (_event) => {
    sendSessionCleanup();
});

// ========================================
// REQUEST HEADERS HELPER
// ========================================
/**
 * Returns common headers for all fetch() requests, including the session ID.
 * @returns {Object} Headers object
 */
function getHeaders() {
    const headers = {
        'X-Agent-Session-ID': SESSION_ID,
    };

    const csrfToken = getCsrfToken();
    if (csrfToken) {
        headers['X-CSRFToken'] = csrfToken;
    }

    return headers;
}
