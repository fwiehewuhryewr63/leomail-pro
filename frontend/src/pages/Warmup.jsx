import React, { useState, useEffect } from 'react';
import {
    Flame, Play, Mail, Users, Timer, Zap, FileText, Link2,
    ArrowRight, Shield, BarChart3, Square
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

const API = 'http://localhost:8000/api';

export default function Warmup() {
    const { t } = useI18n();
    const [farms, setFarms] = useState([]);
    const [templates, setTemplates] = useState([]);
    const [linkPacks, setLinkPacks] = useState([]);

    // Sender / Receiver farm selection
    const [senderFarms, setSenderFarms] = useState([]);
    const [receiverFarms, setReceiverFarms] = useState([]);

    const [selectedTemplates, setSelectedTemplates] = useState([]);
    const [selectedLinks, setSelectedLinks] = useState([]);

    // Phase override: 0=auto, 1-5
    const [phaseOverride, setPhaseOverride] = useState(0);

    const [emailsMin, setEmailsMin] = useState(1);
    const [emailsMax, setEmailsMax] = useState(5);
    const [delayMin, setDelayMin] = useState(60);
    const [delayMax, setDelayMax] = useState(300);
    const [threads, setThreads] = useState(5);
    const [sameProvider, setSameProvider] = useState(false);
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState(null);
    const [stats, setStats] = useState(null);

    useEffect(() => {
        fetch(`${API}/resources/batch`).then(r => r.json()).then(d => {
            setFarms(Array.isArray(d.farms) ? d.farms : []);
            setTemplates(Array.isArray(d.templates) ? d.templates : []);
            setLinkPacks(Array.isArray(d.links) ? d.links : []);
            if (d.task_status?.warmup) {
                setRunning(true);
                setResult({ status: 'running', message: '⏳ Прогрев запущен...' });
            }
        }).catch(() => { });

        // Load latest stats
        fetch(`${API}/warmup/stats/latest`).then(r => r.json()).then(setStats).catch(() => { });
    }, []);

    // Poll stats while running
    useEffect(() => {
        if (!running) return;
        const iv = setInterval(() => {
            fetch(`${API}/warmup/stats/latest`).then(r => r.json()).then(setStats).catch(() => { });
            fetch(`${API}/warmup/status`).then(r => r.json()).then(d => {
                if (!d.running && d.status !== 'running') setRunning(false);
            }).catch(() => { });
        }, 10000);
        return () => clearInterval(iv);
    }, [running]);

    const toggle = (list, setList, id) => {
        setList(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
    };

    const startWarmup = () => {
        setRunning(true);
        setResult(null);
        fetch(`${API}/warmup/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sender_farm_ids: senderFarms,
                receiver_farm_ids: receiverFarms,
                template_ids: selectedTemplates,
                link_pack_ids: selectedLinks,
                phase_override: phaseOverride,
                emails_per_day_min: emailsMin,
                emails_per_day_max: emailsMax,
                delay_min: delayMin,
                delay_max: delayMax,
                same_provider: sameProvider,
                threads: threads,
            })
        }).then(r => r.json()).then(d => {
            setResult(d);
            if (d.status === 'error') setRunning(false);
        }).catch(() => {
            setResult({ status: 'error', message: 'Не удалось запустить' });
            setRunning(false);
        });
    };

    const stopWarmup = () => {
        fetch(`${API}/warmup/stop`, { method: 'POST' }).then(r => r.json()).then(() => {
            setRunning(false);
            setResult({ status: 'stopped', message: '⏹ Прогрев остановлен' });
        }).catch(() => { });
    };

    const totalSenders = farms.filter(f => senderFarms.includes(f.id)).reduce((sum, f) => sum + (f.account_count || 0), 0);
    const totalReceivers = farms.filter(f => receiverFarms.includes(f.id)).reduce((sum, f) => sum + (f.account_count || 0), 0);

    // Group templates by pack
    const packs = {};
    templates.forEach(t => {
        const pack = t.pack_name || 'Без пачки';
        if (!packs[pack]) packs[pack] = [];
        packs[pack].push(t);
    });

    const phaseLabels = {
        0: '🔄 Авто (по дню аккаунта)',
        1: '1️⃣ Фаза 1 (дни 1-3, 1-3 писем)',
        2: '2️⃣ Фаза 2 (дни 4-7, 5-10 писем)',
        3: '3️⃣ Фаза 3 (дни 8-14, 10-20 писем)',
        4: '4️⃣ Фаза 4 (дни 15-21, 20-50 писем)',
        5: '5️⃣ Фаза 5 (дни 22-30, 50-100 писем)',
    };

    const canStart = senderFarms.length > 0 && receiverFarms.length > 0 && selectedTemplates.length > 0;

    return (
        <div className="page">
            <h2 className="page-title">
                <Flame size={24} /> {t('warmupTitle')}
                {running && <span className="badge badge-success" style={{ marginLeft: 12 }}><Zap size={10} /> АКТИВЕН</span>}
            </h2>

            {/* Stats Panel */}
            {stats && stats.total_sent > 0 && (
                <div className="card" style={{ marginBottom: 16 }}>
                    <div className="card-title"><BarChart3 size={14} style={{ marginRight: 6 }} /> СТАТИСТИКА ПРОГРЕВА</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
                        <div style={{ textAlign: 'center', padding: 10, borderRadius: 8, background: 'rgba(0,255,65,0.04)', border: '1px solid rgba(0,255,65,0.1)' }}>
                            <div style={{ fontSize: '1.4em', fontWeight: 800, color: 'var(--accent)' }}>{stats.total_sent}</div>
                            <div style={{ fontSize: '0.65em', color: 'var(--text-muted)', letterSpacing: 1 }}>ОТПРАВЛЕНО</div>
                        </div>
                        <div style={{ textAlign: 'center', padding: 10, borderRadius: 8, background: 'rgba(0,255,65,0.04)', border: '1px solid rgba(0,255,65,0.1)' }}>
                            <div style={{ fontSize: '1.4em', fontWeight: 800, color: 'var(--accent)' }}>{stats.total_checked}</div>
                            <div style={{ fontSize: '0.65em', color: 'var(--text-muted)', letterSpacing: 1 }}>ПРОВЕРЕНО</div>
                        </div>
                        <div style={{ textAlign: 'center', padding: 10, borderRadius: 8, background: 'rgba(46,204,113,0.06)', border: '1px solid rgba(46,204,113,0.15)' }}>
                            <div style={{ fontSize: '1.4em', fontWeight: 800, color: '#2ecc71' }}>{stats.inbox_rate}%</div>
                            <div style={{ fontSize: '0.65em', color: 'var(--text-muted)', letterSpacing: 1 }}>INBOX RATE</div>
                        </div>
                        <div style={{ textAlign: 'center', padding: 10, borderRadius: 8, background: 'rgba(231,76,60,0.06)', border: '1px solid rgba(231,76,60,0.15)' }}>
                            <div style={{ fontSize: '1.4em', fontWeight: 800, color: '#e74c3c' }}>{stats.spam_rate}%</div>
                            <div style={{ fontSize: '0.65em', color: 'var(--text-muted)', letterSpacing: 1 }}>SPAM RATE</div>
                        </div>
                        <div style={{ textAlign: 'center', padding: 10, borderRadius: 8, background: 'rgba(52,152,219,0.06)', border: '1px solid rgba(52,152,219,0.15)' }}>
                            <div style={{ fontSize: '1.4em', fontWeight: 800, color: '#3498db' }}>{stats.reply_rate}%</div>
                            <div style={{ fontSize: '0.65em', color: 'var(--text-muted)', letterSpacing: 1 }}>REPLY RATE</div>
                        </div>
                        <div style={{ textAlign: 'center', padding: 10, borderRadius: 8, background: 'rgba(255,165,0,0.06)', border: '1px solid rgba(255,165,0,0.12)' }}>
                            <div style={{ fontSize: '1.4em', fontWeight: 800, color: '#ffa500' }}>{stats.not_found_count || 0}</div>
                            <div style={{ fontSize: '0.65em', color: 'var(--text-muted)', letterSpacing: 1 }}>NOT FOUND</div>
                        </div>
                    </div>
                </div>
            )}

            {/* Farm Selection: Sender + Receiver */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 12, marginBottom: 16, alignItems: 'start' }}>
                {/* Sender Farms */}
                <div className="card">
                    <div className="card-title" style={{ color: '#e74c3c' }}>
                        <Mail size={14} style={{ marginRight: 6 }} /> 🔴 ФЕРМЫ-ОТПРАВИТЕЛИ
                    </div>
                    <div style={{ fontSize: '0.78em', color: 'var(--text-muted)', marginBottom: 8 }}>
                        Аккаунты этих ферм будут ОТПРАВЛЯТЬ письма
                    </div>
                    {farms.length === 0 ? (
                        <div style={{ fontSize: '0.85em', color: 'var(--text-muted)' }}>Нет ферм</div>
                    ) : (
                        <div style={{ display: 'grid', gap: 6 }}>
                            {farms.map(f => {
                                const isReceiver = receiverFarms.includes(f.id);
                                return (
                                    <button key={f.id}
                                        className={`btn btn-sm ${senderFarms.includes(f.id) ? 'btn-primary' : ''}`}
                                        onClick={() => !isReceiver && toggle(senderFarms, setSenderFarms, f.id)}
                                        disabled={isReceiver}
                                        style={{
                                            justifyContent: 'space-between', textAlign: 'left',
                                            opacity: isReceiver ? 0.3 : 1,
                                        }}>
                                        <span style={{ fontWeight: 600 }}>{f.name}</span>
                                        <span style={{ fontSize: '0.8em', opacity: 0.7 }}>{f.account_count || 0} акк</span>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                    {senderFarms.length > 0 && (
                        <div style={{ marginTop: 8, fontSize: '0.85em', color: '#e74c3c', fontWeight: 700 }}>
                            Отправители: {totalSenders} акк
                        </div>
                    )}
                </div>

                {/* Arrow */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', paddingTop: 60 }}>
                    <ArrowRight size={32} style={{ color: 'var(--accent)', opacity: 0.5 }} />
                </div>

                {/* Receiver Farms */}
                <div className="card">
                    <div className="card-title" style={{ color: '#2ecc71' }}>
                        <Shield size={14} style={{ marginRight: 6 }} /> 🟢 ФЕРМЫ-ПОЛУЧАТЕЛИ
                    </div>
                    <div style={{ fontSize: '0.78em', color: 'var(--text-muted)', marginBottom: 8 }}>
                        Аккаунты этих ферм ПОЛУЧАЮТ письма, проверяют inbox/spam и ОТВЕЧАЮТ
                    </div>
                    {farms.length === 0 ? (
                        <div style={{ fontSize: '0.85em', color: 'var(--text-muted)' }}>Нет ферм</div>
                    ) : (
                        <div style={{ display: 'grid', gap: 6 }}>
                            {farms.map(f => {
                                const isSender = senderFarms.includes(f.id);
                                return (
                                    <button key={f.id}
                                        className={`btn btn-sm ${receiverFarms.includes(f.id) ? 'btn-primary' : ''}`}
                                        onClick={() => !isSender && toggle(receiverFarms, setReceiverFarms, f.id)}
                                        disabled={isSender}
                                        style={{
                                            justifyContent: 'space-between', textAlign: 'left',
                                            opacity: isSender ? 0.3 : 1,
                                            ...(receiverFarms.includes(f.id) ? { background: '#2ecc71', borderColor: '#2ecc71' } : {}),
                                        }}>
                                        <span style={{ fontWeight: 600 }}>{f.name}</span>
                                        <span style={{ fontSize: '0.8em', opacity: 0.7 }}>{f.account_count || 0} акк</span>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                    {receiverFarms.length > 0 && (
                        <div style={{ marginTop: 8, fontSize: '0.85em', color: '#2ecc71', fontWeight: 700 }}>
                            Получатели: {totalReceivers} акк
                        </div>
                    )}
                </div>
            </div>

            {/* Phase Override */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div className="card-title">
                    <Zap size={14} style={{ marginRight: 6 }} /> ФАЗА ПРОГРЕВА
                </div>
                <div style={{ fontSize: '0.85em', color: 'var(--text-muted)', marginBottom: 10 }}>
                    «Авто» — каждый аккаунт использует свой текущий день прогрева.<br />
                    Принудительная фаза — все аккаунты работают с лимитами выбранной фазы.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                    {Object.entries(phaseLabels).map(([key, label]) => (
                        <button key={key}
                            className={`btn btn-sm ${phaseOverride === parseInt(key) ? 'btn-primary' : ''}`}
                            onClick={() => setPhaseOverride(parseInt(key))}
                            style={{ textAlign: 'left', fontSize: '0.85em' }}>
                            {label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Template Selection */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div className="card-title">
                    <FileText size={14} style={{ marginRight: 6 }} /> ШАБЛОНЫ ПИСЕМ
                </div>
                <div style={{ fontSize: '0.85em', color: 'var(--text-muted)', marginBottom: 10 }}>
                    Выберите шаблоны из загруженных паков. Софт будет ротировать между ними.
                </div>
                {templates.length === 0 ? (
                    <div style={{ fontSize: '0.85em', color: 'var(--text-muted)' }}>Нет шаблонов. Загрузите ZIP в «Шаблоны».</div>
                ) : (
                    <div style={{ maxHeight: 240, overflowY: 'auto' }}>
                        {Object.entries(packs).map(([packName, tmpls]) => (
                            <div key={packName} style={{ marginBottom: 10 }}>
                                <div style={{ fontSize: '0.85em', fontWeight: 700, color: 'var(--accent)', marginBottom: 6 }}>
                                    📦 {packName} ({tmpls.length})
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 6 }}>
                                    {tmpls.map(tmpl => (
                                        <button key={tmpl.id}
                                            className={`btn btn-sm ${selectedTemplates.includes(tmpl.id) ? 'btn-primary' : ''}`}
                                            onClick={() => toggle(selectedTemplates, setSelectedTemplates, tmpl.id)}
                                            style={{ justifyContent: 'flex-start', fontSize: '0.85em', textAlign: 'left' }}>
                                            {tmpl.name}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
                {selectedTemplates.length > 0 && (
                    <div style={{ marginTop: 8, fontSize: '0.85em', color: 'var(--accent)', fontWeight: 700 }}>
                        Выбрано: {selectedTemplates.length} шаблонов
                    </div>
                )}
            </div>

            {/* Settings Grid */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: 12 }}>
                    <div className="form-group">
                        <label className="form-label"><Mail size={12} /> ПИСЕМ МИН.</label>
                        <input className="form-input" type="number" value={emailsMin} min={1}
                            style={{ fontSize: '1em' }}
                            onChange={e => setEmailsMin(parseInt(e.target.value) || 1)} />
                    </div>
                    <div className="form-group">
                        <label className="form-label"><Mail size={12} /> ПИСЕМ МАКС.</label>
                        <input className="form-input" type="number" value={emailsMax} min={1}
                            style={{ fontSize: '1em' }}
                            onChange={e => setEmailsMax(parseInt(e.target.value) || 5)} />
                    </div>
                    <div className="form-group">
                        <label className="form-label"><Timer size={12} /> ЗАДЕРЖКА МИН. (СЕК)</label>
                        <input className="form-input" type="number" value={delayMin} min={10}
                            style={{ fontSize: '1em' }}
                            onChange={e => setDelayMin(parseInt(e.target.value) || 60)} />
                    </div>
                    <div className="form-group">
                        <label className="form-label"><Timer size={12} /> ЗАДЕРЖКА МАКС. (СЕК)</label>
                        <input className="form-input" type="number" value={delayMax} min={30}
                            style={{ fontSize: '1em' }}
                            onChange={e => setDelayMax(parseInt(e.target.value) || 300)} />
                    </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 12 }}>
                    <div className="form-group">
                        <label className="form-label"><Zap size={12} /> ПОТОКОВ (макс. 50)</label>
                        <input className="form-input" type="number" value={threads} min={1} max={50}
                            style={{ fontSize: '1em' }}
                            onChange={e => setThreads(Math.min(50, parseInt(e.target.value) || 5))} />
                    </div>
                    <div className="form-group">
                        <label className="form-label">ТИП ПРОВАЙДЕРА</label>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
                            <div className={`toggle-track ${sameProvider ? 'active' : ''}`} onClick={() => setSameProvider(!sameProvider)}>
                                <div className="toggle-knob" />
                            </div>
                            <span style={{ fontSize: '0.9em', color: sameProvider ? 'var(--accent)' : 'var(--text-muted)', fontWeight: 600 }}>
                                {sameProvider ? 'Один провайдер (Gmail→Gmail)' : 'Кросс-провайдер (Gmail→Outlook→Yahoo)'}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            {/* Summary */}
            <div className="card" style={{ marginBottom: 16, padding: '14px 20px', background: 'var(--bg-secondary)' }}>
                <div style={{ display: 'flex', gap: 16, fontSize: '0.9em', color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
                    <span>🔴 Отправителей: <strong style={{ color: '#e74c3c' }}>{totalSenders}</strong></span>
                    <span>🟢 Получателей: <strong style={{ color: '#2ecc71' }}>{totalReceivers}</strong></span>
                    <span>📝 Шаблонов: <strong style={{ color: 'var(--accent)' }}>{selectedTemplates.length}</strong></span>
                    <span>⚡ Фаза: <strong style={{ color: 'var(--accent)' }}>{phaseOverride === 0 ? 'Авто' : phaseOverride}</strong></span>
                    <span>📧 Писем: <strong style={{ color: 'var(--accent)' }}>{emailsMin}-{emailsMax}</strong></span>
                    <span>🧵 Потоков: <strong style={{ color: 'var(--accent)' }}>{threads}</strong></span>
                    <span>🔀 {sameProvider ? 'Same' : 'Cross'}</span>
                </div>
            </div>

            {/* Result */}
            {result && (
                <div className="card" style={{
                    marginBottom: 16, padding: '14px 20px',
                    borderLeft: `3px solid ${result.status === 'started' ? 'var(--success)' : result.status === 'error' ? 'var(--danger)' : 'var(--warning)'}`,
                }}>
                    <div style={{
                        fontSize: '0.95em', fontWeight: 700,
                        color: result.status === 'started' ? 'var(--success)' : result.status === 'error' ? 'var(--danger)' : 'var(--warning)'
                    }}>
                        {result.status === 'started' ? '✅ ' : result.status === 'error' ? '❌ ' : '⏹ '}{result.message}
                    </div>
                </div>
            )}

            {/* Start/Stop Button */}
            <div style={{ display: 'flex', gap: 12 }}>
                {!running ? (
                    <button className="btn btn-primary" onClick={startWarmup}
                        style={{ padding: '16px 36px', fontSize: '1.05em' }}
                        disabled={!canStart}>
                        <Play size={18} /> Запустить прогрев
                        {!canStart && (
                            <span style={{ fontSize: '0.7em', marginLeft: 6 }}>
                                (выберите отправителей + получателей + шаблоны)
                            </span>
                        )}
                    </button>
                ) : (
                    <button className="btn btn-danger" onClick={stopWarmup}
                        style={{ padding: '16px 36px', fontSize: '1.05em' }}>
                        <Square size={18} /> Остановить прогрев
                    </button>
                )}
            </div>
        </div>
    );
}
