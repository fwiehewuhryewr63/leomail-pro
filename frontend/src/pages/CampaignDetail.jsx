import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
    ArrowLeft, Play, Pause, Square, FileText, Link2, Users,
    Upload, Trash2, CheckCircle, AlertTriangle, XCircle, Shield, Mail,
    Plus, RefreshCw, File
} from 'lucide-react';
import { API } from '../api';

export default function CampaignDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [c, setC] = useState(null);
    const [preflight, setPreflight] = useState(null);
    const [tab, setTab] = useState('overview');
    const [importText, setImportText] = useState('');
    const [maxUses, setMaxUses] = useState(100);
    const [importing, setImporting] = useState(false);
    const fileRef = useRef(null);

    const load = () => fetch(`${API}/campaigns/${id}`).then(r => r.json()).then(setC).catch(() => { });
    useEffect(() => {
        load();
        const interval = (c && c.status === 'running') ? 3000 : 10000;
        const iv = setInterval(load, interval);
        return () => clearInterval(iv);
    }, [id, c?.status]);

    const loadPreflight = () => fetch(`${API}/campaigns/${id}/preflight`).then(r => r.json()).then(setPreflight).catch(() => { });
    useEffect(() => { loadPreflight(); }, [id]);

    if (!c) return <div className="page" style={{ padding: 40, color: 'var(--text-muted)' }}>Loading...</div>;

    const pct = c.recipients_total > 0 ? Math.round(c.recipients_sent / c.recipients_total * 100) : 0;

    const action = async (act) => { await fetch(`${API}/campaigns/${id}/${act}`, { method: 'POST' }); load(); loadPreflight(); };

    const doImport = async (endpoint) => {
        setImporting(true);
        try {
            const body = { content: importText, max_uses: maxUses };
            const r = await fetch(`${API}/campaigns/${id}/${endpoint}/import`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
            });
            const d = await r.json();
            alert(`✅ Added: ${d.added}, skipped: ${d.skipped || 0}`);
            setImportText('');
            load(); loadPreflight();
        } catch { alert('Import error'); }
        finally { setImporting(false); }
    };

    const doFileUpload = async (endpoint, file) => {
        if (!file) return;
        setImporting(true);
        try {
            const text = await file.text();
            const body = { content: text, max_uses: maxUses };
            const r = await fetch(`${API}/campaigns/${id}/${endpoint}/import`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
            });
            const d = await r.json();
            alert(`✅ File "${file.name}": added ${d.added}, skipped ${d.skipped || 0}`);
            load(); loadPreflight();
        } catch { alert('File upload error'); }
        finally { setImporting(false); }
    };

    // Resource counters for tabs
    const templateCount = c.templates ? c.templates.length : 0;
    const templateActive = c.templates ? c.templates.filter(t => t.active).length : 0;
    const linksLeft = (c.links_total || 0) - (c.links_used || 0);
    const recipientsLeft = (c.recipients_total || 0) - (c.recipients_sent || 0);
    const isRunning = c.status === 'running';

    // Low resource warnings
    const linksLow = isRunning && c.links_total > 0 && linksLeft < 10;
    const recipientsLow = isRunning && c.recipients_total > 0 && recipientsLeft < 20;

    return (
        <div className="page">
            <div className="page-header">
                <div className="page-breadcrumb">OPERATIONS / CAMPAIGNS</div>
                <h2 className="page-title" style={{ cursor: 'pointer' }} onClick={() => navigate('/campaigns')}>
                    <ArrowLeft size={18} /> {c.name}
                    <span style={{
                        fontSize: '0.42em', fontWeight: 700, padding: '3px 10px', borderRadius: 12,
                        background: `${statusColor(c.status)}20`, color: statusColor(c.status),
                        border: `1px solid ${statusColor(c.status)}40`,
                    }} className="detail-status-pill">{statusLabel(c.status)}</span>
                </h2>
                <div className="engine-hero-strip">
                    <div className="engine-hero-chip">
                        <span className="engine-hero-chip-label">Stage</span>
                        <span className="engine-hero-chip-value">{statusLabel(c.status)}</span>
                    </div>
                    <div className="engine-hero-chip">
                        <span className="engine-hero-chip-label">Recipients</span>
                        <span className="engine-hero-chip-value">{c.recipients_sent || 0} / {c.recipients_total || 0}</span>
                    </div>
                    <div className="engine-hero-chip">
                        <span className="engine-hero-chip-label">Templates</span>
                        <span className="engine-hero-chip-value">{templateActive} active / {templateCount} total</span>
                    </div>
                    <div className="engine-hero-chip">
                        <span className="engine-hero-chip-label">Links Left</span>
                        <span className="engine-hero-chip-value">{linksLeft}</span>
                    </div>
                </div>
            </div>

            {/* Action bar */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
                {['draft', 'paused', 'stopped'].includes(c.status) &&
                    <button className="engine-primary-action" style={btnStyle('var(--success)')} onClick={() => action('start')}><Play size={14} /> Start</button>}
                {c.status === 'running' &&
                    <button className="engine-secondary-action" style={btnStyle('#f59e0b')} onClick={() => action('pause')}><Pause size={14} /> Pause</button>}
                {['running', 'paused'].includes(c.status) &&
                    <button className="engine-secondary-action" style={btnStyle('var(--danger)')} onClick={() => action('stop')}><Square size={14} /> Stop</button>}
                <button className="engine-secondary-action" style={btnStyle('var(--text-muted)')} onClick={() => loadPreflight()}><Shield size={14} /> Pre-flight</button>
            </div>

            {/* Stats cards */}
            <div className="dash-stats" style={{ marginBottom: 16 }}>
                <StatBox label="Sent" value={c.total_sent || 0} color="var(--success)" icon={Mail} />
                <StatBox label="Errors" value={c.total_errors || 0} color="var(--danger)" icon={AlertTriangle} />
                <StatBox label="Acc Born" value={c.accounts_born || 0} color="var(--info)" icon={Users} />
                <StatBox label="Acc Dead" value={c.accounts_dead || 0} color="var(--danger)" icon={XCircle} />
                <StatBox label="Progress" value={`${pct}%`} color="var(--accent)" icon={CheckCircle} />
            </div>

            {/* Progress bar */}
            {c.recipients_total > 0 && (
                <div className="card engine-card" style={{ marginBottom: 16, padding: '12px 18px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8em', marginBottom: 6, color: 'var(--text-muted)' }}>
                        <span>Recipients: {c.recipients_sent} / {c.recipients_total}</span>
                        <span>Links: {c.links_active || 0} / {c.links_total || 0}</span>
                    </div>
                    <div className="progress-bar"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
                </div>
            )}

            {/* Low resource warning banners */}
            {isRunning && templateActive > 0 && templateActive < 5 && (
                <div className="card resource-warning-card">
                    <AlertTriangle size={16} style={{ color: 'var(--warning)' }} />
                    <span style={{ fontSize: '0.85em', color: 'var(--warning)' }}>⚡ Templates running low ({templateActive} left) — <strong style={{ cursor: 'pointer' }} onClick={() => setTab('templates')}>add more</strong></span>
                </div>
            )}
            {linksLow && (
                <div className="card resource-warning-card">
                    <AlertTriangle size={16} style={{ color: 'var(--warning)' }} />
                    <span style={{ fontSize: '0.85em', color: 'var(--warning)' }}>⚡ Links running low ({linksLeft} left) — <strong style={{ cursor: 'pointer' }} onClick={() => setTab('links')}>add more</strong></span>
                </div>
            )}
            {recipientsLow && (
                <div className="card resource-warning-card">
                    <AlertTriangle size={16} style={{ color: 'var(--warning)' }} />
                    <span style={{ fontSize: '0.85em', color: 'var(--warning)' }}>⚡ Recipients running low ({recipientsLeft} left) — <strong style={{ cursor: 'pointer' }} onClick={() => setTab('recipients')}>add more</strong></span>
                </div>
            )}

            {c.stop_reason && (
                <div className="card" style={{ marginBottom: 16, padding: '12px 18px', borderLeft: '3px solid var(--danger)', background: 'linear-gradient(180deg, rgba(239,68,68,0.04), transparent 70%), var(--bg-card)' }}>
                    <span style={{ color: 'var(--danger)', fontWeight: 700 }}>⚠️ Stopped: </span>
                    <span style={{ color: 'var(--text-secondary)' }}>{c.stop_reason}</span>
                </div>
            )}

            {/* Pre-flight */}
            {preflight && (
                <div className="card engine-card" style={{ marginBottom: 16, padding: '16px 18px' }}>
                    <div style={{ fontSize: '0.75em', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--text-muted)', marginBottom: 10 }}>Pre-flight Check</div>
                    <div className="config-row-3" style={{ gap: 10 }}>
                        <PFItem label="Templates" status={preflight.templates?.status} detail={`${preflight.templates?.count || 0} active`} />
                        <PFItem label="Links" status={preflight.links?.status} detail={`${preflight.links?.count || 0} active`} />
                        <PFItem label="Recipients" status={preflight.recipients?.status} detail={`${preflight.recipients?.count || 0} unsent`} />
                        <PFItem label="SMS Balance" status={preflight.sms?.status} detail={`$${preflight.sms?.total_balance || 0} (~${preflight.sms?.estimated_accounts || 0} accs)`} />
                        <PFItem label="Proxies" status={preflight.proxies?.status} detail={`${preflight.proxies?.alive || 0} alive (${preflight.proxies?.geo_match || 0} GEO)`} />
                        <PFItem label="Providers" status={preflight.providers?.status} detail={(preflight.providers?.list || []).join(', ') || 'none'} />
                    </div>
                    <div style={{ marginTop: 10, textAlign: 'center', fontWeight: 700, fontSize: '0.9em', color: preflight.ready ? 'var(--success)' : 'var(--danger)' }}>
                        {preflight.ready ? '✅ Ready to launch' : '❌ Critical issues found'}
                    </div>
                </div>
            )}

            {/* Tabs */}
            <div className="soft-tabbar">
                {[
                    { id: 'templates', label: `Templates (${templateActive})`, icon: FileText },
                    { id: 'links', label: `Links (${c.links_active || 0})`, icon: Link2 },
                    { id: 'recipients', label: `Recipients (${recipientsLeft})`, icon: Users },
                ].map(t => (
                    <button key={t.id} onClick={() => setTab(t.id)} className={`soft-tab${tab === t.id ? ' active' : ''}`} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <t.icon size={14} /> {t.label}
                    </button>
                ))}
            </div>

            {/* Tab content */}
            <div className="card engine-card" style={{ padding: '18px' }}>
                {tab === 'templates' && (
                    <>
                        <TabHeader
                            title="Email Templates"
                            subtitle={`${templateActive} active, ${templateCount} total`}
                            isRunning={isRunning}
                            runningHint="Templates can be added live — they'll be picked up automatically"
                        />
                        <textarea style={ta} value={importText} onChange={e => setImportText(e.target.value)}
                            placeholder={"---TEMPLATE---\nSubject: Olá {{NAME}}\nBody:\n<p>Olá {{NAME}}, confira <a href=\"{{LINK}}\">aqui</a></p>\n---TEMPLATE---\nSubject: Oportunidade\nBody:\n<p>Veja isso: <a href=\"{{LINK}}\">clique</a></p>"} />
                        <ImportButtons
                            onTextImport={() => doImport('templates')}
                            onFileSelect={(f) => doFileUpload('templates', f)}
                            importing={importing}
                            disabled={!importText}
                            fileRef={fileRef}
                            accept=".txt,.html"
                        />
                        {c.templates && c.templates.length > 0 && (
                            <div style={{ marginTop: 14 }}>
                                <div style={{ fontSize: '0.72em', fontWeight: 700, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>Current Templates:</div>
                                {c.templates.map(t => (
                                    <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                        <span style={{ fontSize: '0.85em', flex: 1, color: t.active ? 'var(--text-primary)' : 'var(--text-muted)' }}>{t.subject}</span>
                                        <span style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>×{t.use_count}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </>
                )}

                {tab === 'links' && (
                    <>
                        <TabHeader
                            title="Links"
                            subtitle={`${c.links_active || 0} active of ${c.links_total || 0}`}
                            isRunning={isRunning}
                            runningHint="Links can be added live — no restart needed"
                        />
                        <div style={{ display: 'flex', gap: 10, marginBottom: 8, alignItems: 'flex-end' }}>
                            <div>
                                <label style={{ fontSize: '0.72em', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Max uses/link</label>
                                <input style={{ ...inp, width: 100 }} type="number" value={maxUses} onChange={e => setMaxUses(+e.target.value)} />
                            </div>
                        </div>
                        <textarea style={ta} value={importText} onChange={e => setImportText(e.target.value)}
                            placeholder={"https://example.com/offer1\nhttps://example.com/offer2\nhttps://example.com/offer3"} />
                        <ImportButtons
                            onTextImport={() => doImport('links')}
                            onFileSelect={(f) => doFileUpload('links', f)}
                            importing={importing}
                            disabled={!importText}
                            fileRef={fileRef}
                            accept=".txt,.csv"
                        />
                    </>
                )}

                {tab === 'recipients' && (
                    <>
                        <TabHeader
                            title="Recipients"
                            subtitle={`${recipientsLeft} remaining of ${c.recipients_total || 0}`}
                            isRunning={isRunning}
                            runningHint="New recipients join the queue, duplicates are skipped"
                        />
                        <textarea style={ta} value={importText} onChange={e => setImportText(e.target.value)}
                            placeholder={"user1@example.com\nuser2@example.com,John\nuser3@example.com,Maria"} />
                        <ImportButtons
                            onTextImport={() => doImport('recipients')}
                            onFileSelect={(f) => doFileUpload('recipients', f)}
                            importing={importing}
                            disabled={!importText}
                            fileRef={fileRef}
                            accept=".txt,.csv"
                        />
                    </>
                )}
            </div>
        </div>
    );
}

// --- Sub-components ---

const TabHeader = ({ title, subtitle, isRunning, runningHint }) => (
    <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--text-primary)' }}>{title}</span>
            <span style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>— {subtitle}</span>
        </div>
        {isRunning && (
            <div style={{ fontSize: '0.72em', color: 'var(--success)', display: 'flex', alignItems: 'center', gap: 4 }}>
                <RefreshCw size={10} style={{ animation: 'spin 2s linear infinite' }} /> {runningHint}
            </div>
        )}
    </div>
);

const ImportButtons = ({ onTextImport, onFileSelect, importing, disabled, fileRef, accept }) => (
    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button style={{ ...btnStyle('var(--accent)') }} onClick={onTextImport} disabled={importing || disabled}>
            <Upload size={14} /> {importing ? 'Importing...' : 'Add from text'}
        </button>
        <button style={{ ...btnStyle('var(--info)') }} onClick={() => fileRef.current?.click()}>
            <File size={14} /> Upload file
        </button>
        <input
            ref={fileRef}
            type="file"
            accept={accept}
            style={{ display: 'none' }}
            onChange={(e) => { if (e.target.files[0]) onFileSelect(e.target.files[0]); e.target.value = ''; }}
        />
    </div>
);

// --- helpers ---
const statusColor = (s) => ({ draft: 'var(--text-muted)', running: 'var(--success)', paused: 'var(--warning)', completed: 'var(--info)', stopped: 'var(--danger)' }[s] || 'var(--text-muted)');
const statusLabel = (s) => ({ draft: 'DRAFT', running: 'RUNNING', paused: 'PAUSED', completed: 'DONE', stopped: 'STOPPED' }[s] || s);

const StatBox = ({ label, value, color, icon: Icon }) => (
    <div className="card" style={{ padding: '12px 14px', textAlign: 'center' }}>
        <Icon size={14} style={{ color, marginBottom: 4 }} />
        <div style={{ fontSize: '1.4em', fontWeight: 800, color }}>{value}</div>
        <div style={{ fontSize: '0.68em', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 2 }}>{label}</div>
    </div>
);

const PFItem = ({ label, status, detail }) => (
    <div style={{ padding: '8px 12px', background: 'rgba(255,255,255,0.02)', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
        {status === 'ok' ? <CheckCircle size={14} style={{ color: 'var(--success)' }} /> :
            status === 'warning' ? <AlertTriangle size={14} style={{ color: 'var(--warning)' }} /> :
                <XCircle size={14} style={{ color: 'var(--danger)' }} />}
        <div>
            <div style={{ fontSize: '0.78em', fontWeight: 700, color: 'var(--text-primary)' }}>{label}</div>
            <div style={{ fontSize: '0.7em', color: 'var(--text-muted)' }}>{detail}</div>
        </div>
    </div>
);

const btnStyle = (c) => ({
    display: 'inline-flex', alignItems: 'center', gap: 6, padding: '8px 18px',
    fontWeight: 700, fontSize: '0.85em', borderRadius: 6, cursor: 'pointer',
    background: `${c}20`, border: `1px solid ${c}55`, color: c,
    transition: 'all 0.2s',
});
const inp = {
    padding: '8px 12px', background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6,
    color: 'var(--text-primary)', fontSize: '0.85em', outline: 'none',
};
const ta = {
    width: '100%', minHeight: 120, padding: '12px 14px',
    background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: 8, color: 'var(--text-primary)', fontSize: '0.85em',
    fontFamily: 'monospace', resize: 'vertical', outline: 'none',
    lineHeight: 1.5,
};
