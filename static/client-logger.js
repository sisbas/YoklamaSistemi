// Minimal client-side error reporter that forwards errors to /client-logs.
(function () {
    const ENDPOINT = '/client-logs';
    const MAX_MESSAGE_LENGTH = 500;

    function truncate(value) {
        if (typeof value !== 'string') {
            return value;
        }
        return value.length > MAX_MESSAGE_LENGTH ? value.slice(0, MAX_MESSAGE_LENGTH) + '…' : value;
    }

    function send(payload) {
        try {
            const body = JSON.stringify(payload);
            if (navigator.sendBeacon) {
                const blob = new Blob([body], { type: 'application/json' });
                navigator.sendBeacon(ENDPOINT, blob);
            } else {
                fetch(ENDPOINT, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body,
                    keepalive: true,
                }).catch(() => {});
            }
        } catch (err) {
            // Swallow errors to avoid impacting the host page.
        }
    }

    function buildPayload(level, message, metadata) {
        return {
            level,
            message: truncate(message || ''),
            url: window.location.href,
            ua: navigator.userAgent,
            ts: new Date().toISOString(),
            stack: truncate(metadata && metadata.stack ? String(metadata.stack) : ''),
            extra: metadata && metadata.extra ? metadata.extra : undefined,
        };
    }

    window.addEventListener('error', function (event) {
        const payload = buildPayload('error', event.message || 'Script error', {
            stack: event.error && event.error.stack,
            extra: {
                filename: event.filename,
                lineno: event.lineno,
                colno: event.colno,
            },
        });
        send(payload);
    });

    window.addEventListener('unhandledrejection', function (event) {
        let message = 'Unhandled promise rejection';
        let stack = '';
        if (event.reason) {
            if (typeof event.reason === 'string') {
                message = event.reason;
            } else if (event.reason.message) {
                message = event.reason.message;
            }
            stack = event.reason && event.reason.stack ? event.reason.stack : '';
        }
        const payload = buildPayload('error', message, { stack });
        send(payload);
    });
})();
