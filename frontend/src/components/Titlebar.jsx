import React from 'react';
import { Minus, Square, X } from 'lucide-react';

/**
 * Custom frameless titlebar for Electron.
 * Only renders when running inside Electron (detected via preload.js).
 */
export default function Titlebar() {
    const isElectron = window.electronAPI?.isElectron;
    if (!isElectron) return null;

    return (
        <div className="titlebar">
            <div className="titlebar-brand">
                <span className="titlebar-brand-name">Leomail</span>
                <span className="titlebar-brand-sub">boxed runtime</span>
            </div>

            <div className="titlebar-center-pill">
                <span className="titlebar-center-dot" />
                <span className="titlebar-center-text">Operations Workspace</span>
            </div>

            <div className="titlebar-spacer" />

            <div className="titlebar-controls">
                <button onClick={() => window.electronAPI.minimize()} className="titlebar-btn">
                    <Minus size={14} />
                </button>
                <button onClick={() => window.electronAPI.maximize()} className="titlebar-btn">
                    <Square size={10} />
                </button>
                <button onClick={() => window.electronAPI.close()} className="titlebar-btn titlebar-btn-close">
                    <X size={14} />
                </button>
            </div>
        </div>
    );
}
