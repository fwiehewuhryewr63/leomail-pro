import React, { useState, useEffect, useRef, useCallback } from 'react';
import { API } from '../api';
import { ProviderLogo } from '../components/ProviderLogos';


const TASK_TYPE_LABELS = { birth: 'Autoreg', warmup: 'Warmup', work: 'Mailing' };

function getStatusStyle(status, action) {
    if (status === 'done') return { color: '#10B981', icon: '✓' };
    if (status === 'error') return { color: '#EF4444', icon: '✗' };
    if (status === 'running') {
        if (action?.toLowerCase().includes('sms')) return { color: '#06B6D4', icon: '↔' };
        if (action?.toLowerCase().includes('captcha')) return { color: '#F59E0B', icon: '🛡' };
        return { color: '#06B6D4', icon: '↻' };
    }
    return { color: '#6B7280', icon: '⏳' };
}

function formatTime(startTime) {
    if (!startTime) return '';
    const diff = Math.max(0, Math.floor((Date.now() - new Date(startTime).getTime()) / 1000));
    if (diff > 86400) return `${Math.floor(diff / 86400)}d`;
    const m = Math.floor(diff / 60), s = diff % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function maskProxy(proxy) {
    if (!proxy || proxy === 'No proxy') return '';
    const host = proxy.split(':')[0];
    const parts = host.split('.');
    if (parts.length === 4) return `${parts[0]}.${parts[1]}.*.*`;
    return host.substring(0, 10) + '…';
}

// Clean up action text: remove "Thread N:" prefix
function cleanAction(action) {
    if (!action) return '';
    return action.replace(/^\u041f\u043e\u0442\u043e\u043a\s*\d+:\s*/i, '').trim();
}


export default function Threads() {
    const [threads, setThreads] = useState([]);
    const [selectedThread, setSelectedThread] = useState(null);
    const [screenshotUrl, setScreenshotUrl] = useState(null);
    const [screenshotError, setScreenshotError] = useState(false);
    const [activePages, setActivePages] = useState([]);
    const [showHistory, setShowHistory] = useState(false);
    const [expandedGroups, setExpandedGroups] = useState({}); // task_id -> bool
    const screenshotTimerRef = useRef(null);

    const load = useCallback(() => {
        fetch(`${API}/resources/active-threads`).then(r => r.json())
            .then(d => setThreads(Array.isArray(d) ? d : [])).catch(() => { });
        fetch(`${API}/birth/active-pages`).then(r => r.json())
            .then(d => setActivePages(d.active || [])).catch(() => { });
    }, []);

    useEffect(() => { load(); const iv = setInterval(load, 3000); return () => clearInterval(iv); }, [load]);

    // Screenshot polling
    useEffect(() => {
        if (screenshotTimerRef.current) clearInterval(screenshotTimerRef.current);
        if (selectedThread && activePages.includes(selectedThread)) {
            const fetchSS = () => {
                fetch(`${API}/birth/screenshot/${selectedThread}`)
                    .then(r => { if (r.ok && r.headers.get('content-type')?.includes('image')) return r.blob(); throw 0; })
                    .then(blob => { setScreenshotUrl(URL.createObjectURL(blob)); setScreenshotError(false); })
                    .catch(() => setScreenshotError(true));
            };
            fetchSS();
            screenshotTimerRef.current = setInterval(fetchSS, 2000);
        } else { setScreenshotUrl(null); setScreenshotError(false); }
        return () => { if (screenshotTimerRef.current) clearInterval(screenshotTimerRef.current); };
    }, [selectedThread, activePages]);

    // ── Separate active from history ──
    const activeThreads = threads.filter(t => t.status === 'running');
    const doneThreads = threads.filter(t => t.status !== 'running');

    // ── Group active by task ──
    const activeGroups = {};
    activeThreads.forEach(t => {
        const key = t.task_id || 0;
        if (!activeGroups[key]) activeGroups[key] = { task_id: key, task_type: t.task_type || 'birth', provider: t.provider || '', threads: [] };
        activeGroups[key].threads.push(t);
    });
    const sortedActiveGroups = Object.values(activeGroups).sort((a, b) => b.task_id - a.task_id);

    // ── Group history by task (collapsed by default) ──
    const historyGroups = {};
    doneThreads.forEach(t => {
        const key = t.task_id || 0;
        if (!historyGroups[key]) historyGroups[key] = { task_id: key, task_type: t.task_type || 'birth', provider: t.provider || '', threads: [] };
        historyGroups[key].threads.push(t);
    });
    const sortedHistoryGroups = Object.values(historyGroups).sort((a, b) => b.task_id - a.task_id);

    // Stats (active only)
    const running = activeThreads.length;
    const done = doneThreads.filter(t => t.status === 'done').length;
    const failed = doneThreads.filter(t => t.status === 'error').length;

    const hasPreview = selectedThread && activePages.includes(selectedThread);

    const clearThreads = () => { setThreads([]); setSelectedThread(null); };

    // ── Render a thread row ──
    const renderThread = (t, i) => {
        const si = getStatusStyle(t.status, t.action);
        const isLive = activePages.includes(t.id);
        const isSelected = selectedThread === t.id;
        const action = cleanAction(t.action);

        return (
            <div
                key={t.id || i}
                onClick={() => isLive && setSelectedThread(isSelected ? null : t.id)}
                style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '7px 14px 7px 20px',
                    cursor: isLive ? 'pointer' : 'default',
                    background: isSelected ? 'rgba(6,182,212,0.08)' : 'transparent',
                    borderLeft: `2px solid ${isSelected ? '#06B6D4' : 'transparent'}`,
                    transition: 'background 0.15s',
                }}
            >
                {/* # */}
                <span style={{
                    width: 22, height: 22, borderRadius: '50%',
                    border: `1.5px solid ${si.color}55`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontWeight: 800, fontSize: '0.65em', color: si.color, flexShrink: 0,
                }}>
                    {(t.index ?? i) + 1}
                </span>

                {/* Provider */}
                <ProviderLogo provider={t.provider || 'mail'} size={20} />

                {/* Email */}
                <span style={{
                    width: 180, flexShrink: 0,
                    fontSize: '0.82em', fontWeight: 500, color: 'var(--text-primary)',
                    fontFamily: 'monospace',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                    {t.email || '—'}
                </span>

                {/* Action */}
                <span style={{
                    flex: 1, minWidth: 0,
                    fontSize: '0.75em', color: si.color, fontWeight: 600,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                    {action || (t.status === 'error' ? (t.error || 'Error') : t.status === 'done' ? 'Done ✓' : '...')}
                </span>

                {/* Proxy */}
                <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', fontFamily: 'monospace', flexShrink: 0 }}>
                    {maskProxy(t.proxy)}
                </span>

                {/* Time */}
                <span style={{ fontSize: '0.75em', color: 'var(--text-muted)', fontFamily: 'monospace', flexShrink: 0, minWidth: 36, textAlign: 'right' }}>
                    {formatTime(t.started || t.updated)}
                </span>

                {/* Live dot */}
                {isLive && <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#10B981', boxShadow: '0 0 4px #10B981', flexShrink: 0 }} />}
            </div>
        );
    };

    // ── Render task group ──
    const renderGroup = (group, isHistory = false) => {
        const groupRunning = group.threads.filter(t => t.status === 'running').length;
        const groupDone = group.threads.filter(t => t.status === 'done').length;
        const groupFailed = group.threads.filter(t => t.status === 'error').length;
        const providerName = group.provider ? group.provider.charAt(0).toUpperCase() + group.provider.slice(1) : '';
        const taskLabel = TASK_TYPE_LABELS[group.task_type] || group.task_type;
        const isExpanded = isHistory ? (expandedGroups[group.task_id] ?? false) : true;

        const toggleExpand = () => {
            if (isHistory) {
                setExpandedGroups(prev => ({ ...prev, [group.task_id]: !prev[group.task_id] }));
            }
        };

        // Overall group status for history
        const groupStatus = groupDone > 0 && groupFailed === 0 ? 'done' : groupFailed > 0 && groupDone === 0 ? 'error' : groupFailed > 0 ? 'partial' : 'stopped';
        const statusColor = groupStatus === 'done' ? '#10B981' : groupStatus === 'error' ? '#EF4444' : groupStatus === 'partial' ? '#F59E0B' : 'var(--text-muted)';
        const statusLabel = groupStatus === 'done' ? 'Done' : groupStatus === 'error' ? 'Failed' : groupStatus === 'partial' ? 'Partial' : 'Stopped';

        return (
            <div key={group.task_id} style={{
                background: 'var(--bg-card)', borderRadius: 8,
                border: `1px solid ${groupRunning > 0 ? '#06B6D422' : 'var(--border-default)'}`,
                overflow: 'hidden',
            }}>
                {/* Header */}
                <div
                    onClick={toggleExpand}
                    style={{
                        padding: '8px 14px',
                        display: 'flex', alignItems: 'center', gap: 8,
                        background: groupRunning > 0 ? 'rgba(6,182,212,0.03)' : 'transparent',
                        borderBottom: isExpanded ? '1px solid var(--border-default)' : 'none',
                        fontSize: '0.82em',
                        cursor: isHistory ? 'pointer' : 'default',
                        userSelect: 'none',
                    }}
                >
                    <ProviderLogo provider={group.provider || ''} size={20} />
                    <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>#{group.task_id}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{taskLabel} {providerName} × {group.threads.length}</span>
                    <div style={{ flex: 1 }} />
                    {isHistory && !groupRunning && (
                        <span style={{ fontSize: '0.85em', fontWeight: 700, color: statusColor }}>{statusLabel}</span>
                    )}
                    <div style={{ display: 'flex', gap: 6, fontSize: '0.9em', fontWeight: 700 }}>
                        {groupDone > 0 && <span style={{ color: '#10B981' }}>{groupDone}✓</span>}
                        {groupFailed > 0 && <span style={{ color: '#EF4444' }}>{groupFailed}✗</span>}
                        {groupRunning > 0 && <span style={{ color: '#06B6D4' }}>{groupRunning}↻</span>}
                    </div>
                    {groupRunning > 0 && <span style={{
                        width: 7, height: 7, borderRadius: '50%', background: '#06B6D4',
                        boxShadow: '0 0 6px #06B6D4', animation: 'pulse 1.5s infinite',
                    }} />}
                    {isHistory && <span style={{ fontSize: '0.75em', color: 'var(--text-muted)' }}>{isExpanded ? '▾' : '▸'}</span>}
                </div>

                {/* Threads (collapsible for history) */}
                {isExpanded && <div>{group.threads.map((t, i) => renderThread(t, i))}</div>}
            </div>
        );
    };

    return (
        <div className="page" style={{ display: 'flex', gap: 16, height: 'calc(100vh - 100px)' }}>
            {/* Left: Thread list */}
            <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
                {/* Header */}
                <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                        <div className="page-breadcrumb">MONITORING / THREADS</div>
                        <h2 className="page-title">
                            Threads
                            {running > 0 && (
                                <span className="active-badge">
                                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10B981', boxShadow: '0 0 5px #10B981', animation: 'pulse 1.5s infinite' }} />
                                    {running} active
                                </span>
                            )}
                        </h2>
                    </div>
                    <button className="btn" onClick={clearThreads} style={{ padding: '4px 12px', fontSize: '0.78em', fontWeight: 600, border: '1px solid var(--border-default)', background: 'transparent' }}>
                        Clear
                    </button>
                </div>

                {/* Stats — only show when threads are active */}
                {running > 0 && (
                    <div className="engine-status-bar">
                        <span style={{ color: '#10B981', fontWeight: 700 }}>{done} ✓</span>
                        <span style={{ color: 'var(--text-muted)' }}>·</span>
                        <span style={{ color: '#EF4444', fontWeight: 700 }}>{failed} ✗</span>
                        <span style={{ color: 'var(--text-muted)' }}>·</span>
                        <span style={{ color: '#06B6D4', fontWeight: 700 }}>{running} ↻</span>
                    </div>
                )}

                {/* Active groups */}
                <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {sortedActiveGroups.length === 0 && !showHistory && (
                        <div className="card" style={{ textAlign: 'center', padding: 50, color: 'var(--text-muted)' }}>
                            <div style={{ fontSize: '2em', marginBottom: 6 }}>⊘</div>
                            <div style={{ fontSize: '0.9em' }}>No active threads</div>
                            <div style={{ fontSize: '0.75em', marginTop: 3, opacity: 0.5 }}>Start autoreg to begin tracking</div>
                        </div>
                    )}
                    {sortedActiveGroups.map(g => renderGroup(g))}

                    {/* — History separator — */}
                    {sortedHistoryGroups.length > 0 && (
                        <>
                            <div
                                onClick={() => setShowHistory(!showHistory)}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: 8,
                                    padding: '8px 14px', cursor: 'pointer',
                                    color: 'var(--text-muted)', fontSize: '0.8em',
                                    userSelect: 'none', marginTop: 4,
                                }}
                            >
                                <div style={{ flex: 1, height: 1, background: 'var(--border-default)' }} />
                                <span style={{ fontWeight: 600 }}>
                                    {showHistory ? '▾' : '▸'} History ({doneThreads.length})
                                </span>
                                <div style={{ flex: 1, height: 1, background: 'var(--border-default)' }} />
                            </div>

                            {showHistory && sortedHistoryGroups.map(g => renderGroup(g, true))}
                        </>
                    )}
                </div>
            </div>

            {/* Right: Live Preview */}
            {hasPreview && (
                <div style={{ width: 400, flexShrink: 0, display: 'flex', flexDirection: 'column' }}>
                    <div className="card" style={{ padding: 10, display: 'flex', flexDirection: 'column', gap: 6, flex: 1 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.85em', color: 'var(--text-primary)' }}>🖥 Live Preview</span>
                            <span style={{ fontSize: '0.7em', color: 'var(--text-muted)' }}>#{selectedThread} · 2s</span>
                        </div>
                        <div style={{
                            flex: 1, borderRadius: 6, overflow: 'hidden',
                            background: '#080808', border: '1px solid var(--border-default)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            minHeight: 280,
                        }}>
                            {screenshotError ? (
                                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.8em' }}>
                                    <div style={{ fontSize: '1.3em', marginBottom: 4 }}>📷</div>
                                    Browser closed
                                </div>
                            ) : screenshotUrl ? (
                                <img src={screenshotUrl} alt="Browser" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                            ) : (
                                <span style={{ color: 'var(--text-muted)', fontSize: '0.8em' }}>Loading...</span>
                            )}
                        </div>
                        <button className="btn" onClick={() => { setSelectedThread(null); setScreenshotUrl(null); }}
                            style={{ padding: '4px 12px', fontSize: '0.75em', border: '1px solid var(--border-default)', background: 'transparent', alignSelf: 'flex-end' }}>
                            Close
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}
