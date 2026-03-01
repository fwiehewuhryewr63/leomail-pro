import React, { createContext, useContext, useState, useCallback, useRef } from 'react';

const ToastContext = createContext(null);

let toastId = 0;

export function ToastProvider({ children }) {
    const [toasts, setToasts] = useState([]);
    const timers = useRef({});

    const addToast = useCallback((message, type = 'info', duration = 3500) => {
        const id = ++toastId;
        setToasts(prev => [...prev, { id, message, type, exiting: false }]);

        timers.current[id] = setTimeout(() => {
            setToasts(prev => prev.map(t => t.id === id ? { ...t, exiting: true } : t));
            setTimeout(() => {
                setToasts(prev => prev.filter(t => t.id !== id));
                delete timers.current[id];
            }, 300);
        }, duration);

        return id;
    }, []);

    const removeToast = useCallback((id) => {
        clearTimeout(timers.current[id]);
        setToasts(prev => prev.map(t => t.id === id ? { ...t, exiting: true } : t));
        setTimeout(() => {
            setToasts(prev => prev.filter(t => t.id !== id));
        }, 300);
    }, []);

    const toastApi = useRef(null);
    if (!toastApi.current) {
        toastApi.current = {};
    }
    toastApi.current.success = (msg) => addToast(msg, 'success');
    toastApi.current.error = (msg) => addToast(msg, 'danger');
    toastApi.current.info = (msg) => addToast(msg, 'info');
    toastApi.current.warn = (msg) => addToast(msg, 'warning');

    return (
        <ToastContext.Provider value={toastApi.current}>
            {children}
            <div className="toast-container">
                {toasts.map(t => (
                    <div
                        key={t.id}
                        className={`toast toast-${t.type} ${t.exiting ? 'toast-exit' : ''}`}
                        onClick={() => removeToast(t.id)}
                    >
                        <span>{t.message}</span>
                    </div>
                ))}
            </div>
        </ToastContext.Provider>
    );
}

export function useToast() {
    const ctx = useContext(ToastContext);
    if (!ctx) throw new Error('useToast must be used within ToastProvider');
    return ctx;
}
