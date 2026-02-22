import React, { useState, useEffect, useRef } from 'react';
import { Terminal as TermIcon, Trash2, RefreshCw, Filter, Download } from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

const API = 'http://localhost:8000/api';

const LEVEL_COLORS = {
    INFO: 'var(--success)',
    WARNING: 'var(--warning)',
    ERROR: 'var(--danger)',
    DEBUG: 'var(--text-muted)',
    CRITICAL: '#ff3333',
};

function parseLevel(line) {
    for (const lvl of ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']) {
        if (line.includes(`| ${lvl}`)) return lvl;
    }
    return 'INFO';
}

export default function Logs() {
    const { t } = useI18n();
    const [logs, setLogs] = useState([]);
    const [total, setTotal] = useState(0);
    const [filter, setFilter] = useState('ALL');
    const [autoScroll, setAutoScroll] = useState(true);
    const [loading, setLoading] = useState(false);
    const termRef = useRef(null);
    const intervalRef = useRef(null);

    const loadLogs = async () => {
        try {
            const url = filter === 'ALL'
                ? `${API}/logs/?lines=200`
                : `${API}/logs/?lines=200&level=${filter}`;
            const res = await fetch(url);
            const data = await res.json();
            setLogs(data.logs || []);
            setTotal(data.total || 0);
        } catch { }
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

    const filters = ['ALL', 'INFO', 'WARNING', 'ERROR'];

    return (
        <div className="page">
            <h2 className="page-title"><TermIcon size={22} /> {t('logsTitle') || 'System Logs'}</h2>

            <div className="card" style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                        {filters.map(f => (
                            <button key={f} className={`btn btn-sm ${filter === f ? 'btn-primary' : ''}`}
                                onClick={() => setFilter(f)}
                                style={filter === f ? {} : { opacity: 0.6 }}>
                                <Filter size={11} /> {f}
                            </button>
                        ))}
                    </div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                        <span style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>
                            {total} total lines
                        </span>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.78em', cursor: 'pointer' }}>
                            <input type="checkbox" checked={autoScroll} onChange={e => setAutoScroll(e.target.checked)} />
                            Auto-scroll
                        </label>
                        <button className="btn btn-sm" onClick={loadLogs}><RefreshCw size={13} /></button>
                        <button className="btn btn-sm" onClick={exportLogs} disabled={logs.length === 0}
                            title="Экспорт в TXT">
                            <Download size={13} /> TXT
                        </button>
                        <button className="btn btn-sm btn-danger" onClick={clearLogs} disabled={loading}>
                            <Trash2 size={13} /> Clear
                        </button>
                    </div>
                </div>
            </div>

            <div className="card">
                <div ref={termRef} className="terminal" style={{
                    maxHeight: 520, minHeight: 400, overflow: 'auto',
                    fontFamily: 'JetBrains Mono, Consolas, monospace', fontSize: '0.75em',
                    lineHeight: 1.7, padding: '12px 16px',
                }}>
                    {logs.length === 0 ? (
                        <div style={{ opacity: 0.4, textAlign: 'center', paddingTop: 120 }}>
                            {t('noLogs') || 'No logs yet. Start a task to see output here.'}
                        </div>
                    ) : logs.map((line, i) => {
                        const level = parseLevel(line);
                        return (
                            <div key={i} className="log-line" style={{
                                borderLeft: `3px solid ${LEVEL_COLORS[level] || 'var(--text-muted)'}`,
                                paddingLeft: 10,
                                marginBottom: 1,
                                color: level === 'ERROR' || level === 'CRITICAL' ? LEVEL_COLORS[level] : 'var(--text-secondary)',
                                fontWeight: level === 'ERROR' ? 600 : 400,
                            }}>
                                {line}
                            </div>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
