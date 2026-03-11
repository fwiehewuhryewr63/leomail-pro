import React, { useState, useEffect, useRef } from 'react';
import { Terminal as TermIcon, Trash2, RefreshCw, Download, Pause, Play } from 'lucide-react';
import { API } from '../api';

const LEVEL_COLORS = {
    INFO: '#10B981',
    WARNING: '#F59E0B',
    ERROR: '#EF4444',
    DEBUG: '#6B7280',
    CRITICAL: '#DC2626',
};

const LEVEL_BG = {
    INFO: 'rgba(16,185,129,0.12)',
    WARNING: 'rgba(245,158,11,0.12)',
    ERROR: 'rgba(239,68,68,0.12)',
    DEBUG: 'rgba(107,114,128,0.12)',
    CRITICAL: 'rgba(220,38,38,0.15)',
};

function parseLevel(line) {
    for (const lvl of ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']) {
        if (line.includes(`| ${lvl}`)) return lvl;
    }
    return 'INFO';
}

export default function Logs() {
    const [logs, setLogs] = useState([]);
    const [total, setTotal] = useState(0);
    const [filter, setFilter] = useState('ALL');
    const [autoScroll, setAutoScroll] = useState(true);
    const [loading, setLoading] = useState(false);
    const termRef = useRef(null);
    const intervalRef = useRef(null);

    /* ── Level counts ── */
    const levelCounts = logs.reduce((acc, line) => {
        const lvl = parseLevel(line);
        acc[lvl] = (acc[lvl] || 0) + 1;
        return acc;
    }, {});

    const loadLogs = async () => {
        try {
            const url = filter === 'ALL'
                ? `${API}/logs/?lines=200`
                : `${API}/logs/?lines=200&level=${filter}`;
            const res = await fetch(url);
            const data = await res.json();
            setLogs(data.logs || []);
            setTotal(data.total || 0);
        } catch { /* ignore */ }
    };

    useEffect(() => {
        loadLogs();
        intervalRef.current = setInterval(loadLogs, 15000);
        return () => clearInterval(intervalRef.current);
    }, [filter]);

    useEffect(() => {
        if (autoScroll && termRef.current) {
            termRef.current.scrollTop = termRef.current.scrollHeight;
        }
    }, [logs, autoScroll]);

    const clearLogs = async () => {
        setLoading(true);
        await fetch(`${API}/logs/`, { method: 'DELETE' });
        setLogs([]);
        setTotal(0);
        setLoading(false);
    };

    const exportLogs = () => {
        const text = logs.join('\n');
        const blob = new Blob([text], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        a.href = url;
        a.download = `leomail_logs_${ts}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const filters = ['ALL', 'INFO', 'WARNING', 'ERROR', 'DEBUG'];

    return (
        <div className="page">
            {/* ═══ HEADER ═══ */}
            <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <div className="page-breadcrumb">MONITORING / LOGS</div>
                    <h2 className="page-title">
                        <TermIcon size={22} /> System Logs
                    </h2>
                    <div className="engine-hero-strip">
                        <div className="engine-hero-chip">
                            <span className="engine-hero-chip-label">Visible</span>
                            <span className="engine-hero-chip-value">{logs.length} lines</span>
                        </div>
                        <div className="engine-hero-chip">
                            <span className="engine-hero-chip-label">Warnings</span>
                            <span className="engine-hero-chip-value">{levelCounts.WARNING || 0}</span>
                        </div>
                        <div className="engine-hero-chip">
                            <span className="engine-hero-chip-label">Errors</span>
                            <span className="engine-hero-chip-value">{(levelCounts.ERROR || 0) + (levelCounts.CRITICAL || 0)}</span>
                        </div>
                        <div className="engine-hero-chip">
                            <span className="engine-hero-chip-label">Mode</span>
                            <span className="engine-hero-chip-value">{autoScroll ? 'Live following' : 'Manual review'}</span>
                        </div>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: '0.75em', color: 'var(--text-muted)', fontWeight: 600 }}>
                        {total} total lines
                    </span>
                </div>
            </div>

            {/* ═══ STAT CARDS ═══ */}
            <div className="config-row-4" style={{ marginBottom: 20 }}>
                {[
                    { label: 'TOTAL', value: logs.length, color: '#10B981' },
                    { label: 'INFO', value: levelCounts.INFO || 0, color: '#3B82F6' },
                    { label: 'WARNING', value: levelCounts.WARNING || 0, color: '#F59E0B' },
                    { label: 'ERROR', value: (levelCounts.ERROR || 0) + (levelCounts.CRITICAL || 0), color: '#EF4444' },
                ].map(s => (
                    <div key={s.label} className="card" style={{ padding: '14px 18px', borderLeft: `3px solid ${s.color}` }}>
                        <div style={{ fontSize: '1.8em', fontWeight: 900, color: s.color, lineHeight: 1 }}>{s.value}</div>
                        <div style={{ fontSize: '0.65em', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 1.5, marginTop: 4 }}>{s.label}</div>
                    </div>
                ))}
            </div>

            {/* ═══ FILTER TOOLBAR ═══ */}
            <div className="card glass-toolbar" style={{ marginBottom: 16, padding: '10px 16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                    {/* Filter pills */}
                    <div style={{ display: 'flex', gap: 6 }}>
                        {filters.map(f => (
                            <button key={f} onClick={() => setFilter(f)} style={{
                                padding: '6px 16px', borderRadius: 20,
                                border: `1px solid ${filter === f ? (LEVEL_COLORS[f] || 'var(--accent)') : 'var(--border-default)'}`,
                                background: filter === f ? (f === 'ALL' ? 'var(--accent)' : LEVEL_COLORS[f]) : 'transparent',
                                color: filter === f ? (f === 'ERROR' || f === 'CRITICAL' ? '#fff' : '#000') : 'var(--text-secondary)',
                                fontSize: '0.78em', fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit',
                                transition: 'all 0.2s',
                                letterSpacing: 0.5,
                            }}>
                                {f}
                                {f !== 'ALL' && <span style={{
                                    marginLeft: 5, fontSize: '0.85em', opacity: 0.8,
                                }}>{levelCounts[f] || 0}</span>}
                            </button>
                        ))}
                    </div>

                    {/* Actions */}
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        {/* Auto-scroll toggle */}
                        <div onClick={() => setAutoScroll(!autoScroll)} style={{
                            display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                            padding: '5px 12px', borderRadius: 16,
                            background: autoScroll ? 'rgba(16,185,129,0.1)' : 'transparent',
                            border: `1px solid ${autoScroll ? 'rgba(16,185,129,0.3)' : 'var(--border-default)'}`,
                            transition: 'all 0.2s',
                        }}>
                            {autoScroll ? <Play size={11} style={{ color: '#10B981' }} /> : <Pause size={11} style={{ color: 'var(--text-muted)' }} />}
                            <span style={{ fontSize: '0.75em', fontWeight: 600, color: autoScroll ? '#10B981' : 'var(--text-muted)' }}>Auto-scroll</span>
                        </div>

                        <button className="btn" onClick={loadLogs}
                            style={{ borderRadius: 20, padding: '6px 14px', fontSize: '0.78em' }}>
                            <RefreshCw size={12} /> Refresh
                        </button>
                        <button className="btn" onClick={exportLogs} disabled={logs.length === 0}
                            style={{ borderRadius: 20, padding: '6px 14px', fontSize: '0.78em' }}>
                            <Download size={12} /> Export
                        </button>
                        <button className="btn" onClick={clearLogs} disabled={loading}
                            style={{
                                borderRadius: 20, padding: '6px 14px', fontSize: '0.78em',
                                borderColor: 'rgba(239,68,68,0.3)', color: '#EF4444',
                            }}>
                            <Trash2 size={12} /> Clear
                        </button>
                    </div>
                </div>
            </div>

            {/* ═══ TERMINAL ═══ */}
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                {/* Terminal header */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '10px 16px',
                    borderBottom: '1px solid var(--border-default)',
                    background: 'rgba(0,0,0,0.2)',
                }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#EF4444', opacity: 0.7 }} />
                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#F59E0B', opacity: 0.7 }} />
                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#10B981', opacity: 0.7 }} />
                    </div>
                    <span style={{ fontSize: '0.72em', fontWeight: 600, color: 'var(--text-muted)', letterSpacing: 1, marginLeft: 8 }}>
                        LEOMAIL — LIVE LOG STREAM
                    </span>
                    <span style={{ fontSize: '0.68em', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                        {logs.length} / {total} lines
                    </span>
                </div>

                {/* Terminal body */}
                <div ref={termRef} style={{
                    maxHeight: 520, minHeight: 400, overflow: 'auto',
                    fontFamily: 'JetBrains Mono, Consolas, monospace', fontSize: '0.75em',
                    lineHeight: 1.8, padding: '8px 0',
                    background: 'rgba(0,0,0,0.15)',
                }}>
                    {logs.length === 0 ? (
                        <div style={{ opacity: 0.3, textAlign: 'center', paddingTop: 140, fontSize: '1.1em' }}>
                            <TermIcon size={32} style={{ marginBottom: 12, opacity: 0.5 }} /><br />
                            No logs yet. Start a task to see output here.
                        </div>
                    ) : logs.map((line, i) => {
                        const level = parseLevel(line);
                        return (
                            <div key={i} style={{
                                borderLeft: `3px solid ${LEVEL_COLORS[level] || 'var(--text-muted)'}`,
                                paddingLeft: 14,
                                paddingRight: 16,
                                paddingTop: 1,
                                paddingBottom: 1,
                                marginBottom: 0,
                                color: level === 'ERROR' || level === 'CRITICAL' ? LEVEL_COLORS[level] : 'var(--text-secondary)',
                                fontWeight: level === 'ERROR' || level === 'CRITICAL' ? 600 : 400,
                                background: level === 'ERROR' || level === 'CRITICAL' ? 'rgba(239,68,68,0.04)' :
                                    level === 'WARNING' ? 'rgba(245,158,11,0.02)' : 'transparent',
                                transition: 'background 0.15s',
                            }}
                                onMouseEnter={e => e.currentTarget.style.background = 'rgba(255,255,255,0.02)'}
                                onMouseLeave={e => e.currentTarget.style.background =
                                    level === 'ERROR' || level === 'CRITICAL' ? 'rgba(239,68,68,0.04)' :
                                        level === 'WARNING' ? 'rgba(245,158,11,0.02)' : 'transparent'}
                            >
                                {line}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
