// Bireme Research - Main JavaScript
// Alpine.js and HTMX are loaded via CDN

// HTMX configuration
document.body.addEventListener('htmx:configRequest', function(evt) {
    // CSRF token is set via hx-headers in base.html
});

// Show toast notification
function showToast(message, type = 'success') {
    window.dispatchEvent(new CustomEvent('toast', {
        detail: { message, type }
    }));
}

// Handle HTMX errors
document.body.addEventListener('htmx:responseError', function(evt) {
    showToast('An error occurred. Please try again.', 'error');
});

// Handle successful HTMX swaps that include a message
document.body.addEventListener('htmx:afterSwap', function(evt) {
    const messageEl = evt.detail.target.querySelector('[data-toast-message]');
    if (messageEl) {
        showToast(messageEl.dataset.toastMessage, messageEl.dataset.toastType || 'success');
    }
});
