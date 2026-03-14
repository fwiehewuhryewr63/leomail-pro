import React, { useState, useEffect, useRef } from 'react';
import {
    Play, StopCircle, Upload, CheckCircle, XCircle, RefreshCw, Circle,
    FileText, AlertTriangle
} from 'lucide-react';
import { API } from '../api';
import { ProviderLogo } from '../components/ProviderLogos';

function normalizeCount(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function buildProgress(data = {}) {
    return {
        valid: normalizeCount(data.valid),
        invalid: normalizeCount(data.invalid),
        challenge: normalizeCount(data.challenge),
        skipped: normalizeCount(data.skipped),
        processing: normalizeCount(data.processing),
        total: normalizeCount(data.total),
    };
}

export default function Validator() {
    /* ── State ── */
    const [file, setFile] = useState(null);
    const [uploadResult, setUploadResult] = useState(null);
    const [threads, setThreads] = useState(5);
    const [skipExisting, setSkipExisting] = useState(true);
    const [saveSession, setSaveSession] = useState(true);
    const [farmName, setFarmName] = useState('');
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState(null);
    const [progress, setProgress] = useState(null);
    const [threadLogs, setThreadLogs] = useState([]);
    const [stopModal, setStopModal] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const fileInputRef = useRef(null);

    /* ── Check if validator is running on mount ── */
    useEffect(() => {
        fetch(`${API}/validator/status`).then(r => r.json()).then(d => {
            if (d.running) {
                setRunning(true);
                setUploadResult({ total: normalizeCount(d.total), filename: d.filename, format: d.format });
                setProgress(buildProgress(d));
                if (Array.isArray(d.thread_logs)) setThreadLogs(d.thread_logs);
            }
        }).catch(() => { });
    }, []);

    /* ── File Upload ── */
    const handleFileUpload = async (selectedFile) => {
        if (!selectedFile) return;
        setFile(selectedFile);
        setResult(null);

        const formData = new FormData();
        formData.append('file', selectedFile);

        try {
            const res = await fetch(`${API}/validator/upload`, { method: 'POST', body: formData });
            const data = await res.json();
            if (res.ok) {
                setResult(null);
                setUploadResult({ ...data, total: normalizeCount(data.total) });
                setProgress(null);
                setThreadLogs([]);
            } else {
                setResult({ status: 'error', message: data.detail || 'Upload failed' });
            }
        } catch (e) {
            setResult({ status: 'error', message: 'Upload failed: ' + e.message });
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        const f = e.dataTransfer.files[0];
        if (f) handleFileUpload(f);
    };

    /* ── Start / Stop ── */
    const startValidation = () => {
        setRunning(true);
        setResult(null);
        setProgress(buildProgress({ total: uploadResult?.total || 0 }));
        setThreadLogs([]);

        fetch(`${API}/validator/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                threads: parseInt(threads) || 5,
                skip_existing: skipExisting,
                save_session: saveSession,
                farm_name: farmName,
            })
        }).then(async r => {
            const data = await r.json().catch(() => ({}));
            if (!r.ok) {
                throw new Error(data.detail || data.message || 'Failed to start validation');
            }
            return data;
        }).then(d => {
            if (d.status === 'error') {
                setResult({ status: 'error', message: d.message });
                setRunning(false);
            } else {
                setResult(null);
            }
        }).catch((e) => {
            setResult({ status: 'error', message: e.message || 'Failed to start validation' });
            setRunning(false);
        });
    };

    const stopValidation = () => {
        fetch(`${API}/validator/stop`, { method: 'POST' })
            .then(r => r.json())
            .then(() => {
                setRunning(false);
                setStopModal(false);
                setResult({ status: 'stopped', message: 'Validation stopped by user' });
            })
            .catch(() => { setRunning(false); setStopModal(false); });
    };

    /* ── Poll ── */
    useEffect(() => {
        if (!running) return;
        const iv = setInterval(() => {
            fetch(`${API}/validator/status`).then(r => r.json()).then(d => {
                setProgress(buildProgress(d));
                if (Array.isArray(d.thread_logs)) setThreadLogs(d.thread_logs);
                if (!d.running) {
                    setRunning(false);
                    const valid = normalizeCount(d.valid);
                    const invalid = normalizeCount(d.invalid);
                    const challenge = normalizeCount(d.challenge);
                    const skipped = normalizeCount(d.skipped);
                    const parts = [`${valid} valid`, `${invalid} invalid`];
                    if (challenge) parts.push(`${challenge} challenge`);
                    if (skipped) parts.push(`${skipped} skipped`);
                    setResult({
                        status: 'completed',
                        message: `Done: ${parts.join(', ')}`
                    });
                }
            }).catch(() => { });
        }, 2000);
        return () => clearInterval(iv);
    }, [running]);

    const safeProgress = progress || buildProgress();
    const completed = safeProgress.valid + safeProgress.invalid + safeProgress.challenge + safeProgress.skipped;
    const pct = safeProgress.total > 0 ? Math.round(completed / safeProgress.total * 100) : 0;
    const queued = Math.max(0, safeProgress.total - completed - safeProgress.processing);

    return (
        <div className="page">
            {/* Header */}
            <div className="page-header">
                <div className="page-breadcrumb">VALIDATOR</div>
                <h2 className="page-title">Account Validator</h2>
                <div className="engine-hero-strip">
                    <div className="engine-hero-chip">
                        <span className="engine-hero-chip-label">Workflow</span>
                        <span className="engine-hero-chip-value">{running ? 'Checking live batch' : 'Upload and verify'}</span>
                    </div>
                    <div className="engine-hero-chip">
                        <span className="engine-hero-chip-label">Loaded</span>
                        <span className="engine-hero-chip-value">{uploadResult?.total || 0} accounts</span>
                    </div>
                    <div className="engine-hero-chip">
                        <span className="engine-hero-chip-label">Threads</span>
                        <span className="engine-hero-chip-value">{threads || 0} workers</span>
                    </div>
                    <div className="engine-hero-chip">
                        <span className="engine-hero-chip-label">Sessions</span>
                        <span className="engine-hero-chip-value">{saveSession ? 'Saved after login' : 'No session save'}</span>
                    </div>
                </div>
            </div>

            {/* ═══════════════ Upload Section ═══════════════ */}
            <div className="card engine-card">
                <div className="engine-section-head">
                    <div>
                        <div className="engine-section-kicker">Source batch</div>
                        <div className="card-section-header" style={{ marginBottom: 0 }}>Upload</div>
                    </div>
                    <div className="engine-section-caption">Bring in a clean file, preview the batch and keep the format obvious.</div>
                </div>

                <div className={`engine-panel-grid${uploadResult ? ' split' : ''}`} style={{ gridTemplateColumns: uploadResult ? undefined : '1fr' }}>
                    {/* Drop Zone */}
                    <div
                        onDrop={handleDrop}
                        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                        onDragLeave={() => setDragOver(false)}
                        onClick={() => fileInputRef.current?.click()}
                        className="engine-dropzone"
                        style={{
                            border: `2px dashed ${dragOver ? 'var(--teal)' : 'rgba(6, 182, 212, 0.25)'}`,
                            background: dragOver ? 'rgba(6, 182, 212, 0.06)' : 'rgba(6, 182, 212, 0.02)',
                            boxShadow: dragOver ? '0 0 20px rgba(6, 182, 212, 0.1)' : 'none',
                        }}>
                        <Upload size={40} style={{ color: 'var(--teal)', marginBottom: 12 }} />
                        <div style={{ fontWeight: 700, fontSize: '0.95em', marginBottom: 6 }}>
                            {file ? file.name : 'Drop file here or click to browse'}
                        </div>
                        <div style={{ fontSize: '0.75em', color: 'var(--text-muted)' }}>
                            email:password / email;password / email|password / optional recovery as third field / extra fields ignored
                        </div>
                        <input ref={fileInputRef} type="file" accept=".txt,.csv,.tsv" hidden
                            onChange={(e) => handleFileUpload(e.target.files[0])} />
                    </div>

                    {/* Stats */}
                    {uploadResult && (
                        <div className="engine-upload-stats">
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px', background: 'rgba(6, 182, 212, 0.06)', borderRadius: 10, border: '1px solid rgba(6, 182, 212, 0.15)' }}>
                                <FileText size={20} style={{ color: 'var(--teal)' }} />
                                <div>
                                    <div style={{ fontWeight: 700, fontSize: '0.88em' }}>{uploadResult.filename}</div>
                                    <div style={{ fontSize: '0.75em', color: 'var(--text-muted)' }}>File loaded</div>
                                </div>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                                <StatBox label="Accounts" value={uploadResult.total} color="var(--teal)" />
                                <StatBox label="Format" value={uploadResult.format || 'auto'} color="var(--indigo)" small />
                            </div>
                            {uploadResult.providers && (
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                    {Object.entries(uploadResult.providers).map(([p, count]) => (
                                        <div key={p} style={{
                                            display: 'flex', alignItems: 'center', gap: 6,
                                            padding: '4px 10px', borderRadius: 6,
                                            background: 'rgba(255,255,255,0.03)', fontSize: '0.78em',
                                            border: '1px solid rgba(255,255,255,0.06)',
                                        }}>
                                            <ProviderLogo provider={p} size={16} />
                                            <span style={{ fontWeight: 600 }}>{count}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* ═══════════════ Config Section ═══════════════ */}
            <div className="card engine-card">
                <div className="engine-section-head">
                    <div>
                        <div className="engine-section-kicker">Execution profile</div>
                        <div className="card-section-header" style={{ marginBottom: 0 }}>Config</div>
                    </div>
                    <div className="engine-section-caption">Control worker count, skip behavior and post-login session handling.</div>
                </div>

                <div className="config-row-2">
                    <div>
                        <label className="form-label">Farm</label>
                        <input className="form-input" type="text" placeholder="Auto-create new farm"
                            value={farmName} onChange={e => setFarmName(e.target.value)}
                            style={{ fontSize: '1.05em', padding: '10px 14px' }} />
                    </div>
                    <div>
                        <label className="form-label">Threads</label>
                        <input className="form-input" type="text" inputMode="numeric" value={threads}
                            style={{ fontSize: '1.05em', padding: '10px 14px' }}
                            onFocus={e => e.target.select()}
                            onChange={e => { const v = e.target.value.replace(/\D/g, ''); setThreads(v === '' ? '' : v); }}
                            onBlur={e => setThreads(Math.min(50, Math.max(1, parseInt(e.target.value) || 1)))} />
                    </div>
                </div>

                {/* Toggles */}
                <div className="config-row-2" style={{ marginBottom: 20 }}>
                    <Toggle label="Skip existing accounts" checked={skipExisting} onChange={setSkipExisting} />
                    <Toggle label="Save session after login" checked={saveSession} onChange={setSaveSession} />
                </div>

                {/* Buttons */}
                <div className="engine-actions">
                    <button className="btn-start" onClick={startValidation} disabled={running || !uploadResult}>
                        <Play size={16} /> START
                    </button>
                    <button className={`btn-stop${running ? ' active' : ''}`} onClick={() => running ? setStopModal(true) : null} disabled={!running}>
                        <StopCircle size={16} /> STOP
                    </button>
                </div>
            </div>

            {/* ═══════════════ Progress Section ═══════════════ */}
            <div className="card" style={{ padding: '16px 24px', marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <span style={{ fontSize: '0.82em', fontWeight: 600, color: 'var(--text-secondary)' }}>Progress</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.82em' }}>
                        <span style={{ color: 'var(--text-muted)' }}>{completed} / {safeProgress.total} ({pct}%)</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--success)' }}><CheckCircle size={12} /> {safeProgress.valid}</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--danger)' }}><XCircle size={12} /> {safeProgress.invalid}</span>
                        {safeProgress.challenge > 0 && <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: '#f59e0b' }}><AlertTriangle size={12} /> {safeProgress.challenge}</span>}
                        {safeProgress.skipped > 0 && <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--text-muted)' }}><Circle size={12} /> {safeProgress.skipped}</span>}
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--warning)' }}><RefreshCw size={12} /> {safeProgress.processing}</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 3, color: 'var(--text-muted)' }}><Circle size={12} /> {queued}</span>
                    </div>
                </div>
                <div className="progress-bar">
                    <div className="progress-fill" style={{ width: `${pct}%`, background: 'var(--teal)' }} />
                </div>
            </div>

            {/* ═══════════════ Thread Monitor ═══════════════ */}
            <div className="card" style={{ padding: '16px 24px' }}>
                <div className="card-section-header">Results</div>

                {!running && completed === 0 ? (
                    <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)', fontSize: '0.85em' }}>
                        Upload a file and press START to begin validation
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {threadLogs.map((tLog, i) => {
                            const isValid = tLog.status === 'completed';
                            const isError = tLog.status === 'error';
                            const isRunning = tLog.status === 'running';
                            const isChallenge = tLog.status === 'challenge';
                            const isSkipped = tLog.status === 'skipped';
                            const statusColor = isValid ? 'var(--success)' : isError ? 'var(--danger)' : isChallenge ? '#f59e0b' : isRunning ? 'var(--warning)' : isSkipped ? 'var(--text-muted)' : 'var(--text-muted)';
                            const statusIcon = isValid ? <CheckCircle size={14} style={{ color: 'var(--success)' }} />
                                : isError ? <XCircle size={14} style={{ color: 'var(--danger)' }} />
                                    : isChallenge ? <AlertTriangle size={14} style={{ color: '#f59e0b' }} />
                                        : isRunning ? <RefreshCw size={14} style={{ color: 'var(--warning)' }} />
                                            : <Circle size={14} style={{ color: 'var(--text-muted)' }} />;

                            const provider = tLog.email ? tLog.email.split('@').pop()?.split('.')[0] : null;

                            return (
                                <div key={i} style={{
                                    display: 'grid', gridTemplateColumns: '70px 40px 1fr 200px',
                                    alignItems: 'center', gap: 8, padding: '10px 14px', borderRadius: 8,
                                    background: isValid ? 'rgba(16,185,129,0.04)' : isError ? 'rgba(239,68,68,0.04)' : isChallenge ? 'rgba(245,158,11,0.04)' : isRunning ? 'rgba(245,158,11,0.04)' : 'rgba(255,255,255,0.01)',
                                    borderLeft: `3px solid ${statusColor}`,
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                        {statusIcon}
                                        <span style={{ fontWeight: 700, fontSize: '0.85em' }}>T-{i + 1}</span>
                                    </div>
                                    {provider && <ProviderLogo provider={provider} size={24} />}
                                    {!provider && <div />}
                                    <span style={{ fontSize: '0.82em', color: tLog.email ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: tLog.email ? 500 : 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {tLog.email || '-'}
                                    </span>
                                    <span style={{ fontSize: '0.78em', color: statusColor, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                        {tLog.current_step || (isValid ? 'Valid' : isError ? 'Invalid' : 'Idle')}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* ═══════════════ Result Message ═══════════════ */}
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
                    <div className="card" style={{ maxWidth: 380, width: '90%', padding: 24 }} onClick={e => e.stopPropagation()}>
                        <div style={{ fontWeight: 800, fontSize: '1.1em', color: 'var(--danger)', marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
                            <StopCircle size={20} /> Stop validation?
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
                            <button className="btn" onClick={stopValidation}
                                style={{ padding: '14px 20px', background: 'var(--danger)', color: '#fff', fontWeight: 700, fontSize: '0.95em', border: 'none', borderRadius: 8 }}>
                                Stop immediately
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

/* ── Sub-components ── */
function StatBox({ label, value, color, small }) {
    return (
        <div style={{
            padding: '10px 14px', borderRadius: 8,
            background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
        }}>
            <div style={{ fontSize: small ? '0.82em' : '1.3em', fontWeight: 800, color }}>{value}</div>
            <div style={{ fontSize: '0.68em', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 }}>{label}</div>
        </div>
    );
}

function Toggle({ label, checked, onChange }) {
    return (
        <div onClick={() => onChange(!checked)} style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 14px', borderRadius: 8, cursor: 'pointer',
            background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
            transition: 'all 0.2s',
        }}>
            <span style={{ fontSize: '0.85em', fontWeight: 600, color: 'var(--text-secondary)' }}>{label}</span>
            <div style={{
                width: 40, height: 22, borderRadius: 11,
                background: checked ? 'var(--accent)' : 'rgba(255,255,255,0.1)',
                transition: 'background 0.2s', position: 'relative',
            }}>
                <div style={{
                    width: 16, height: 16, borderRadius: '50%',
                    background: '#fff', position: 'absolute', top: 3,
                    left: checked ? 21 : 3, transition: 'left 0.2s',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
                }} />
            </div>
        </div>
    );
}
