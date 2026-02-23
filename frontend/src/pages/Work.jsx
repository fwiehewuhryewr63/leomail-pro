import React, { useState, useEffect } from 'react';
import {
    Send, Play, Square, AlertTriangle, CheckCircle, XCircle,
    Clock, Shield, FileText, Link as LinkIcon, Database, Zap, Users, Timer, Mail
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

import { API } from '../api';

export default function Work() {
    const { t } = useI18n();
    const [templates, setTemplates] = useState([]);  // Packs
    const [databases, setDatabases] = useState([]);
    const [linkPacks, setLinkPacks] = useState([]);  // Link Packs
    const [farms, setFarms] = useState([]);

    // Multi-select IDs
    const [selectedFarms, setSelectedFarms] = useState([]);
    const [selectedDBs, setSelectedDBs] = useState([]);
    const [selectedLinkPacks, setSelectedLinkPacks] = useState([]);
    const [selectedTemplates, setSelectedTemplates] = useState([]);

    // Settings
    const [emailsMin, setEmailsMin] = useState(25);
    const [emailsMax, setEmailsMax] = useState(75);
    const [delayMin, setDelayMin] = useState(30);
    const [delayMax, setDelayMax] = useState(180);
    const [maxLinkUses, setMaxLinkUses] = useState(0);
    const [threads, setThreads] = useState(10);
    const [sameProvider, setSameProvider] = useState(false);

    const [running, setRunning] = useState(false);
    const [result, setResult] = useState(null);

    useEffect(() => {
        fetch(`${API}/resources/batch`).then(r => r.json()).then(d => {
            setTemplates(Array.isArray(d.templates) ? d.templates : []);
            setDatabases(Array.isArray(d.databases) ? d.databases : []);
            setLinkPacks(Array.isArray(d.links) ? d.links : []);
            setFarms(Array.isArray(d.farms) ? d.farms : []);
            if (d.task_status?.work) {
                setRunning(true);
                setResult({ status: 'running', message: '⏳ Рассылка запущена...' });
            }
        }).catch(() => { });
    }, []);

    const toggle = (list, setList, id) => {
        setList(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
    };

    const startWork = () => {
        setRunning(true);
        setResult(null);
        fetch(`${API}/work/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                farm_ids: selectedFarms,
                database_ids: selectedDBs,
                link_database_ids: selectedLinkPacks,
                template_ids: selectedTemplates,
                emails_per_day_min: emailsMin,
                emails_per_day_max: emailsMax,
                delay_min: delayMin,
                delay_max: delayMax,
                max_link_uses: maxLinkUses,
                same_provider: sameProvider,
                threads: threads,
            })
        }).then(r => r.json()).then(d => setResult(d)).catch(() => {
            setResult({ status: 'error', message: 'Failed to start' });
        });
    };

    const totalRecipients = databases.filter(d => selectedDBs.includes(d.id)).reduce((sum, d) => sum + (d.total_count - d.used_count), 0);
    const totalAccounts = farms.filter(f => selectedFarms.includes(f.id)).reduce((sum, f) => sum + (f.account_count || 0), 0);

    // Issue categories
    const issueCards = [
        { key: 'rate_limit', label: t('issueRateLimit'), icon: Clock, color: 'var(--warning)', desc: 'Лимит отправки → авто-пауза', critical: true },
        { key: 'mailer_daemon', label: 'Bounce получателя', icon: AlertTriangle, color: 'var(--warning)', desc: 'Жёлтая — аккаунт продолжает, рейтинг -1', critical: false },
        { key: 'send_error', label: 'Ошибка отправки', icon: XCircle, color: 'var(--danger)', desc: 'Ошибка → учитывается', critical: true },
        { key: 'suspended', label: t('issueSuspended'), icon: Shield, color: '#e74c3c', desc: 'Бан → исключён', critical: true },
        { key: 'not_found', label: 'Не найден', icon: CheckCircle, color: 'var(--text-muted)', desc: 'НЕ штрафуется', critical: false },
    ];

    return (
        <div className="page">
            <h2 className="page-title">
                <Send size={24} /> {t('workTitle')}
                {running && <span className="badge badge-success" style={{ marginLeft: 12 }}><Zap size={10} /> ACTIVE</span>}
            </h2>

            {/* Farms */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div className="card-title"><Users size={13} style={{ marginRight: 6 }} /> ФЕРМЫ (АККАУНТЫ)</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8 }}>
                    {farms.map(f => (
                        <button key={f.id} className={`btn ${selectedFarms.includes(f.id) ? 'btn-primary' : ''}`}
                            onClick={() => toggle(selectedFarms, setSelectedFarms, f.id)}
                            style={{ textAlign: 'left', padding: '10px 14px', gap: 4, flexDirection: 'column', alignItems: 'flex-start' }}>
                            <span style={{ fontWeight: 700, fontSize: '0.95em' }}>{f.name}</span>
                            <span style={{ fontSize: '0.8em', opacity: 0.7 }}>{f.account_count || 0} аккаунтов</span>
                        </button>
                    ))}
                </div>
            </div>

            {/* Resources: Templates, Databases, Links */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 }}>
                {/* Templates (For now individual, grouping by pack later if needed) */}
                <div className="card">
                    <div className="card-title"><FileText size={13} style={{ marginRight: 6 }} /> ШАБЛОНЫ</div>
                    <div style={{ display: 'grid', gap: 4, maxHeight: 200, overflowY: 'auto' }}>
                        {templates.length === 0 && (
                            <div style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>Нет шаблонов</div>
                        )}
                        {templates.map(tmpl => (
                            <button key={tmpl.id} className={`btn btn-sm ${selectedTemplates.includes(tmpl.id) ? 'btn-primary' : ''}`}
                                onClick={() => toggle(selectedTemplates, setSelectedTemplates, tmpl.id)}
                                style={{ justifyContent: 'flex-start', fontSize: '0.8em', textAlign: 'left' }}>
                                <div style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                    {tmpl.name} <span style={{ opacity: 0.6 }}>({tmpl.pack_name || 'Без пачки'})</span>
                                </div>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Recipient Databases */}
                <div className="card">
                    <div className="card-title"><Database size={13} style={{ marginRight: 6 }} /> БАЗЫ EMAIL</div>
                    <div style={{ display: 'grid', gap: 4, maxHeight: 200, overflowY: 'auto' }}>
                        {databases.length === 0 && (
                            <div style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>Нет баз</div>
                        )}
                        {databases.map(d => (
                            <button key={d.id} className={`btn btn-sm ${selectedDBs.includes(d.id) ? 'btn-primary' : ''}`}
                                onClick={() => toggle(selectedDBs, setSelectedDBs, d.id)}
                                style={{ justifyContent: 'flex-start', fontSize: '0.8em' }}>
                                {d.name} ({d.total_count - d.used_count})
                            </button>
                        ))}
                    </div>
                </div>

                {/* Link Packs */}
                <div className="card">
                    <div className="card-title"><LinkIcon size={13} style={{ marginRight: 6 }} /> ПАКИ ССЫЛОК</div>
                    <div style={{ display: 'grid', gap: 4, maxHeight: 200, overflowY: 'auto' }}>
                        {linkPacks.length === 0 && (
                            <div style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>Нет паков</div>
                        )}
                        {linkPacks.map(l => (
                            <button key={l.id} className={`btn btn-sm ${selectedLinkPacks.includes(l.id) ? 'btn-primary' : ''}`}
                                onClick={() => toggle(selectedLinkPacks, setSelectedLinkPacks, l.id)}
                                style={{ justifyContent: 'flex-start', fontSize: '0.8em' }}>
                                {l.name} ({l.total_count})
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            {/* Settings Grid */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                    <div className="form-group">
                        <label className="form-label"><Mail size={12} /> ПИСЕМ/ДЕНЬ МИН.</label>
                        <input className="form-input" type="number" value={emailsMin} min={1}
                            onChange={e => setEmailsMin(parseInt(e.target.value) || 25)} />
                    </div>
                    <div className="form-group">
                        <label className="form-label"><Mail size={12} /> ПИСЕМ/ДЕНЬ МАКС.</label>
                        <input className="form-input" type="number" value={emailsMax} min={1}
                            onChange={e => setEmailsMax(parseInt(e.target.value) || 75)} />
                    </div>
                    <div className="form-group">
                        <label className="form-label"><Timer size={12} /> {t('delayMin')}</label>
                        <input className="form-input" type="number" value={delayMin} min={5}
                            onChange={e => setDelayMin(parseInt(e.target.value) || 30)} />
                    </div>
                    <div className="form-group">
                        <label className="form-label"><Timer size={12} /> {t('delayMax')}</label>
                        <input className="form-input" type="number" value={delayMax} min={10}
                            onChange={e => setDelayMax(parseInt(e.target.value) || 180)} />
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginTop: 12 }}>
                    <div className="form-group">
                        <label className="form-label"><Zap size={12} /> ПОТОКОВ (макс. 50)</label>
                        <input className="form-input" type="number" value={threads} min={1} max={50}
                            onChange={e => setThreads(Math.min(50, parseInt(e.target.value) || 10))} />
                    </div>
                    <div className="form-group">
                        <label className="form-label"><LinkIcon size={12} /> МАКС. ССЫЛКА</label>
                        <input className="form-input" type="number" value={maxLinkUses} min={0}
                            onChange={e => setMaxLinkUses(parseInt(e.target.value) || 0)} />
                        <div style={{ fontSize: '0.8em', color: 'var(--text-muted)', marginTop: 2 }}>
                            0 = без лимита
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">SAME / CROSS PROVIDER</label>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
                            <div className={`toggle-track ${sameProvider ? 'active' : ''}`} onClick={() => setSameProvider(!sameProvider)}>
                                <div className="toggle-knob" />
                            </div>
                            <span style={{ fontSize: '0.9em', color: sameProvider ? 'var(--accent)' : 'var(--text-muted)', fontWeight: 600 }}>
                                {sameProvider ? 'Один провайдер' : 'Кросс-провайдер'}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Summary */}
            <div className="card" style={{ marginBottom: 16, padding: '12px 20px', background: 'var(--bg-secondary)' }}>
                <div style={{ display: 'flex', gap: 20, fontSize: '0.82em', color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
                    <span>👥 Аккаунтов: <strong style={{ color: 'var(--accent)' }}>{totalAccounts}</strong></span>
                    <span>📬 Получателей: <strong style={{ color: 'var(--accent)' }}>{totalRecipients}</strong></span>
                    <span>📧 Писем/аккаунт: <strong style={{ color: 'var(--accent)' }}>{emailsMin}-{emailsMax}</strong></span>
                    <span>📝 Шаблонов: <strong style={{ color: 'var(--accent)' }}>{selectedTemplates.length}</strong></span>
                    <span>🔗 Паков ссылок: <strong style={{ color: 'var(--accent)' }}>{selectedLinkPacks.length}</strong></span>
                    <span>🧵 Потоков: <strong style={{ color: 'var(--accent)' }}>{threads}</strong></span>
                </div>
            </div>

            {/* Issue Monitoring */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div className="card-title"><AlertTriangle size={13} style={{ marginRight: 6 }} /> {t('accountIssues')}</div>
                <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginBottom: 8 }}>
                    Все ошибки кроме "Not Found" → авто-исключение аккаунта
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
                    {issueCards.map(ic => (
                        <div key={ic.key} style={{
                            padding: '10px', borderRadius: 'var(--radius-sm)',
                            border: `1px solid ${ic.critical ? 'rgba(225,112,85,0.15)' : 'var(--border-subtle)'}`,
                            background: ic.critical ? 'rgba(225,112,85,0.03)' : 'transparent',
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                <ic.icon size={13} style={{ color: ic.color }} />
                                <span style={{ fontSize: '0.72em', fontWeight: 700, color: ic.color }}>{ic.label}</span>
                            </div>
                            <div style={{ fontSize: '1.2em', fontWeight: 800, color: ic.critical ? 'var(--danger)' : 'var(--text-muted)' }}>0</div>
                            <div style={{ fontSize: '0.62em', color: 'var(--text-muted)', marginTop: 2 }}>{ic.desc}</div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Result */}
            {result && (
                <div className="card" style={{
                    marginBottom: 16, padding: '12px 20px',
                    borderLeft: `3px solid ${result.status === 'started' ? 'var(--success)' : 'var(--danger)'}`,
                }}>
                    <div style={{ fontSize: '0.88em', fontWeight: 700, color: result.status === 'started' ? 'var(--success)' : 'var(--danger)' }}>
                        {result.status === 'started' ? '✅ ' : '❌ '}{result.message}
                    </div>
                </div>
            )}

            {/* Start/Stop */}
            <div style={{ display: 'flex', gap: 12 }}>
                <button className="btn btn-primary" onClick={startWork}
                    style={{ padding: '14px 32px' }}
                    disabled={selectedFarms.length === 0 || selectedTemplates.length === 0 || selectedDBs.length === 0}>
                    <Play size={16} /> {t('startWork')}
                    {(selectedFarms.length === 0 || selectedTemplates.length === 0 || selectedDBs.length === 0) && (
                        <span style={{ fontSize: '0.7em', marginLeft: 6 }}>(выберите фермы + шаблоны + базы)</span>
                    )}
                </button>
            </div>
        </div>
    );
}
