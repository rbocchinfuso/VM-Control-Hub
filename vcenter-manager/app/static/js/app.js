document.addEventListener('DOMContentLoaded', function() {
    var tooltipEls = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipEls.forEach(function(el) {
        new bootstrap.Tooltip(el);
    });

    setTimeout(function() {
        document.querySelectorAll('.alert.alert-dismissible').forEach(function(alert) {
            var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) bsAlert.close();
        });
    }, 5000);
});
