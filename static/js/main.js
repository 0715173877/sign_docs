// Main JavaScript for SignDocs
// Professional Document Signing Application

(function() {
    'use strict';

    // ============================================
    // DOM Ready
    // ============================================
    document.addEventListener('DOMContentLoaded', function() {
        initAutoDismissAlerts();
        initTooltips();
        initFileInputStyling();
        initSmoothScroll();
        initModals();
        initPasswordToggle();
        initDeleteConfirmations();
    });

    // ============================================
    // Auto-dismiss Alerts after 5 seconds
    // ============================================
    function initAutoDismissAlerts() {
        const alerts = document.querySelectorAll('.alert-dismissible');
        alerts.forEach(function(alert) {
            setTimeout(function() {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }, 5000);
        });
    }

    // ============================================
    // Initialize Bootstrap Tooltips
    // ============================================
    function initTooltips() {
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        if (tooltipTriggerList.length > 0) {
            [...tooltipTriggerList].map(el => new bootstrap.Tooltip(el));
        }
    }

    // ============================================
    // File Input Styling Enhancement
    // ============================================
    function initFileInputStyling() {
        document.querySelectorAll('input[type="file"]').forEach(function(input) {
            input.addEventListener('change', function(e) {
                const fileName = e.target.files[0]?.name;
                const label = e.target.closest('.mb-3')?.querySelector('.file-name-display');
                if (label && fileName) {
                    label.textContent = fileName;
                    label.classList.remove('text-muted');
                    label.classList.add('text-success', 'fw-semibold');
                }
            });
        });
    }

    // ============================================
    // Smooth Scroll to Anchor Links
    // ============================================
    function initSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
            anchor.addEventListener('click', function(e) {
                const href = this.getAttribute('href');
                if (href === '#') return;
                const target = document.querySelector(href);
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        });
    }

    // ============================================
    // Initialize Bootstrap Modals
    // ============================================
    function initModals() {
        // Bootstrap handles data-bs-toggle="modal" automatically via event delegation.
        // No need to pre-initialize modals - that can cause conflicts.
        // We just listen for shown events to fix z-index issues.
        
        // Fix for modal backdrop blocking clicks on form elements
        document.addEventListener('shown.bs.modal', function() {
            const modals = document.querySelectorAll('.modal.show');
            modals.forEach(function(m) {
                m.style.zIndex = '1056';
            });
        });
    }

    // ============================================
    // Password Visibility Toggle
    // ============================================
    function initPasswordToggle() {
        document.querySelectorAll('.password-toggle').forEach(function(btn) {
            btn.addEventListener('click', function() {
                const input = this.closest('.input-group').querySelector('input');
                if (!input) return;
                const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
                input.setAttribute('type', type);
                this.querySelector('i').classList.toggle('bi-eye');
                this.querySelector('i').classList.toggle('bi-eye-slash');
            });
        });
    }

    // ============================================
    // Delete Confirmation
    // ============================================
    function initDeleteConfirmations() {
        document.querySelectorAll('[data-confirm]').forEach(function(el) {
            el.addEventListener('click', function(e) {
                const message = this.getAttribute('data-confirm') || 'Are you sure you want to delete this?';
                if (!confirm(message)) {
                    e.preventDefault();
                }
            });
        });
    }

    // ============================================
    // Utility: Show Toast Notification
    // ============================================
    window.showToast = function(message, type) {
        type = type || 'info';
        const container = document.querySelector('.toast-container') || (function() {
            const div = document.createElement('div');
            div.className = 'toast-container position-fixed top-0 end-0 p-3';
            div.style.zIndex = '9999';
            document.body.appendChild(div);
            return div;
        })();

        const icons = {
            success: 'bi-check-circle-fill text-success',
            error: 'bi-x-circle-fill text-danger',
            warning: 'bi-exclamation-triangle-fill text-warning',
            info: 'bi-info-circle-fill text-primary'
        };

        const bgColors = {
            success: '#e6f9f2',
            error: '#fde8ed',
            warning: '#fff8e1',
            info: '#eef0ff'
        };

        const toast = document.createElement('div');
        toast.className = 'd-flex align-items-center gap-2 p-3 mb-2 rounded shadow-lg border';
        toast.style.background = bgColors[type] || bgColors.info;
        toast.style.borderLeft = '4px solid ' + (type === 'success' ? '#06d6a0' : type === 'error' ? '#ef476f' : type === 'warning' ? '#ffd166' : '#4361ee');
        toast.style.minWidth = '280px';
        toast.style.animation = 'slideInLeft 0.3s ease-out';
        toast.innerHTML = '<i class="bi ' + (icons[type] || icons.info) + ' fs-5"></i><span class="flex-grow-1 small fw-medium">' + message + '</span><button class="btn-close btn-close-sm" onclick="this.parentElement.remove()"></button>';
        container.appendChild(toast);

        setTimeout(function() {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(20px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(function() { toast.remove(); }, 300);
        }, 4000);
    };

    // ============================================
    // Utility: Format Date
    // ============================================
    window.formatDate = function(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    // ============================================
    // Utility: Copy to Clipboard
    // ============================================
    window.copyToClipboard = function(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(function() {
                showToast('Copied to clipboard!', 'success');
            }).catch(function() {
                fallbackCopy(text);
            });
        } else {
            fallbackCopy(text);
        }
    };

    function fallbackCopy(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            showToast('Copied to clipboard!', 'success');
        } catch (e) {
            showToast('Failed to copy', 'error');
        }
        document.body.removeChild(textarea);
    }

})();
