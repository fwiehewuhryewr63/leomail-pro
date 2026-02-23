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

    // Farm dropdown
    const [farmDropdownOpen, setFarmDropdownOpen] = useState(false);
    const [farmSearch, setFarmSearch] = useState('');
    const farmDropdownRef = React.useRef(null);

    // Settings
    const [emailsMin, setEmailsMin] = useState(25);
    const [emailsMax, setEmailsMax] = useState(75);
    const [delayMin, setDelayMin] = useState(30);
    const [delayMax, setDelayMax] = useState(180);
    const [maxLinkUses, setMaxLinkUses] = useState(0);
    const [maxLinkCycles, setMaxLinkCycles] = useState(0);
    const [threads, setThreads] = useState(10);
    const [sameProvider, setSameProvider] = useState(false);

    const [running, setRunning] = useState(false);
    const [result, setResult] = useState(null);
    const [estimate, setEstimate] = useState(null);

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

    // Close dropdown on outside click
    useEffect(() => {
        const handleClick = (e) => {
            if (farmDropdownRef.current && !farmDropdownRef.current.contains(e.target)) {
                setFarmDropdownOpen(false);
            }
        };
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
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
                max_link_cycles: maxLinkCycles,
                same_provider: sameProvider,
                threads: threads,
            })
        }).then(r => r.json()).then(d => setResult(d)).catch(() => {
            setResult({ status: 'error', message: 'Failed to start' });
        });
    };

    // Auto-estimate on resource change (debounced)
    useEffect(() => {
        if (selectedFarms.length === 0 || selectedTemplates.length === 0 || selectedDBs.length === 0) {
            setEstimate(null);
            return;
        }
        const timer = setTimeout(() => {
            fetch(`${API}/work/estimate`, {
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
                    max_link_cycles: maxLinkCycles,
                    threads: threads,
                })
            }).then(r => r.json()).then(setEstimate).catch(() => { });
        }, 600);
        return () => clearTimeout(timer);
    }, [selectedFarms, selectedDBs, selectedLinkPacks, selectedTemplates,
        emailsMin, emailsMax, delayMin, delayMax, maxLinkUses, maxLinkCycles, threads]);

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

    const filteredFarms = farms.filter(f => f.name.toLowerCase().includes(farmSearch.toLowerCase()));

    return (
        <div className="page">
            <h2 className="page-title">
                <Send size={24} /> {t('workTitle')}
                {running && <span className="badge badge-success" style={{ marginLeft: 12 }}><Zap size={10} /> ACTIVE</span>}
            </h2>

            {/* Farms — Searchable Dropdown */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div className="card-title"><Users size={13} style={{ marginRight: 6 }} /> ФЕРМЫ (АККАУНТЫ)</div>

                {/* Selected farms chips */}
                {selectedFarms.length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                        {selectedFarms.map(id => {
                            const farm = farms.find(f => f.id === id);
                            if (!farm) return null;
                            return (
                                <span key={id} style={{
                                    display: 'inline-flex', alignItems: 'center', gap: 6,
                                    padding: '5px 12px', borderRadius: 20,
                                    background: 'rgba(0,255,65,0.1)', border: '1px solid rgba(0,255,65,0.25)',
                                    fontSize: '0.82em', fontWeight: 600, color: 'var(--accent)',
                                }}>
                                    {farm.name}
                                    <span style={{ opacity: 0.6, fontSize: '0.85em' }}>({farm.account_count || 0})</span>
                                    <span onClick={() => toggle(selectedFarms, setSelectedFarms, id)}
                                        style={{ cursor: 'pointer', marginLeft: 2, opacity: 0.7, fontWeight: 800 }}>✕</span>
                                </span>
                            );
                        })}
                    </div>
                )}

                {/* Dropdown trigger */}
                <div ref={farmDropdownRef} style={{ position: 'relative' }}>
                    <div onClick={() => setFarmDropdownOpen(!farmDropdownOpen)} style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        padding: '10px 14px', borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--border-subtle)', cursor: 'pointer',
                        background: farmDropdownOpen ? 'var(--bg-secondary)' : 'transparent',
                        transition: 'all 0.2s',
                    }}>
                        <span style={{ fontSize: '0.88em', color: selectedFarms.length > 0 ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                            {selectedFarms.length > 0
                                ? `Выбрано ${selectedFarms.length} ферм (${totalAccounts} аккаунтов)`
                                : 'Выберите фермы для рассылки...'}
                        </span>
                        <span style={{ fontSize: '0.7em', color: 'var(--text-muted)', transform: farmDropdownOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>
                    </div>

                    {/* Dropdown panel */}
                    {farmDropdownOpen && (
                        <div style={{
                            position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50,
                            marginTop: 4, borderRadius: 'var(--radius-sm)',
                            border: '1px solid var(--border-subtle)',
                            background: 'var(--bg-card)', boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
                            maxHeight: 280, overflow: 'hidden', display: 'flex', flexDirection: 'column',
                        }}>
                            {/* Search input */}
                            <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--border-subtle)' }}>
                                <input
                                    className="form-input"
                                    placeholder="🔍 Поиск ферм..."
                                    value={farmSearch}
                                    onChange={e => setFarmSearch(e.target.value)}
                                    autoFocus
                                    style={{ fontSize: '0.85em', padding: '6px 10px', width: '100%' }}
                                />
                            </div>

                            {/* Farm list */}
                            <div style={{ overflowY: 'auto', maxHeight: 220 }}>
                                {filteredFarms.length === 0 ? (
                                    <div style={{ padding: '12px 14px', fontSize: '0.82em', color: 'var(--text-muted)' }}>
                                        Нет ферм{farmSearch ? ` для «${farmSearch}»` : ''}
                                    </div>
                                ) : filteredFarms.map(f => {
                                    const isSelected = selectedFarms.includes(f.id);
                                    return (
                                        <div key={f.id}
                                            onClick={() => toggle(selectedFarms, setSelectedFarms, f.id)}
                                            style={{
                                                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                                padding: '9px 14px', cursor: 'pointer',
                                                background: isSelected ? 'rgba(0,255,65,0.06)' : 'transparent',
                                                borderLeft: isSelected ? '3px solid var(--accent)' : '3px solid transparent',
                                                transition: 'all 0.15s',
                                            }}
                                            onMouseEnter={e => e.currentTarget.style.background = isSelected ? 'rgba(0,255,65,0.1)' : 'rgba(255,255,255,0.03)'}
                                            onMouseLeave={e => e.currentTarget.style.background = isSelected ? 'rgba(0,255,65,0.06)' : 'transparent'}
                                        >
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                                <span style={{
                                                    width: 16, height: 16, borderRadius: 4,
                                                    border: isSelected ? '2px solid var(--accent)' : '2px solid var(--border-subtle)',
                                                    background: isSelected ? 'var(--accent)' : 'transparent',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    fontSize: '0.7em', color: '#000', fontWeight: 800,
                                                }}>{isSelected ? '✓' : ''}</span>
                                                <span style={{ fontWeight: 600, fontSize: '0.88em' }}>{f.name}</span>
                                            </div>
                                            <span style={{ fontSize: '0.78em', color: 'var(--text-muted)' }}>
                                                {f.account_count || 0} аккаунтов
                                            </span>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    )}
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
                        <label className="form-label"><LinkIcon size={12} /> ЦИКЛОВ ССЫЛОК</label>
                        <input className="form-input" type="text" inputMode="numeric"
                            value={maxLinkCycles}
                            onFocus={e => e.target.select()}
                            onChange={e => { const v = e.target.value.replace(/\D/g, ''); setMaxLinkCycles(v === '' ? '' : v); }}
                            onBlur={e => setMaxLinkCycles(parseInt(e.target.value) || 0)} />
                        <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginTop: 2 }}>
                            0 = ∞ кругов
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label"><LinkIcon size={12} /> МАКС. РАЗ/ССЫЛКУ</label>
                        <input className="form-input" type="text" inputMode="numeric"
                            value={maxLinkUses}
                            onFocus={e => e.target.select()}
                            onChange={e => { const v = e.target.value.replace(/\D/g, ''); setMaxLinkUses(v === '' ? '' : v); }}
                            onBlur={e => setMaxLinkUses(parseInt(e.target.value) || 0)} />
                        <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginTop: 2 }}>
                            0 = без лимита
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">ПРЕСЕТЫ ССЫЛОК</label>
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 2 }}>
                            <button className={`btn btn-sm ${maxLinkCycles === 0 && maxLinkUses === 0 ? 'btn-primary' : ''}`}
                                onClick={() => { setMaxLinkCycles(0); setMaxLinkUses(0); }}>🔁 Безлимит</button>
                            <button className={`btn btn-sm ${maxLinkCycles === 1 && maxLinkUses === 1 ? 'btn-primary' : ''}`}
                                onClick={() => { setMaxLinkCycles(1); setMaxLinkUses(1); }}>1️⃣ Одноразовый</button>
                            <button className={`btn btn-sm ${maxLinkCycles === 3 && maxLinkUses === 0 ? 'btn-primary' : ''}`}
                                onClick={() => { setMaxLinkCycles(3); setMaxLinkUses(0); }}>🔄 3 круга</button>
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

            {/* Resource Calculator */}
            {estimate && (
                <div className="card" style={{
                    marginBottom: 16, padding: '14px 20px',
                    borderLeft: `3px solid ${estimate.sufficient ? 'var(--success)' : 'var(--danger)'}`,
                    background: estimate.sufficient ? 'rgba(0,210,160,0.03)' : 'rgba(255,107,74,0.03)',
                }}>
                    <div style={{ display: 'flex', gap: 16, fontSize: '0.82em', color: 'var(--text-secondary)', flexWrap: 'wrap', marginBottom: estimate.warnings?.length ? 10 : 0 }}>
                        <span>👥 Аккаунтов: <strong style={{ color: 'var(--accent)' }}>{estimate.accounts}</strong></span>
                        <span>📬 Получателей: <strong style={{ color: 'var(--accent)' }}>{estimate.recipients}</strong></span>
                        <span>📊 Ёмкость: <strong style={{ color: estimate.total_capacity >= estimate.recipients ? 'var(--success)' : 'var(--warning)' }}>{estimate.total_capacity}</strong></span>
                        <span>📝 Шаблонов: <strong style={{ color: 'var(--accent)' }}>{estimate.templates}</strong></span>
                        {estimate.links_effective != null && (
                            <span>🔗 Ссылок: <strong style={{ color: 'var(--accent)' }}>{estimate.links_total}</strong>
                                {estimate.links_effective < 999999 && <span style={{ color: 'var(--text-muted)' }}> (×{Math.ceil(estimate.links_effective / Math.max(estimate.links_total, 1))} = {estimate.links_effective})</span>}
                                {estimate.links_effective >= 999999 && <span style={{ color: 'var(--text-muted)' }}> (∞)</span>}
                            </span>
                        )}
                        <span>⏱ ETA: <strong style={{ color: 'var(--accent)' }}>
                            {estimate.estimated_hours < 1 ? `${Math.round(estimate.estimated_hours * 60)} мин` : `${estimate.estimated_hours} ч`}
                        </strong></span>
                        <span>🧵 Потоков: <strong style={{ color: 'var(--accent)' }}>{threads}</strong></span>
                    </div>
                    {estimate.warnings?.length > 0 && (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                            {estimate.warnings.map((w, i) => (
                                <div key={i} style={{ fontSize: '0.78em', fontWeight: 600, color: w.startsWith('❌') ? 'var(--danger)' : 'var(--warning)' }}>
                                    {w}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}

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
