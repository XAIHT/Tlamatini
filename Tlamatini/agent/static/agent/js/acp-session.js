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
        const r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
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
    if (SESSION_ID) {
        const url = `/agent/cleanup_session/?session_id=${SESSION_ID}`;
        if (navigator.sendBeacon) {
            navigator.sendBeacon(url);
            console.log(`[Session] Cleanup beacon sent for ${SESSION_ID}`);
        } else {
            fetch(url, { keepalive: true });
        }
    }
});

// Also cleanup on beforeunload for browsers that don't fire pagehide reliably
window.addEventListener('beforeunload', (_event) => {
    if (SESSION_ID) {
        const url = `/agent/cleanup_session/?session_id=${SESSION_ID}`;
        if (navigator.sendBeacon) {
            navigator.sendBeacon(url);
        }
    }
});

// ========================================
// REQUEST HEADERS HELPER
// ========================================
/**
 * Returns common headers for all fetch() requests, including the session ID.
 * @returns {Object} Headers object
 */
function getHeaders() {
    return {
        'X-Agent-Session-ID': SESSION_ID,
    };
}
