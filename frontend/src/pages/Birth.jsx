import React, { useState, useEffect } from 'react';
import {
    Play, StopCircle, RefreshCw, CheckCircle, XCircle, Circle
} from 'lucide-react';
import { API } from '../api';
import { ProviderLogo } from '../components/ProviderLogos';

/* ── Provider definitions ── */
const PROVIDERS = [
    { id: 'gmail', name: 'Gmail', color: '#EA4335', sms: 'simsms' },
    { id: 'yahoo', name: 'Yahoo', color: '#6001D2', sms: 'simsms' },
    { id: 'aol', name: 'AOL', color: '#FF6B00', sms: 'simsms' },
    { id: 'outlook', name: 'Outlook', color: '#0078D4', sms: 'simsms' },
    { id: 'hotmail', name: 'Hotmail', color: '#0078D4', sms: 'simsms' },
    { id: 'protonmail', name: 'ProtonMail', color: '#6D4AFF', noSms: true },
];





export default function Birth() {
    const [provider, setProvider] = useState('outlook');
    const [quantity, setQuantity] = useState(25);
    const [threads, setThreads] = useState(5);
    const [_farmName, _setFarmName] = useState('');
    const [running, setRunning] = useState(false);
    const [runningProvider, setRunningProvider] = useState(null); // actual provider of running task
    const [result, setResult] = useState(null);
    const [namePacks, setNamePacks] = useState([]);
    const [selectedNamePacks, setSelectedNamePacks] = useState([]);
    const [packsOpen, setPacksOpen] = useState(false);
    const [stopModal, setStopModal] = useState(false);

    /* ── Progress state ── */
    const [progress, setProgress] = useState(null); // null = not loaded yet
    const [threadLogs, setThreadLogs] = useState([]);

    useEffect(() => {
        fetch(`${API}/resources/batch`).then(r => r.json()).then(d => {
            setNamePacks(Array.isArray(d.name_packs) ? d.name_packs : []);
        }).catch(() => { /* ignore */ });
        // Check if autoreg is ACTUALLY running (engine status, not stale task record)
        fetch(`${API}/engine/status`).then(r => r.json()).then(d => {
            if (d.autoreg?.status === 'running') {
                setRunning(true);
                setResult({ status: 'running', message: 'Running...' });
            }
        }).catch(() => { /* ignore */ });
        // Fetch birth status — only show if task is actually running (not stale finished task)
        fetch(`${API}/birth/status`).then(r => r.json()).then(d => {
            if (d.running) {
                setRunning(true);
                setProgress({
                    completed: d.completed || 0, total: d.total || 0,
                    failed: d.failed || 0, retrying: d.retrying || 0,
                    queued: Math.max(0, (d.total || 0) - (d.completed || 0) - (d.failed || 0) - (d.retrying || 0)),
                });
                if (d.provider) setRunningProvider(d.provider);
                setResult({ status: 'running', message: 'Running...' });
            }
            // If not running, leave progress as null → shows clean "Press START"
        }).catch(() => { /* leave progress null */ });
    }, []);


    const startBirth = () => {
        setRunning(true);
        setRunningProvider(provider); // track which provider is actually running
        setResult(null);
        setProgress({ completed: 0, total: parseInt(quantity) || 0, failed: 0, retrying: 0, queued: parseInt(quantity) || 0 });
        fetch(`${API}/birth/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider,
                quantity: parseInt(quantity) || 1,
                name_pack_ids: selectedNamePacks,
                sms_provider: 'auto',
                threads: parseInt(threads) || 1,
                farm_name: _farmName,
            })
        }).then(r => r.json()).then(setResult).catch(() => {
            setResult({ status: 'error', message: 'Failed to start' });
            setRunning(false);
        });
    };

    const stopBirth = (mode) => {
        fetch(`${API}/birth/stop?mode=${mode}`, { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                setRunning(false);
                setRunningProvider(null);
                setStopModal(false);
                setResult({
                    status: 'stopped',
                    message: mode === 'instant'
                        ? `⛔ Stopped: ${d.stopped} tasks killed`
                        : `Graceful stop: waiting for ${d.stopped} tasks`
                });
            })
            .catch(() => { setRunning(false); setRunningProvider(null); setStopModal(false); });
    };

    /* Poll status */
    useEffect(() => {
        if (!running) return;
        const iv = setInterval(() => {
            fetch(`${API}/birth/status`)
                .then(r => r.json())
                .then(d => {
                    setProgress({
                        completed: d.completed || 0, total: d.total || 0,
                        failed: d.failed || 0, retrying: d.retrying || 0,
                        queued: Math.max(0, (d.total || 0) - (d.completed || 0) - (d.failed || 0) - (d.retrying || 0)),
                    });
                    // Get real thread logs if available
                    if (Array.isArray(d.thread_logs)) {
                        setThreadLogs(d.thread_logs);
                    }
                    if (d.provider) setRunningProvider(d.provider);
                    if (!d.running) {
                        setRunning(false);
                        setRunningProvider(null);
                        setResult({
                            status: d.status === 'failed' ? 'error' : 'completed',
                            message: `${d.status === 'failed' ? '⛔' : '✅'} Done: ${d.completed}/${d.total}, errors: ${d.failed}`
                        });
                    }
                }).catch(() => { });
        }, 3000);
        return () => clearInterval(iv);
    }, [running]);

    const safeProgress = progress || { completed: 0, total: 0, failed: 0, retrying: 0, queued: 0 };
    const pct = safeProgress.total > 0 ? Math.round(safeProgress.completed / safeProgress.total * 100) : 0;
    const displayProvider = runningProvider || provider; // use actual running provider for display

    return (
        <div className="page">
            {/* Header */}
            <div style={{ fontSize: '0.65em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 2 }}>AUTOREG</div>
            <h2 className="page-title" style={{ margin: '0 0 20px', borderBottom: '2px solid var(--accent)', paddingBottom: 8, display: 'inline-block' }}>Autoreg</h2>

            {/* ═══════════════ Config Section ═══════════════ */}
            <div className="card" style={{ padding: '20px 24px', marginBottom: 16 }}>
                <div style={{ fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 14 }}>Config</div>

                {/* ── Provider Cards ── */}
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${PROVIDERS.length}, 1fr)`, gap: 10, marginBottom: 24 }}>
                    {PROVIDERS.map(p => {
                        const active = provider === p.id;
                        return (
                            <div key={p.id} onClick={() => setProvider(p.id)} style={{
                                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                                gap: 8, padding: '16px 8px', borderRadius: 12, cursor: 'pointer',
                                background: active ? `${p.color}18` : 'rgba(255,255,255,0.02)',
                                border: `2px solid ${active ? p.color : 'rgba(255,255,255,0.06)'}`,
                                transition: 'all 0.2s', position: 'relative',
                                boxShadow: active ? `0 0 20px ${p.color}15, inset 0 0 15px ${p.color}08` : 'none',
                            }}>
                                {/* Checkmark */}
                                {active && (
                                    <div style={{
                                        position: 'absolute', top: 6, right: 6,
                                        width: 18, height: 18, borderRadius: '50%',
                                        background: 'var(--accent)', display: 'flex',
                                        alignItems: 'center', justifyContent: 'center',
                                    }}>
                                        <span style={{ color: '#000', fontSize: '0.7em', fontWeight: 900 }}>✓</span>
                                    </div>
                                )}
                                {/* Icon */}
                                <ProviderLogo provider={p.id} size={64} />
                                <span style={{
                                    fontSize: '0.78em', fontWeight: 700, color: active ? '#fff' : 'var(--text-muted)',
                                    letterSpacing: 0.3,
                                }}>{p.name}</span>
                            </div>
                        );
                    })}
                </div>

                {/* ── Farm + Quantity row ── */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 14 }}>
                    <div>
                        <label style={labelStyle}>Farm</label>
                        <input className="form-input" type="text" placeholder="Auto-create new farm" value={_farmName}
                            onChange={e => _setFarmName(e.target.value)}
                            style={{ fontSize: '1.05em', padding: '10px 14px' }} />
                    </div>
                    <div>
                        <label style={labelStyle}>Quantity</label>
                        <input className="form-input" type="text" inputMode="numeric" value={quantity}
                            style={{ fontSize: '1.05em', padding: '10px 14px' }}
                            onFocus={e => e.target.select()}
                            onChange={e => { const v = e.target.value.replace(/\D/g, ''); setQuantity(v === '' ? '' : v); }}
                            onBlur={e => setQuantity(Math.max(1, parseInt(e.target.value) || 1))} />
                    </div>
                </div>

                {/* ── Threads + Name Pack row ── */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 20 }}>
                    <div>
                        <label style={labelStyle}>Threads</label>
                        <input className="form-input" type="text" inputMode="numeric" value={threads}
                            style={{ fontSize: '1.05em', padding: '10px 14px' }}
                            onFocus={e => e.target.select()}
                            onChange={e => { const v = e.target.value.replace(/\D/g, ''); setThreads(v === '' ? '' : v); }}
                            onBlur={e => setThreads(Math.min(50, Math.max(1, parseInt(e.target.value) || 1)))} />
                    </div>
                    <div>
                        <label style={labelStyle}>Name Pack</label>
                        <div className="form-input" onClick={() => setPacksOpen(!packsOpen)}
                            style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px' }}>
                            <span>{selectedNamePacks.length > 0 ? `${selectedNamePacks.length} selected` : 'Select...'}</span>
                            <span style={{ fontSize: '0.8em', color: 'var(--text-muted)' }}>{packsOpen ? '▲' : '▼'}</span>
                        </div>
                        {packsOpen && (
                            <div style={{
                                marginTop: 4, background: 'var(--bg-card)', border: '1px solid var(--border-default)',
                                borderRadius: 8, maxHeight: 200, overflowY: 'auto', padding: 6,
                            }}>
                                {namePacks.length === 0 ? (
                                    <div style={{ fontSize: '0.82em', color: 'var(--text-muted)', padding: 8 }}>No packs — upload in Names</div>
                                ) : namePacks.map(np => (
                                    <div key={np.id} onClick={() => setSelectedNamePacks(prev =>
                                        prev.includes(np.id) ? prev.filter(x => x !== np.id) : [...prev, np.id]
                                    )} style={{
                                        padding: '6px 10px', borderRadius: 6, cursor: 'pointer', fontSize: '0.85em',
                                        background: selectedNamePacks.includes(np.id) ? 'rgba(16,185,129,0.12)' : 'transparent',
                                        color: selectedNamePacks.includes(np.id) ? 'var(--accent)' : 'var(--text-secondary)',
                                        fontWeight: selectedNamePacks.includes(np.id) ? 600 : 400,
                                        display: 'flex', justifyContent: 'space-between',
                                    }}>
                                        <span>{np.name}</span>
                                        <span style={{ opacity: 0.5 }}>{np.total_count}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

                {/* ── Buttons: START / STOP ── */}

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <button onClick={startBirth} disabled={running}
                        style={{
                            padding: '14px 24px', fontSize: '1em', fontWeight: 800, cursor: running ? 'not-allowed' : 'pointer',
                            background: running ? 'rgba(16,185,129,0.15)' : 'var(--accent)', color: running ? 'var(--accent)' : '#000',
                            border: 'none', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                            fontFamily: 'inherit', transition: 'all 0.2s',
                        }}>
                        <Play size={16} /> START
                    </button>
                    <button onClick={() => running ? setStopModal(true) : null} disabled={!running}
                        style={{
                            padding: '14px 24px', fontSize: '1em', fontWeight: 800, cursor: !running ? 'not-allowed' : 'pointer',
                            background: 'transparent', color: !running ? 'var(--text-muted)' : 'var(--danger)',
                            border: `2px solid ${!running ? 'rgba(255,255,255,0.08)' : 'var(--danger)'}`,
                            borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                            fontFamily: 'inherit', transition: 'all 0.2s',
                        }}>
                        <StopCircle size={16} /> STOP
                    </button>
                </div>
            </div>

            {/* ═══════════════ Progress Section ═══════════════ */}
            <div className="card" style={{ padding: '16px 24px', marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <span style={{ fontSize: '0.82em', fontWeight: 600, color: 'var(--text-secondary)' }}>Progress</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.82em' }}>
                        <span style={{ color: 'var(--text-muted)' }}>{safeProgress.completed} / {safeProgress.total} ({pct}%)</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--success)' }}><CheckCircle size={12} /> {safeProgress.completed}</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--danger)' }}><XCircle size={12} /> {safeProgress.failed}</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--warning)' }}><RefreshCw size={12} /> {safeProgress.retrying}</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--text-muted)' }}><Circle size={12} /> {safeProgress.queued}</span>
                    </div>
                </div>
                <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${pct}%` }} />
                </div>
            </div>

            {/* ═══════════════ Thread Monitor ═══════════════ */}
            <div className="card" style={{ padding: '16px 24px' }}>
                <div style={{ fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 12 }}>Thread monitor</div>

                {!running && safeProgress.total === 0 ? (
                    <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)', fontSize: '0.85em' }}>
                        Press START to begin registration
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {Array.from({ length: Math.min(safeProgress.total || parseInt(threads) || 1, 10) }, (_, i) => {
                            const tIdx = i + 1;
                            const isActive = running && i < (safeProgress.completed + safeProgress.failed + safeProgress.retrying);
                            const isDone = i < safeProgress.completed;
                            const isFailed = i >= safeProgress.completed && i < safeProgress.completed + safeProgress.failed;
                            const isRetrying = i >= safeProgress.completed + safeProgress.failed && i < safeProgress.completed + safeProgress.failed + safeProgress.retrying;

                            const statusIcon = isDone ? <CheckCircle size={14} style={{ color: 'var(--success)' }} />
                                : isFailed ? <XCircle size={14} style={{ color: 'var(--danger)' }} />
                                    : isRetrying ? <RefreshCw size={14} style={{ color: 'var(--warning)' }} />
                                        : <Circle size={14} style={{ color: 'var(--text-muted)' }} />;

                            // Use real thread log data if available
                            const tLog = threadLogs[i];
                            const statusText = tLog?.status === 'completed' ? (tLog.email || 'Registered ✓')
                                : tLog?.status === 'error' ? (tLog.error_message || 'Failed')
                                    : tLog?.status === 'running' ? (tLog.current_step || 'Working...')
                                        : isDone ? 'Registered ✓'
                                            : isFailed ? 'Failed'
                                                : isRetrying ? 'Retrying...'
                                                    : 'Queued';

                            const statusColor = isDone ? 'var(--success)' : isFailed ? 'var(--danger)' : isRetrying ? 'var(--warning)' : 'var(--text-muted)';

                            return (
                                <div key={tIdx} style={{
                                    display: 'grid', gridTemplateColumns: '70px 40px 1fr 130px 70px',
                                    alignItems: 'center', gap: 8,
                                    padding: '10px 14px', borderRadius: 8,
                                    background: isDone ? 'rgba(16,185,129,0.04)'
                                        : isFailed ? 'rgba(239,68,68,0.04)'
                                            : isRetrying ? 'rgba(245,158,11,0.04)'
                                                : 'rgba(255,255,255,0.01)',
                                    borderLeft: isActive || isDone || isFailed || isRetrying ? `3px solid ${statusColor}` : '3px solid transparent',
                                }}>
                                    {/* Thread ID */}
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        {statusIcon}
                                        <span style={{ fontWeight: 700, fontSize: '0.85em' }}>T-{tIdx}</span>
                                    </div>

                                    {/* Provider logo */}
                                    <ProviderLogo provider={displayProvider} size={24} />

                                    {/* Email placeholder */}
                                    <span style={{ fontSize: '0.82em', color: isDone ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: isDone ? 500 : 400 }}>
                                        {isDone ? `user${tIdx}@${displayProvider}.com` : '—'}
                                    </span>

                                    {/* Status */}
                                    <span style={{ fontSize: '0.78em', color: statusColor, fontWeight: 600 }}>{statusText}</span>

                                    {/* Time */}
                                    <span style={{ fontSize: '0.75em', color: 'var(--text-muted)', textAlign: 'right' }}>
                                        {isActive || isDone || isFailed ? `${tIdx}m ${(tIdx * 17) % 59}s` : ''}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* ═══════════════ Result message ═══════════════ */}
            {result && !running && (
                <div className="card" style={{
                    marginTop: 16, padding: '14px 20px',
                    borderLeft: `3px solid ${result.status === 'error' || result.status === 'stopped' ? 'var(--danger)' : 'var(--success)'}`,
                }}>
                    <div style={{ fontSize: '0.95em', fontWeight: 700, color: result.status === 'error' || result.status === 'stopped' ? 'var(--danger)' : 'var(--success)' }}>
                        {result.message}
                    </div>
                </div>
            )}

            {/* ═══════════════ Stop Modal ═══════════════ */}
            {stopModal && (
                <div style={{
                    position: 'fixed', inset: 0, zIndex: 9999,
                    background: 'rgba(0,0,0,0.85)', display: 'flex',
                    alignItems: 'center', justifyContent: 'center',
                }} onClick={() => setStopModal(false)}>
                    <div className="card" style={{ maxWidth: 420, width: '90%', padding: 24 }} onClick={e => e.stopPropagation()}>
                        <div style={{ fontWeight: 800, fontSize: '1.1em', color: 'var(--danger)', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                            <StopCircle size={20} /> Stop registration?
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
                            <button className="btn" onClick={() => stopBirth('instant')}
                                style={{ padding: '14px 20px', background: 'var(--danger)', color: '#fff', fontWeight: 700, fontSize: '0.95em', border: 'none', borderRadius: 8 }}>
                                Instant — kill all threads now
                            </button>
                            <button className="btn" onClick={() => stopBirth('graceful')}
                                style={{ padding: '14px 20px', background: 'var(--warning)', color: '#000', fontWeight: 700, fontSize: '0.95em', border: 'none', borderRadius: 8 }}>
                                Wait for current threads to finish
                            </button>
                        </div>
                        <button className="btn" onClick={() => setStopModal(false)}
                            style={{ width: '100%', padding: 10, fontSize: '0.9em' }}>Cancel</button>
                    </div>
                </div>
            )}


        </div>
    );
}

/* ── Styles ── */
const labelStyle = {
    fontSize: '0.68em', fontWeight: 700, textTransform: 'uppercase',
    letterSpacing: 1, color: 'var(--text-muted)', marginBottom: 6, display: 'block',
};
