import React, { useState, useEffect } from 'react';
import {
    Baby, Play, Smartphone, Monitor, Shield, Wifi, Zap, UserCircle, StopCircle
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

import { API } from '../api';

const PROVIDERS = [
    { id: 'gmail', name: 'Gmail', color: '#EA4335', abbr: 'GM', sms: 'simsms', mobileHint: true },
    { id: 'yahoo', name: 'Yahoo', color: '#6001D2', abbr: 'YH', sms: 'simsms' },
    { id: 'aol', name: 'AOL', color: '#FF6B00', abbr: 'AO', sms: 'simsms' },
    { id: 'outlook', name: 'Outlook', color: '#0078D4', abbr: 'OL', sms: 'simsms' },
    { id: 'hotmail', name: 'Hotmail', color: '#0078D4', abbr: 'HM', sms: 'simsms' },
];
export default function Birth() {
    const { t } = useI18n();
    const [provider, setProvider] = useState('outlook');
    const [deviceType, setDeviceType] = useState('desktop'); // 'desktop' or 'phone_android'
    const [smsProvider, setSmsProvider] = useState('simsms');
    const [smsCountries, setSmsCountries] = useState([]);
    const [allCountries, setAllCountries] = useState([]);
    const [countryModal, setCountryModal] = useState(false);
    const [quantity, setQuantity] = useState(5);
    const [threads, setThreads] = useState(1);
    const [farmName, setFarmName] = useState('');
    const [running, setRunning] = useState(false);
    const [result, setResult] = useState(null);
    const [proxyStats, setProxyStats] = useState({ alive: 0, socks5: 0, http: 0, mobile: 0 });
    const [namePacks, setNamePacks] = useState([]);
    const [selectedNamePacks, setSelectedNamePacks] = useState([]);
    const [packsOpen, setPacksOpen] = useState(false);
    const [existingFarms, setExistingFarms] = useState([]);
    const [farmDropOpen, setFarmDropOpen] = useState(false);

    useEffect(() => {
        fetch(`${API}/resources/batch`).then(r => r.json()).then(d => {
            setProxyStats({ alive: d.proxies?.alive || 0, socks5: d.proxies?.socks5 || 0, http: d.proxies?.http || 0, mobile: d.proxies?.mobile || 0 });
            setNamePacks(Array.isArray(d.name_packs) ? d.name_packs : []);
            if (d.task_status?.birth) {
                setRunning(true);
                setResult({ status: 'running', message: '⏳ Регистрация запущена...' });
            }
        }).catch(() => { });

        // Fetch existing farms for dropdown
        fetch(`${API}/farms/`).then(r => r.json()).then(f => setExistingFarms(Array.isArray(f) ? f : [])).catch(() => { });

        // Fetch SMS countries
        fetch(`${API}/birth/sms-countries`).then(r => r.json()).then(d => {
            const countries = d.countries || [];
            setAllCountries(countries);
            setSmsCountries(countries.map(c => c.code));
        }).catch(() => { });
    }, []);

    useEffect(() => {
        const p = PROVIDERS.find(pr => pr.id === provider);
        if (p) setSmsProvider(p.sms);
    }, [provider]);

    const toggleNamePack = (id) => {
        setSelectedNamePacks(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
    };

    const selectedProvider = PROVIDERS.find(p => p.id === provider);

    const startBirth = () => {
        setRunning(true);
        setResult(null);
        fetch(`${API}/birth/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider,
                quantity: parseInt(quantity) || 1,
                device_type: deviceType,
                name_pack_ids: selectedNamePacks,
                sms_provider: smsProvider,
                sms_countries: smsCountries,
                threads: parseInt(threads) || 1,
                farm_name: farmName,
            })
        }).then(r => r.json()).then(d => {
            setResult(d);
        }).catch(() => {
            setResult({ status: 'error', message: 'Не удалось запустить' });
            setRunning(false);
        });
    };

    const [stopModal, setStopModal] = useState(false);

    const stopBirth = (mode) => {
        fetch(`${API}/birth/stop?mode=${mode}`, { method: 'POST' })
            .then(r => r.json())
            .then(d => {
                setRunning(false);
                setStopModal(false);
                setResult({
                    status: 'stopped',
                    message: mode === 'instant'
                        ? `⛔ Мгновенно остановлено: ${d.stopped} задач`
                        : `⏳ Остановка: ждём завершения потоков (${d.stopped} задач)`
                });
            })
            .catch(() => {
                setRunning(false);
                setStopModal(false);
            });
    };

    // Poll backend for running tasks — keep Stop button alive
    useEffect(() => {
        if (!running) return;
        const interval = setInterval(() => {
            fetch(`${API}/birth/status`)
                .then(r => r.json())
                .then(d => {
                    if (d.running) {
                        // Still running — show live progress
                        setResult({
                            status: 'running',
                            message: `⏳ Идёт регистрация: ${d.completed}/${d.total} готово, ошибок: ${d.failed}`
                        });
                    } else {
                        // Task finished
                        setRunning(false);
                        if (d.task_id) {
                            setResult({
                                status: d.status === 'failed' ? 'error' : 'completed',
                                message: `${d.status === 'failed' ? '⛔' : '✅'} Итог: ${d.completed}/${d.total} зарегистрировано, ошибок: ${d.failed}${d.error ? ' — ' + d.error : ''}`
                            });
                        }
                    }
                }).catch(() => { });
        }, 5000);
        return () => clearInterval(interval);
    }, [running]);

    const totalNames = namePacks.filter(np => selectedNamePacks.includes(np.id)).reduce((s, np) => s + (np.total_count || 0), 0);

    return (
        <div className="page">
            <h2 className="page-title"><Baby size={24} /> {t('birthTitle')}</h2>

            {/* Provider selection — BIG cards */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div className="card-title">ПРОВАЙДЕР ПОЧТЫ</div>
                <div style={{ display: 'grid', gridTemplateColumns: `repeat(${PROVIDERS.length}, 1fr)`, gap: 10 }}>
                    {PROVIDERS.map(p => (
                        <button key={p.id}
                            className={`btn ${provider === p.id ? 'btn-primary' : ''}`}
                            onClick={() => setProvider(p.id)}
                            style={{
                                borderColor: provider === p.id ? p.color : 'var(--border-default)',
                                flexDirection: 'column',
                                height: 100,
                                gap: 6,
                                background: provider === p.id ? `${p.color}22` : undefined,
                                borderWidth: provider === p.id ? 2 : 1,
                            }}>
                            <span style={{
                                fontSize: '1.4em', fontWeight: 900,
                                color: provider === p.id ? p.color : 'var(--text-muted)',
                                letterSpacing: '1px',
                            }}>{p.abbr}</span>
                            <span style={{
                                fontWeight: 800,
                                fontSize: '1.1em',
                                color: provider === p.id ? p.color : 'var(--text-primary)',
                                letterSpacing: '0.5px',
                            }}>{p.name}</span>
                            <span style={{ fontSize: '0.72em', color: 'var(--text-muted)', fontWeight: 600 }}>
                                {p.mobileHint ? 'Mobile рек.' : 'Любой'}
                            </span>
                        </button>
                    ))}
                </div>
            </div>

            {/* Name Packs + Device/Proxy — compact row */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16, alignItems: 'stretch' }}>
                {/* Name Pack Selection — dropdown */}
                <div className="card" style={{ padding: '12px 16px' }}>
                    <div
                        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
                        onClick={() => setPacksOpen(!packsOpen)}
                    >
                        <div className="card-title" style={{ margin: 0 }}>
                            <UserCircle size={14} style={{ marginRight: 6 }} /> ПАКИ ИМЁН
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            {selectedNamePacks.length > 0 && (
                                <span style={{ fontSize: '0.8em', color: 'var(--accent)', fontWeight: 700 }}>
                                    {selectedNamePacks.length} выбр. · {totalNames} имён
                                </span>
                            )}
                            <span style={{ color: 'var(--text-muted)', fontSize: '0.8em' }}>{packsOpen ? '▲' : '▼'}</span>
                        </div>
                    </div>
                    {packsOpen && (
                        <div style={{ marginTop: 10, maxHeight: 200, overflowY: 'auto' }}>
                            {namePacks.length === 0 ? (
                                <div style={{ fontSize: '0.85em', color: 'var(--warning)', fontWeight: 600 }}>
                                    ⚠️ Нет паков — загрузите в «Имена»
                                </div>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                    {namePacks.map(np => (
                                        <button key={np.id}
                                            className={`btn btn-sm ${selectedNamePacks.includes(np.id) ? 'btn-primary' : ''}`}
                                            onClick={(e) => { e.stopPropagation(); toggleNamePack(np.id); }}
                                            style={{ justifyContent: 'space-between', fontSize: '0.85em', padding: '5px 10px' }}>
                                            <span>{np.name}</span>
                                            <span style={{ opacity: 0.6, fontSize: '0.9em' }}>{np.total_count}</span>
                                        </button>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Device + Proxy (compact) */}
                <div className="card" style={{ padding: '12px 16px' }}>
                    <div className="card-title" style={{ marginBottom: 8 }}>
                        <Monitor size={14} style={{ marginRight: 6 }} /> УСТРОЙСТВО + ПРОКСИ
                    </div>
                    <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
                        <button
                            className={`btn ${deviceType === 'desktop' ? 'btn-primary' : 'btn-ghost'}`}
                            onClick={() => setDeviceType('desktop')}
                            style={{ flex: 1, padding: '5px 8px', fontSize: '0.85em', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}
                        >
                            <Monitor size={14} /> ПК
                        </button>
                        <button
                            className={`btn ${deviceType === 'phone_android' ? 'btn-primary' : 'btn-ghost'}`}
                            onClick={() => setDeviceType('phone_android')}
                            style={{ flex: 1, padding: '5px 8px', fontSize: '0.85em', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}
                        >
                            <Smartphone size={14} /> Моб
                        </button>
                    </div>
                    {selectedProvider?.mobileHint && deviceType === 'desktop' && (
                        <div style={{ fontSize: '0.75em', color: 'var(--warning)', fontWeight: 600, padding: '3px 6px', background: 'rgba(251,191,36,0.1)', borderRadius: 4, marginBottom: 6 }}>
                            Mobile рекомендуется
                        </div>
                    )}
                    {(() => {
                        const pcCount = proxyStats.socks5 + proxyStats.http;
                        const mobCount = proxyStats.mobile;
                        const count = deviceType === 'desktop' ? pcCount : mobCount;
                        return (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
                                <Wifi size={12} style={{ color: count > 0 ? 'var(--success)' : 'var(--danger)' }} />
                                <span style={{ fontSize: '0.9em', fontWeight: 700, color: count > 0 ? 'var(--success)' : 'var(--danger)' }}>
                                    {count} доступно
                                </span>
                                <span style={{ fontSize: '0.75em', color: 'var(--text-muted)' }}>
                                    {deviceType === 'desktop'
                                        ? `(${proxyStats.socks5} SOCKS5 + ${proxyStats.http} HTTP)`
                                        : `(${mobCount} MOBILE)`
                                    }
                                </span>
                            </div>
                        );
                    })()}
                </div>
            </div>

            {/* Settings */}
            <div className="card" style={{ marginBottom: 16 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
                    <div className="form-group">
                        <label className="form-label">КОЛИЧЕСТВО</label>
                        <input className="form-input" type="text" inputMode="numeric"
                            value={quantity}
                            style={{ fontSize: '1em' }}
                            onFocus={e => e.target.select()}
                            onChange={e => {
                                const v = e.target.value.replace(/\D/g, '');
                                setQuantity(v === '' ? '' : v);
                            }}
                            onBlur={e => {
                                const v = parseInt(e.target.value) || 1;
                                setQuantity(Math.max(1, v));
                            }} />
                    </div>
                    <div className="form-group">
                        <label className="form-label"><Zap size={12} /> ПОТОКОВ (макс. 50)</label>
                        <input className="form-input" type="text" inputMode="numeric"
                            value={threads}
                            style={{ fontSize: '1em' }}
                            onFocus={e => e.target.select()}
                            onChange={e => {
                                const v = e.target.value.replace(/\D/g, '');
                                setThreads(v === '' ? '' : v);
                            }}
                            onBlur={e => {
                                const v = parseInt(e.target.value) || 1;
                                setThreads(Math.min(50, Math.max(1, v)));
                            }} />
                        <div style={{ fontSize: '0.8em', color: 'var(--text-muted)', marginTop: 3 }}>
                            ~300MB RAM / поток
                        </div>
                    </div>
                    <div className="form-group">
                        <label className="form-label">ПРОВАЙДЕР SMS</label>
                        <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                            {['simsms', 'grizzly'].map(sp => (
                                <button key={sp} className={`btn ${smsProvider === sp ? 'btn-primary' : ''}`}
                                    onClick={() => setSmsProvider(sp)}
                                    style={{ flex: 1, fontSize: '0.95em', padding: '10px' }}>
                                    {sp === 'grizzly' ? 'Grizzly' : 'SimSMS'}
                                </button>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Country select button — compact */}
                <div style={{ marginTop: 10 }}>
                    <button className="btn" onClick={() => setCountryModal(true)}
                        style={{ width: '100%', padding: '8px', fontSize: '0.9em', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                        🌍 Выбор стран SMS ({smsCountries.length}/{allCountries.length})
                    </button>
                </div>

                <div className="form-group" style={{ marginTop: 14 }}>
                    <label className="form-label">НАЗВАНИЕ ФЕРМЫ</label>
                    <input className="form-input" value={farmName} onChange={e => setFarmName(e.target.value)}
                        style={{ fontSize: '1em' }}
                        placeholder="Оставьте пустым — создаст автоматически" />
                </div>
            </div>

            {/* Summary */}
            <div className="card" style={{ marginBottom: 16, padding: '14px 20px', background: 'var(--bg-secondary)' }}>
                <div style={{ display: 'flex', gap: 20, fontSize: '0.95em', color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
                    <span>📧 {quantity}× <strong style={{ color: 'var(--accent)' }}>{provider.toUpperCase()}</strong></span>
                    <span>👤 <strong style={{ color: 'var(--accent)' }}>{totalNames || 0}</strong> имён</span>
                    <span>🧵 <strong style={{ color: 'var(--accent)' }}>{threads}</strong> потоков</span>
                    <span>📱 SMS: <strong style={{ color: 'var(--accent)' }}>{smsProvider === 'grizzly' ? 'Grizzly' : 'SimSMS'}</strong></span>
                </div>
            </div>

            {/* Result */}
            {result && (() => {
                const isOk = ['started', 'running', 'completed'].includes(result.status);
                const color = result.status === 'running' ? 'var(--accent)' : isOk ? 'var(--success)' : 'var(--danger)';
                return (
                    <div className="card" style={{
                        marginBottom: 16, padding: '14px 20px',
                        borderLeft: `3px solid ${color}`,
                    }}>
                        <div style={{ fontSize: '1em', fontWeight: 700, color }}>
                            {result.message}
                        </div>
                    </div>
                );
            })()}

            {/* Start / Stop */}
            <div style={{ display: 'flex', gap: 12 }}>
                <button className="btn btn-primary" onClick={startBirth}
                    style={{ padding: '16px 36px', fontSize: '1.05em' }}
                    disabled={((deviceType === 'desktop' ? (proxyStats.socks5 + proxyStats.http) : proxyStats.mobile) === 0) || running || selectedNamePacks.length === 0}>
                    <Play size={18} /> Запустить регистрацию
                    {(deviceType === 'desktop' ? (proxyStats.socks5 + proxyStats.http) : proxyStats.mobile) === 0 && <span style={{ fontSize: '0.75em', marginLeft: 6 }}>(нет прокси для {deviceType === 'desktop' ? 'ПК' : 'Моб'})</span>}
                    {(deviceType === 'desktop' ? (proxyStats.socks5 + proxyStats.http) : proxyStats.mobile) > 0 && selectedNamePacks.length === 0 && <span style={{ fontSize: '0.75em', marginLeft: 6 }}>(выберите паки имён)</span>}
                </button>
                {running && (
                    <button className="btn btn-danger" onClick={() => setStopModal(true)}
                        style={{ padding: '16px 36px', fontSize: '1.05em' }}>
                        <StopCircle size={18} /> Остановить
                    </button>
                )}
            </div>

            {/* Stop mode modal */}
            {stopModal && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 9999,
                    background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    backdropFilter: 'blur(4px)',
                }} onClick={() => setStopModal(false)}>
                    <div className="card" style={{
                        maxWidth: 420, width: '90%', padding: '24px',
                    }} onClick={e => e.stopPropagation()}>
                        <div style={{
                            fontWeight: 800, fontSize: '1.1em', color: 'var(--danger)',
                            marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8,
                        }}>
                            <StopCircle size={20} /> Остановить регистрацию?
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
                            <button className="btn" onClick={() => stopBirth('instant')}
                                style={{
                                    padding: '14px 20px', background: 'var(--danger)', color: '#fff',
                                    fontWeight: 700, fontSize: '0.95em', border: 'none', borderRadius: 8,
                                }}>
                                ⚡ Мгновенно — убить все потоки сейчас
                            </button>
                            <button className="btn" onClick={() => stopBirth('graceful')}
                                style={{
                                    padding: '14px 20px', background: 'var(--warning)', color: '#000',
                                    fontWeight: 700, fontSize: '0.95em', border: 'none', borderRadius: 8,
                                }}>
                                ⏳ Дождаться завершения текущих потоков
                            </button>
                        </div>
                        <button className="btn" onClick={() => setStopModal(false)}
                            style={{ width: '100%', padding: '10px', fontSize: '0.9em' }}>
                            Отмена
                        </button>
                    </div>
                </div>
            )}
            {/* Country select modal */}
            {countryModal && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                    background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center',
                    justifyContent: 'center', zIndex: 9999,
                }} onClick={() => setCountryModal(false)}>
                    <div onClick={e => e.stopPropagation()} style={{
                        background: 'var(--bg-primary)', border: '1px solid var(--border)',
                        borderRadius: 12, padding: 20, width: 440, maxHeight: '70vh',
                        overflowY: 'auto', boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
                    }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                            <h3 style={{ margin: 0, color: 'var(--accent)', fontSize: '1.05em' }}>🌍 Страны для SMS номеров</h3>
                            <div style={{ display: 'flex', gap: 6 }}>
                                <button className="btn btn-primary" style={{ fontSize: '0.75em', padding: '4px 10px' }}
                                    onClick={() => setSmsCountries(allCountries.map(c => c.code))}>Все</button>
                                <button className="btn" style={{ fontSize: '0.75em', padding: '4px 10px' }}
                                    onClick={() => setSmsCountries([])}>Сброс</button>
                            </div>
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 5 }}>
                            {allCountries.map(c => (
                                <button key={c.code}
                                    className={`btn ${smsCountries.includes(c.code) ? 'btn-primary' : ''}`}
                                    onClick={() => setSmsCountries(prev =>
                                        prev.includes(c.code) ? prev.filter(x => x !== c.code) : [...prev, c.code]
                                    )}
                                    style={{
                                        fontSize: '0.82em', padding: '6px 10px', textAlign: 'left',
                                        opacity: smsCountries.includes(c.code) ? 1 : 0.45,
                                    }}>
                                    {c.flag} {c.name}
                                </button>
                            ))}
                        </div>
                        <button className="btn btn-primary" onClick={() => setCountryModal(false)}
                            style={{ width: '100%', marginTop: 14, padding: '10px', fontSize: '0.95em' }}>
                            ✅ Готово ({smsCountries.length} стран)
                        </button>
                    </div>
                </div>
            )}

        </div>
    );
}
