import React, { useState, useEffect } from 'react';
import {
    Settings as SettingsIcon, Key, Copy, Check,
    Trash2, Edit3, Save, TestTube, Loader, Download, RefreshCw
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';
import { API } from '../api';
import { PROVIDER_COLORS } from '../utils/providers';
import { ProviderLogo } from '../components/ProviderLogos';

/* ── Service definitions ── */
const CAPTCHA_SERVICES = [
    { key: 'twocaptcha_key', configPath: ['captcha', 'twocaptcha', 'api_key'], name: '2Captcha', service: 'twocaptcha', desc: 'FunCaptcha / Arkose', color: '#EF4444' },
    { key: 'capguru_key', configPath: ['captcha', 'capguru', 'api_key'], name: 'CapGuru', service: 'capguru', desc: 'reCAPTCHA v2/v3', color: '#10B981' },
    { key: 'capsolver_key', configPath: ['captcha', 'capsolver', 'api_key'], name: 'CapSolver', service: 'capsolver', desc: 'hCaptcha / Image', color: '#3B82F6' },
];

const SMS_SERVICES = [
    { key: 'simsms_key', configPath: ['sms', 'simsms', 'api_key'], name: 'SimSMS', service: 'simsms', desc: 'Default SMS', color: '#06B6D4' },
    { key: 'grizzly_key', configPath: ['sms', 'grizzly', 'api_key'], name: 'Grizzly SMS', service: 'grizzly', desc: 'Alternative', color: '#F59E0B' },
    { key: 'fivesim_key', configPath: ['sms', '5sim', 'api_key'], name: '5sim', service: '5sim', desc: 'Fallback', color: '#8B5CF6' },
];

const PROXY_PROVIDERS = [
    { id: 'gmail', name: 'Gmail', color: PROVIDER_COLORS.gmail, backendKey: 'gmail_proxy_limit', configKey: 'gmail' },
    { id: 'yahoo_aol', name: 'Yahoo + AOL', color: PROVIDER_COLORS.yahoo, backendKey: 'yahoo_aol_proxy_limit', configKey: 'yahoo_aol' },
    { id: 'outlook_hotmail', name: 'Outlook + Hotmail', color: PROVIDER_COLORS.outlook, backendKey: 'outlook_hotmail_proxy_limit', configKey: 'outlook_hotmail' },
    { id: 'protonmail', name: 'ProtonMail', color: PROVIDER_COLORS.protonmail, backendKey: 'protonmail_proxy_limit', configKey: 'protonmail' },
    { id: 'webde', name: 'Web.de', color: PROVIDER_COLORS.webde, backendKey: 'webde_proxy_limit', configKey: 'webde' },
];

function SectionHeader({ color, title, subtitle }) {
    return (
        <div className="settings-section-head">
            <div className="settings-section-head-left">
                <span className="card-section-dot" style={{ background: color }} />
                <div>
                    <div className="settings-section-title">{title}</div>
                    {subtitle && <div className="settings-section-subtitle">{subtitle}</div>}
                </div>
            </div>
        </div>
    );
}


export default function Settings() {
    const _i18n = useI18n();
    const [rawSettings, setRawSettings] = useState({});
    const [editing, setEditing] = useState(null);
    const [editVal, setEditVal] = useState('');
    const [copied, setCopied] = useState(null);
    const [testing, setTesting] = useState(null);
    const [testResult, setTestResult] = useState({});
    const [proxyLimits, setProxyLimits] = useState({});
    const [cooldownTimings, setCooldownTimings] = useState({ soft: 10, hard: 30 });
    const [updateInfo, setUpdateInfo] = useState(null);
    const [updateChecking, setUpdateChecking] = useState(false);
    const [updateApplying, setUpdateApplying] = useState(false);
    const [updateStatus, setUpdateStatus] = useState('');
    const [updateProgress, setUpdateProgress] = useState(null);



    const loadSettings = () => {
        fetch(`${API}/settings/`)
            .then(r => r.json())
            .then(d => {
                setRawSettings(d || {});

                const limits = {};
                const pl = d?.proxy_limits || {};
                PROXY_PROVIDERS.forEach(p => {
                    limits[p.id] = pl[p.configKey] ?? 3;
                });
                setProxyLimits(limits);
                const cd = d?.proxy_cooldown || {};
                setCooldownTimings({ soft: cd.soft_min ?? 10, hard: cd.hard_min ?? 30 });
            })
            .catch(() => { /* ignore */ });
    };

    useEffect(() => {
        loadSettings();
        fetch(`${API}/update/version`).then(r => r.json()).then(d => setUpdateInfo(prev => ({ ...prev, current_version: d.version || d.server_version }))).catch(() => { });
    }, []);

    const getKeyValue = (configPath) => {
        let val = rawSettings;
        for (const p of configPath.slice(0, -1)) {
            val = val?.[p] || {};
        }
        return val?.[configPath[configPath.length - 1]] || '';
    };

    const saveKey = (svc, value) => {
        const body = {};
        body[svc.key] = value;
        fetch(`${API}/settings/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(() => {
            loadSettings();
            setEditing(null);
        });
    };

    const deleteKey = (svc) => {
        const body = {};
        body[svc.key] = '';
        fetch(`${API}/settings/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(() => loadSettings());
    };

    const testService = async (service) => {
        setTesting(service);
        try {
            const r = await fetch(`${API}/settings/test/${service}`, { method: 'POST' });
            const data = await r.json();
            setTestResult(prev => ({ ...prev, [service]: data }));
        } catch {
            setTestResult(prev => ({ ...prev, [service]: { status: 'error', message: 'Connection error' } }));
        }
        setTesting(null);
    };

    const copyKey = (svc) => {
        const val = getKeyValue(svc.configPath);
        navigator.clipboard.writeText(val);
        setCopied(svc.key);
        setTimeout(() => setCopied(null), 1500);
    };

    const getStatus = (svc) => {
        const v = getKeyValue(svc.configPath);
        if (!v || v === '***') return 'missing';
        return 'active';
    };

    const saveProxyLimit = (providerId, value) => {
        const provider = PROXY_PROVIDERS.find(p => p.id === providerId);
        if (!provider) return;
        const body = {};
        body[provider.backendKey] = parseInt(value) || 3;
        fetch(`${API}/settings/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(() => loadSettings());
    };

    /* ── Service card renderer ── */
    const ServiceCard = ({ svc }) => {
        const status = getStatus(svc);
        const maskedVal = getKeyValue(svc.configPath);
        const isEditing = editing === svc.key;
        const tr = testResult[svc.service];

        return (
            <div className="card settings-service-card">
                <div className="settings-service-top">
                    <div style={{ fontWeight: 800, fontSize: '0.95em', color: svc.color || 'var(--text-primary)' }}>{svc.name}</div>
                    {status === 'active' ? (
                        <span className="badge badge-success" style={{ fontSize: '0.7em' }}>Connected</span>
                    ) : (
                        <span className="badge" style={{ fontSize: '0.7em', background: 'rgba(255,255,255,0.06)', color: 'var(--text-muted)' }}>Not configured</span>
                    )}
                </div>

                {/* API Key input */}
                <div style={{ marginBottom: 8 }}>
                    <div className="settings-field-label">API key</div>
                    {isEditing ? (
                        <div style={{ display: 'flex', gap: 6 }}>
                            <input className="form-input" style={{ fontSize: '0.85em', padding: '6px 10px', fontFamily: 'JetBrains Mono, monospace' }}
                                value={editVal} onChange={e => setEditVal(e.target.value)}
                                placeholder="Enter API key" autoFocus />
                            <button className="btn btn-primary btn-sm" onClick={() => saveKey(svc, editVal)}>
                                <Save size={13} />
                            </button>
                        </div>
                    ) : (
                        <div className="settings-key-preview" style={{
                            fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82em', padding: '6px 10px',
                            background: 'rgba(255,255,255,0.03)', borderRadius: 6, color: 'var(--text-secondary)',
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            cursor: 'pointer', border: '1px solid var(--border-subtle)',
                        }} onClick={() => { setEditing(svc.key); setEditVal(''); }}>
                            {maskedVal || '••••••••'}
                        </div>
                    )}
                </div>

                {/* Balance display from test */}
                {tr && (
                    <div style={{
                        fontSize: '0.78em', marginBottom: 8, padding: '4px 8px', borderRadius: 4,
                        background: tr.status === 'ok' ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                        color: tr.status === 'ok' ? 'var(--success)' : 'var(--danger)',
                    }}>
                        {tr.status === 'ok' && tr.balance != null && `Balance: $${tr.balance}`}
                        {tr.message && ` ${tr.message}`}
                    </div>
                )}

                {/* Actions */}
                <div style={{ display: 'flex', gap: 4 }}>
                    <button className="btn btn-sm" style={{ flex: 1, fontSize: '0.78em' }}
                        onClick={() => testService(svc.service)}
                        disabled={testing === svc.service || status === 'missing'}>
                        {testing === svc.service ? <Loader size={12} className="spin" /> : <TestTube size={12} />} Test
                    </button>
                    {maskedVal && maskedVal !== '***' && (
                        <button className="btn btn-sm" onClick={() => copyKey(svc)}>
                            {copied === svc.key ? <Check size={12} /> : <Copy size={12} />}
                        </button>
                    )}
                    <button className="btn btn-sm" onClick={() => { setEditing(svc.key); setEditVal(''); }}>
                        <Edit3 size={12} />
                    </button>
                    {maskedVal && maskedVal !== '***' && (
                        <button className="btn btn-sm btn-danger" onClick={() => deleteKey(svc)}>
                            <Trash2 size={12} />
                        </button>
                    )}
                </div>
            </div>
        );
    };

    return (
        <div className="page">
            <div className="page-header">
                <div className="page-breadcrumb">SYSTEM / SETTINGS</div>
                <h2 className="page-title">
                    <SettingsIcon size={22} /> Settings
                </h2>
                <div className="settings-hero-strip">
                    <div className="settings-hero-chip">
                        <span className="settings-hero-chip-label">Captcha</span>
                        <span className="settings-hero-chip-value">{CAPTCHA_SERVICES.length} providers</span>
                    </div>
                    <div className="settings-hero-chip">
                        <span className="settings-hero-chip-label">SMS</span>
                        <span className="settings-hero-chip-value">{SMS_SERVICES.length} providers</span>
                    </div>
                    <div className="settings-hero-chip">
                        <span className="settings-hero-chip-label">Proxy Policy</span>
                        <span className="settings-hero-chip-value">Per provider</span>
                    </div>
                    <div className="settings-hero-chip">
                        <span className="settings-hero-chip-label">Runtime</span>
                        <span className="settings-hero-chip-value">Boxed app</span>
                    </div>
                </div>
            </div>

            {/* ═══ CAPTCHA SERVICES ═══ */}
            <div style={{ marginBottom: 20 }}>
                <SectionHeader color="#10B981" title="Captcha Services" subtitle="Solver keys and provider health" />
                <div className="config-row-3">
                    {CAPTCHA_SERVICES.map(svc => <ServiceCard key={svc.key} svc={svc} />)}
                </div>
            </div>

            {/* ═══ SMS PROVIDERS ═══ */}
            <div style={{ marginBottom: 20 }}>
                <SectionHeader color="#06B6D4" title="SMS Providers" subtitle="Verification routing and balances" />
                <div className="config-row-3">
                    {SMS_SERVICES.map(svc => <ServiceCard key={svc.key} svc={svc} />)}
                </div>
            </div>



            {/* PROXY LIMITS */}
            <div style={{ marginBottom: 20 }}>
                <SectionHeader color="#F59E0B" title="Proxy Limits" subtitle="Max safe reuse before rotation by provider" />
                <div className="card settings-proxy-card" style={{ padding: '14px 16px' }}>
                    <div className="settings-proxy-grid">
                        {PROXY_PROVIDERS.map(p => (
                            <div key={p.id} className="settings-proxy-provider">
                                <ProviderLogo provider={p.id} size={24} />
                                <span style={{ fontSize: '0.78em', fontWeight: 700, color: p.color, whiteSpace: 'nowrap' }}>{p.name}</span>
                                <input
                                    type="number"
                                    className="form-input"
                                    value={proxyLimits[p.id] ?? 3}
                                    onChange={e => setProxyLimits(prev => ({ ...prev, [p.id]: parseInt(e.target.value) || 0 }))}
                                    onBlur={e => saveProxyLimit(p.id, e.target.value)}
                                    style={{ width: 48, textAlign: 'center', fontSize: '0.95em', padding: '4px 2px', fontWeight: 700 }}
                                    min={0}
                                    max={20}
                                />
                                <span style={{ fontSize: '0.6em', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: 0.5 }}>max uses</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* PROXY COOLDOWN TIMINGS */}
            <div style={{ marginBottom: 20 }}>
                <SectionHeader color="#F59E0B" title="Cooldown Timings" subtitle="How long a proxy pauses per provider after a failure" />
                <div className="card settings-proxy-card" style={{ padding: '14px 16px' }}>
                    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                        {[{ key: 'soft', label: 'Soft fail', desc: 'Timeout / transient', color: '#F59E0B', min: 1, max: 120 },
                          { key: 'hard', label: 'Hard fail', desc: 'Provider block / ban', color: '#EF4444', min: 1, max: 240 }].map(t => (
                            <div key={t.key} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <div>
                                    <div style={{ fontSize: '0.82em', fontWeight: 800, color: t.color }}>{t.label}</div>
                                    <div style={{ fontSize: '0.62em', color: 'var(--text-muted)', fontWeight: 600 }}>{t.desc}</div>
                                </div>
                                <input
                                    type="number"
                                    className="form-input"
                                    value={cooldownTimings[t.key]}
                                    onChange={e => setCooldownTimings(prev => ({ ...prev, [t.key]: parseInt(e.target.value) || 0 }))}
                                    onBlur={e => {
                                        const v = Math.max(t.min, Math.min(t.max, parseInt(e.target.value) || t.min));
                                        setCooldownTimings(prev => ({ ...prev, [t.key]: v }));
                                        const body = t.key === 'soft'
                                            ? { proxy_soft_cooldown_min: v }
                                            : { proxy_hard_cooldown_min: v };
                                        fetch(`${API}/settings/`, {
                                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify(body)
                                        }).then(() => loadSettings());
                                    }}
                                    style={{ width: 56, textAlign: 'center', fontSize: '0.95em', padding: '4px 2px', fontWeight: 700 }}
                                    min={t.min}
                                    max={t.max}
                                />
                                <span style={{ fontSize: '0.62em', color: 'var(--text-muted)', fontWeight: 600, letterSpacing: 0.5 }}>min</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>


            <div style={{ marginBottom: 20 }}>
                <SectionHeader color="#8B5CF6" title="Data Portability" subtitle="Move or back up live operating data" />
                <div className="card" style={{ padding: '20px 24px' }}>
                    <div className="config-row-2">
                        <div>
                            <button className="btn btn-primary" style={{ width: '100%', padding: '12px 16px', fontSize: '0.9em', fontWeight: 700 }}
                                onClick={async () => {
                                    try {
                                        const res = await fetch(`${API}/export/`);
                                        const d = await res.json();
                                        const blob = new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' });
                                        const url = URL.createObjectURL(blob);
                                        const a = document.createElement('a');
                                        a.href = url;
                                        a.download = `leomail-export-${new Date().toISOString().slice(0, 10)}.json`;
                                        a.click();
                                        URL.revokeObjectURL(url);
                                        alert(`Exported: ${d.stats?.total_accounts || 0} accounts, ${d.stats?.total_proxies || 0} proxies, ${d.stats?.total_farms || 0} farms`);
                                    } catch (_e) { void _e; alert('Export failed'); }
                                }}>
                                Export All Data
                            </button>
                            <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 6 }}>
                                Accounts, proxies, farms as JSON
                            </div>
                        </div>
                        <div>
                            <label style={{ display: 'block' }}>
                                <div className="btn" style={{ width: '100%', padding: '12px 16px', fontSize: '0.9em', fontWeight: 700, textAlign: 'center', cursor: 'pointer' }}>
                                    Import Data
                                </div>
                                <input type="file" accept=".json" style={{ display: 'none' }}
                                    onChange={async (ev) => {
                                        const file = ev.target.files?.[0];
                                        if (!file) return;
                                        const fd = new FormData();
                                        fd.append('file', file);
                                        try {
                                            const res = await fetch(`${API}/export/import`, { method: 'POST', body: fd });
                                            const d = await res.json();
                                            if (d.ok) {
                                                alert(`Imported: ${d.imported.accounts} accounts, ${d.imported.proxies} proxies, ${d.imported.farms} farms (${d.imported.skipped} skipped)`);
                                            } else {
                                                alert(d.error || 'Import failed');
                                            }
                                        } catch (_e) { void _e; alert('Import failed'); }
                                        ev.target.value = '';
                                    }} />
                            </label>
                            <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 6 }}>
                                Restore from JSON export file
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* ═══ SYSTEM UPDATE ═══ */}
            <div style={{ marginBottom: 20 }}>
                <SectionHeader color="#8B5CF6" title="System Update" subtitle="Version checks, release notes, and boxed app rollout" />
                <div className="card settings-update-card" style={{ padding: '16px 20px' }}>
                    {/* Version + Check */}
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                        <div>
                            <div style={{ fontSize: '0.78em', color: 'var(--text-muted)', marginBottom: 2 }}>Current Version</div>
                            <div style={{ fontSize: '1.3em', fontWeight: 800, fontFamily: 'JetBrains Mono, monospace' }}>
                                v{updateInfo?.current_version || '...'}
                            </div>
                        </div>
                        <button className="btn btn-primary" onClick={async () => {
                            setUpdateChecking(true);
                            setUpdateStatus('');
                            try {
                                const r = await fetch(`${API}/update/check`);
                                const d = await r.json();
                                setUpdateInfo(d);
                                if (!d.update_available) setUpdateStatus('✅ You are on the latest version');
                            } catch { setUpdateStatus('❌ Failed to check for updates'); }
                            setUpdateChecking(false);
                        }} disabled={updateChecking || updateApplying}
                            style={{ borderRadius: 20, padding: '8px 18px', fontSize: '0.82em' }}>
                            {updateChecking ? <><Loader size={14} className="spin" /> Checking...</> : <><RefreshCw size={14} /> Check for Updates</>}
                        </button>
                    </div>

                    {/* Update available banner */}
                    {updateInfo?.update_available && !updateApplying && (
                        <div style={{ background: 'rgba(139,92,246,0.1)', borderRadius: 10, padding: 16, marginBottom: 10, border: '1px solid rgba(139,92,246,0.25)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                                <div>
                                    <span style={{ fontSize: '1.15em', fontWeight: 800, color: '#8B5CF6' }}>v{updateInfo.remote_version}</span>
                                    <span style={{ color: 'var(--text-muted)', fontSize: '0.78em', marginLeft: 10 }}>
                                        {updateInfo.download_size_mb ? `${updateInfo.download_size_mb} MB` : ''}
                                    </span>
                                </div>
                                <button className="btn btn-success" onClick={async () => {
                                    if (!confirm(`Update to v${updateInfo.remote_version}?\nApp will restart.`)) return;
                                    setUpdateApplying(true);
                                    setUpdateStatus('');
                                    // Start polling progress
                                    let pollCount = 0;
                                    const MAX_POLLS = 120; // 60 seconds at 500ms
                                    const pollId = setInterval(async () => {
                                        if (++pollCount > MAX_POLLS) {
                                            clearInterval(pollId);
                                            setUpdateStatus('❌ Update timed out. Please restart the app.');
                                            setUpdateApplying(false);
                                            return;
                                        }
                                        try {
                                            const r = await fetch(`${API}/update/progress`);
                                            const p = await r.json();
                                            if (p.active) {
                                                const labels = { checking: '🔍 Checking...', backing_up: '💾 Backing up...', downloading: '⬇️ Downloading...', extracting: '📦 Extracting...', verifying: '🔒 Verifying integrity...', applying: '🚀 Applying...', done: '✅ Complete', error: '❌ Error' };
                                                setUpdateStatus(`${labels[p.step] || p.step}  ${p.detail || ''}`);
                                                setUpdateProgress(p);
                                            }
                                            if (p.step === 'applying' || p.step === 'error' || p.step === 'done') {
                                                clearInterval(pollId);
                                                if (p.step === 'applying') setUpdateStatus('🚀 Update downloaded! Restarting...');
                                            }
                                        } catch { /* server may be restarting */ clearInterval(pollId); setUpdateStatus('🔄 Restarting...'); }
                                    }, 500);
                                    try {
                                        const r = await fetch(`${API}/update/download-and-apply`, { method: 'POST' });
                                        const d = await r.json();
                                        clearInterval(pollId);
                                        if (d.success) {
                                            setUpdateStatus('✅ Update downloaded! App is restarting...');
                                        } else {
                                            const rawErr = (d.errors || []).join(', ');
                                            const friendly = rawErr.includes('SHA-256') ? 'Update file failed integrity check. Please try again.'
                                                : rawErr.includes('Download incomplete') ? 'Download was interrupted. Please try again.'
                                                : rawErr.includes('not found in ZIP') ? 'Update package is invalid. Contact support.'
                                                : rawErr || 'Update failed. Please try again.';
                                            setUpdateStatus(`❌ ${friendly}`);
                                            setUpdateApplying(false);
                                        }
                                    } catch {
                                        clearInterval(pollId);
                                        setUpdateStatus('🔄 App is restarting...');
                                        // If app doesn't actually restart within 15s, recover UI
                                        setTimeout(() => { setUpdateApplying(false); }, 15000);
                                    }
                                }} disabled={updateApplying}
                                    style={{ borderRadius: 20, padding: '8px 20px', fontSize: '0.85em', fontWeight: 700 }}>
                                    <Download size={14} /> Update
                                </button>
                            </div>
                            {updateInfo.release_notes && (
                                <pre style={{ fontSize: '0.78em', color: 'var(--text-muted)', whiteSpace: 'pre-wrap', margin: 0, lineHeight: 1.5, maxHeight: 120, overflow: 'auto' }}>
                                    {updateInfo.release_notes.replace(/sha256:\s*[a-fA-F0-9]{64}/g, '').trim()}
                                </pre>
                            )}
                        </div>
                    )}

                    {/* Progress bar during update */}
                    {updateApplying && (
                        <div style={{ marginBottom: 10 }}>
                            <div style={{
                                height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.06)', overflow: 'hidden', marginBottom: 6
                            }}>
                                <div style={{
                                    height: '100%', borderRadius: 3,
                                    background: 'linear-gradient(90deg, #8B5CF6, #6366F1)',
                                    width: `${updateProgress?.percent || 0}%`,
                                    transition: 'width 0.3s ease',
                                }} />
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75em', color: 'var(--text-muted)' }}>
                                <span>{updateProgress?.detail || 'Preparing...'}</span>
                                <span>{updateProgress?.percent || 0}%</span>
                            </div>
                        </div>
                    )}

                    {/* Status message */}
                    {updateStatus && (!updateApplying || updateStatus.includes('❌')) && (
                        <div style={{ fontSize: '0.82em', color: updateStatus.includes('❌') ? '#EF4444' : '#10B981', marginTop: 4 }}>
                            {updateStatus}
                        </div>
                    )}
                </div>
            </div>

            {/* ═══ SAVE SETTINGS ═══ */}
            <button className="btn btn-primary" onClick={() => {
                const body = {};
                PROXY_PROVIDERS.forEach(p => {
                    body[p.backendKey] = parseInt(proxyLimits[p.id]) || 3;
                });
                body.proxy_soft_cooldown_min = cooldownTimings.soft;
                body.proxy_hard_cooldown_min = cooldownTimings.hard;
                fetch(`${API}/settings/`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                }).then(() => loadSettings());
            }} style={{
                width: '100%', padding: '14px', fontSize: '1em', fontWeight: 700,
                marginTop: 16, borderRadius: 8,
            }}>
                Save Settings
            </button>

        </div>
    );
}

/* ── Simple toggle button ── */
function ToggleBtn({ settingKey, rawSettings, onSave }) {
    const isOn = rawSettings?.[settingKey] ?? false;
    return (
        <button
            onClick={() => onSave(settingKey, !isOn)}
            style={{
                width: 40, height: 22, borderRadius: 11, border: 'none', cursor: 'pointer',
                background: isOn ? 'var(--success)' : 'rgba(255,255,255,0.1)',
                position: 'relative', transition: 'background 0.2s',
            }}>
            <div style={{
                width: 16, height: 16, borderRadius: '50%', background: '#fff',
                position: 'absolute', top: 3, left: isOn ? 21 : 3,
                transition: 'left 0.2s', boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
            }} />
        </button>
    );
}
