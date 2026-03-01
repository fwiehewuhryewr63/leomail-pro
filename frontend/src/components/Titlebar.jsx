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
        <div style={{
            height: 32,
            background: '#07080a',
            display: 'flex',
            alignItems: 'center',
            WebkitAppRegion: 'drag',  // makes it draggable
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            zIndex: 999999,
            borderBottom: '1px solid rgba(255,255,255,0.06)',
            paddingLeft: 14,
            userSelect: 'none',
        }}>
            {/* App title */}
            <span style={{
                fontSize: '0.72em',
                fontWeight: 800,
                letterSpacing: 2,
                color: '#10B981',
                textTransform: 'uppercase',
                fontFamily: 'Inter, system-ui, sans-serif',
            }}>
                LEOMAIL
            </span>
            <span style={{
                fontSize: '0.58em',
                color: 'rgba(255,255,255,0.2)',
                marginLeft: 8,
                fontWeight: 500,
                fontFamily: 'JetBrains Mono, monospace',
            }}>
                v4.0
            </span>

            {/* Spacer */}
            <div style={{ flex: 1 }} />

            {/* Window controls */}
            <div style={{ display: 'flex', WebkitAppRegion: 'no-drag' }}>
                <button onClick={() => window.electronAPI.minimize()} style={btnStyle}>
                    <Minus size={14} />
                </button>
                <button onClick={() => window.electronAPI.maximize()} style={btnStyle}>
                    <Square size={10} />
                </button>
                <button onClick={() => window.electronAPI.close()} style={{ ...btnStyle, ...closeBtnStyle }}>
                    <X size={14} />
                </button>
            </div>
        </div>
    );
}

const btnStyle = {
    width: 46,
    height: 32,
    border: 'none',
    background: 'transparent',
    color: 'rgba(255,255,255,0.5)',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'background 0.15s, color 0.15s',
};

const closeBtnStyle = {
    // hover effects handled by CSS would be better, but inline works
};
