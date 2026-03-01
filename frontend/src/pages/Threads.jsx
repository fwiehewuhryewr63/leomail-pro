import React, { useState, useEffect, useRef } from 'react';
import { API } from '../api';
import { ProviderLogo } from '../components/ProviderLogos';



const STATUS_CONFIG = {
    registered: { label: 'Registered ✓', color: '#10B981', bg: 'rgba(16,185,129,0.12)', border: '#10B981' },
    sms: { label: '↔ SMS code...', color: '#06B6D4', bg: 'rgba(6,182,212,0.10)', border: '#06B6D4' },
    proxy_refused: { label: 'Proxy refused', color: '#EF4444', bg: 'rgba(239,68,68,0.10)', border: '#EF4444' },
    captcha: { label: 'FunCaptcha solving...', color: '#F59E0B', bg: 'rgba(245,158,11,0.10)', border: '#F59E0B' },
    queued: { label: 'Queued', color: '#6B7280', bg: 'transparent', border: '#2a2d35' },
    running: { label: 'Running...', color: '#06B6D4', bg: 'rgba(6,182,212,0.06)', border: '#06B6D4' },
    error: { label: 'Error', color: '#EF4444', bg: 'rgba(239,68,68,0.08)', border: '#EF4444' },
    done: { label: 'Registered ✓', color: '#10B981', bg: 'rgba(16,185,129,0.08)', border: '#10B981' },
    sms_verification: { label: 'SMS verification...', color: '#06B6D4', bg: 'rgba(6,182,212,0.08)', border: '#06B6D4' },
    proxy_timeout: { label: 'Proxy timeout', color: '#EF4444', bg: 'rgba(239,68,68,0.08)', border: '#EF4444' },
};

function getStatusConfig(status, action) {
    if (status === 'done') return STATUS_CONFIG.registered;
    if (status === 'error') {
        if (action?.includes('Proxy')) return STATUS_CONFIG.proxy_refused;
        return STATUS_CONFIG.error;
    }
    if (status === 'running') {
        if (action?.includes('SMS') || action?.includes('sms')) return STATUS_CONFIG.sms;
        if (action?.includes('captcha') || action?.includes('Captcha') || action?.includes('FunCaptcha')) return STATUS_CONFIG.captcha;
        return STATUS_CONFIG.running;
    }
    return STATUS_CONFIG[status] || STATUS_CONFIG.queued;
}

function formatElapsed(startTime) {
    if (!startTime) return '';
    const diff = Math.floor((Date.now() - new Date(startTime).getTime()) / 1000);
    if (diff < 0) return '0m 00s';
    const mins = Math.floor(diff / 60);
    const secs = diff % 60;
    return `${mins}m ${secs.toString().padStart(2, '0')}s`;
}

function formatTimestamp(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

export default function Threads() {
    const [threads, setThreads] = useState([]);
    const [autoScroll, setAutoScroll] = useState(true);
    const [stats, setStats] = useState({ completed: 0, failed: 0, running: 0, success_rate: 0 });
    const containerRef = useRef(null);

    const load = () => {
        fetch(`${API}/resources/active-threads`)
            .then(r => r.json())
            .then(d => {
                const arr = Array.isArray(d) ? d : [];
                setThreads(arr);
                const completed = arr.filter(t => t.status === 'done').length;
                const failed = arr.filter(t => t.status === 'error').length;
                const running = arr.filter(t => t.status === 'running').length;
                const total = completed + failed;
                setStats({
                    completed,
                    failed,
                    running,
                    success_rate: total > 0 ? ((completed / total) * 100).toFixed(1) : 0,
                });
            })
            .catch(() => { });
    };

    useEffect(() => {
        load();
        const iv = setInterval(load, 3000);
        return () => clearInterval(iv);
    }, []);

    useEffect(() => {
        if (autoScroll && containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [threads, autoScroll]);

    const activeCount = threads.filter(t => t.status === 'running').length;

    const clearThreads = () => {
        setThreads([]);
        setStats({ completed: 0, failed: 0, running: 0, success_rate: 0 });
    };

    return (
        <div className="page">
            {/* ── Header ── */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h2 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ fontSize: '1.5em', fontWeight: 300, fontStyle: 'italic', color: 'var(--text-primary)' }}>Live Threads</span>
                    {activeCount > 0 && (
                        <span style={{
                            display: 'inline-flex', alignItems: 'center', gap: 6,
                            fontSize: '0.5em', padding: '4px 12px', borderRadius: 20,
                            color: '#10B981', fontWeight: 700,
                        }}>
                            <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10B981', boxShadow: '0 0 6px #10B981' }} />
                            {activeCount} active
                        </span>
                    )}
                </h2>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.85em', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                        Auto-scroll
                        <div onClick={() => setAutoScroll(!autoScroll)} style={{
                            width: 38, height: 20, borderRadius: 10, cursor: 'pointer',
                            background: autoScroll ? '#10B981' : 'var(--bg-input)',
                            border: '1px solid var(--border-default)',
                            position: 'relative', transition: 'background 0.2s',
                        }}>
                            <div style={{
                                width: 16, height: 16, borderRadius: '50%', background: '#fff',
                                position: 'absolute', top: 1, left: autoScroll ? 19 : 1, transition: 'left 0.2s',
                            }} />
                        </div>
                    </label>
                    <button className="btn" onClick={clearThreads} style={{
                        padding: '6px 16px', fontSize: '0.85em', fontWeight: 600,
                        border: '1px solid var(--border-default)', background: 'transparent',
                    }}>
                        Clear
                    </button>
                </div>
            </div>

            {/* ── Stats bar ── */}
            <div className="card" style={{
                padding: '10px 18px', marginBottom: 16,
                fontSize: '0.85em', color: 'var(--text-secondary)',
                display: 'flex', alignItems: 'center', gap: 8,
            }}>
                <span style={{ fontWeight: 600 }}>Today:</span>
                <span style={{ color: '#10B981', fontWeight: 700 }}>{stats.completed} ✓ completed</span>
                <span style={{ color: 'var(--text-muted)' }}>|</span>
                <span style={{ color: '#EF4444', fontWeight: 700 }}>{stats.failed} ✗ failed</span>
                <span style={{ color: 'var(--text-muted)' }}>|</span>
                <span style={{ color: '#06B6D4', fontWeight: 700 }}>{stats.running} ↻ running</span>
                <span style={{ color: 'var(--text-muted)' }}>—</span>
                <span style={{ fontWeight: 700 }}>{stats.success_rate}% success</span>
            </div>

            {/* ── Thread rows ── */}
            <div ref={containerRef} style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 'calc(100vh - 240px)', overflowY: 'auto' }}>
                {threads.length === 0 ? (
                    <div className="card" style={{ textAlign: 'center', padding: 60, color: 'var(--text-muted)' }}>
                        <div style={{ fontSize: '2em', marginBottom: 8 }}>⊘</div>
                        <div style={{ fontSize: '0.95em' }}>No active threads</div>
                        <div style={{ fontSize: '0.8em', marginTop: 4 }}>Start an autoreg process to see live thread activity</div>
                    </div>
                ) : (
                    threads.map((t, i) => {
                        const sc = getStatusConfig(t.status, t.action);
                        const provider = (t.provider || 'gmail').toLowerCase();

                        return (
                            <div key={t.id || i} style={{
                                display: 'flex', alignItems: 'center', gap: 14,
                                padding: '14px 18px',
                                background: sc.bg,
                                borderLeft: `3px solid ${sc.border}`,
                                borderRadius: 8,
                                border: `1px solid ${sc.border}22`,
                                borderLeftWidth: 3,
                                borderLeftColor: sc.border,
                                transition: 'all 0.3s',
                            }}>
                                {/* Thread ID circle */}
                                <div style={{
                                    width: 36, height: 36, borderRadius: '50%',
                                    border: `2px solid ${sc.border}`,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    fontWeight: 800, fontSize: '0.8em', color: sc.color, flexShrink: 0,
                                }}>
                                    T-{i + 1}
                                </div>

                                {/* Provider logo */}
                                <ProviderLogo provider={provider} size={40} />

                                {/* Email */}
                                <div style={{
                                    flex: 1, minWidth: 0,
                                    fontSize: '0.95em', fontWeight: 500, color: 'var(--text-primary)',
                                    fontFamily: 'monospace',
                                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                }}>
                                    {t.email || '—'}
                                </div>

                                {/* Status pill */}
                                <div style={{
                                    padding: '4px 14px', borderRadius: 6,
                                    background: `${sc.color}18`, border: `1px solid ${sc.color}44`,
                                    color: sc.color, fontWeight: 700, fontSize: '0.82em',
                                    whiteSpace: 'nowrap', flexShrink: 0,
                                }}>
                                    {t.action || sc.label}
                                </div>

                                {/* Elapsed time */}
                                <div style={{
                                    fontSize: '0.85em', color: 'var(--text-muted)', fontWeight: 600,
                                    fontFamily: 'monospace', whiteSpace: 'nowrap', flexShrink: 0, minWidth: 60,
                                    textAlign: 'right',
                                }}>
                                    {formatElapsed(t.started || t.updated)}
                                </div>

                                {/* Timestamp */}
                                <div style={{
                                    fontSize: '0.85em', color: 'var(--text-muted)', fontWeight: 500,
                                    fontFamily: 'monospace', whiteSpace: 'nowrap', flexShrink: 0, minWidth: 44,
                                    textAlign: 'right',
                                }}>
                                    {formatTimestamp(t.updated)}
                                </div>
                            </div>
                        );
                    })
                )}
            </div>
        </div>
    );
}
