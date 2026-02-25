import React, { useState, useEffect } from 'react';
import {
    Settings as SettingsIcon, Key, Copy, Check,
    Trash2, Edit3, Save, TestTube, Loader
} from 'lucide-react';
import { useI18n } from '../i18n/I18nContext';

import { API } from '../api';

const SERVICE_KEYS = [
    { key: 'simsms_key', configPath: ['sms', 'simsms', 'api_key'], name: 'SimSMS', desc: 'SMS верификация (default)', required: true, service: 'simsms', services: ['Birth (все провайдеры)'] },
    { key: 'grizzly_key', configPath: ['sms', 'grizzly', 'api_key'], name: 'Grizzly SMS', desc: 'SMS верификация (alt)', required: false, service: 'grizzly', services: ['Birth (Gmail)'] },
    { key: 'fivesim_key', configPath: ['sms', '5sim', 'api_key'], name: '5sim', desc: 'SMS верификация (fallback)', required: false, service: '5sim', services: ['Birth (все провайдеры)'] },
    { key: 'capguru_key', configPath: ['captcha', 'capguru', 'api_key'], name: 'CapGuru', desc: 'reCAPTCHA v2/v3 (Gmail, Yahoo)', required: true, service: 'capguru', services: ['Birth (reCAPTCHA)'] },
    { key: 'twocaptcha_key', configPath: ['captcha', 'twocaptcha', 'api_key'], name: '2Captcha', desc: 'FunCaptcha / Arkose (Outlook, Hotmail)', required: false, service: 'twocaptcha', services: ['Birth (Outlook/Hotmail)'] },
];

export default function Settings() {
    const { t } = useI18n();
    const [tab, setTab] = useState('keys');
    const [rawSettings, setRawSettings] = useState({});
    const [editing, setEditing] = useState(null);
    const [editVal, setEditVal] = useState('');
    const [copied, setCopied] = useState(null);
    const [saved, setSaved] = useState(false);
    const [testing, setTesting] = useState(null);
    const [testResult, setTestResult] = useState({});

    useEffect(() => { loadSettings(); }, []);

    const loadSettings = () => {
        fetch(`${API}/settings/`)
            .then(r => r.json())
            .then(d => setRawSettings(d || {}))
            .catch(() => { });
    };

    const getMaskedKey = (ak) => {
        const path = ak.configPath;
        let val = rawSettings;
        for (const p of path.slice(0, -1)) {
            val = val?.[p] || {};
        }
        return val?.[path[path.length - 1]] || '';
    };

    const saveKey = (ak, value) => {
        const body = {};
        body[ak.key] = value;
        fetch(`${API}/settings/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(() => {
            loadSettings();
            setEditing(null);
            flashSaved();
        });
    };

    const deleteKey = (ak) => {
        const body = {};
        body[ak.key] = '';
        fetch(`${API}/settings/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(() => loadSettings());
    };

    const flashSaved = () => {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const testService = async (service) => {
        setTesting(service);
        try {
            const r = await fetch(`${API}/settings/test/${service}`, { method: 'POST' });
            const data = await r.json();
            setTestResult(prev => ({ ...prev, [service]: data }));
        } catch (e) {
            setTestResult(prev => ({ ...prev, [service]: { status: 'error', message: 'Ошибка подключения' } }));
        }
        setTesting(null);
    };

    const copyKey = (key) => {
        const masked = getMaskedKey(SERVICE_KEYS.find(a => a.key === key));
        navigator.clipboard.writeText(masked);
        setCopied(key);
        setTimeout(() => setCopied(null), 1500);
    };

    const getStatus = (ak) => {
        const v = getMaskedKey(ak);
        if (!v || v === '***') return 'missing';
        if (v.length < 8) return 'short';
        return 'active';
    };

    const tabs = [
        { id: 'keys', label: t('apiKeys') },
        { id: 'general', label: t('general') },
        { id: 'system', label: t('systemTab') },
    ];

    return (
        <div className="page">
            <h2 className="page-title"><SettingsIcon size={24} /> {t('settingsTitle')}</h2>

            <div style={{ display: 'flex', gap: 4, marginBottom: 20, borderBottom: '1px solid var(--border-default)', paddingBottom: 0 }}>
                {tabs.map(tb => (
                    <button key={tb.id} className="btn" onClick={() => setTab(tb.id)} style={{
                        borderRadius: '8px 8px 0 0', border: 'none',
                        borderBottom: tab === tb.id ? '2px solid var(--accent)' : '2px solid transparent',
                        background: tab === tb.id ? 'var(--accent-subtle)' : 'transparent',
                        color: tab === tb.id ? 'var(--text-primary)' : 'var(--text-muted)',
                        fontWeight: tab === tb.id ? 700 : 500, padding: '10px 20px',
                    }}>
                        {tb.label}
                    </button>
                ))}
            </div>

            {/* Service API Keys */}
            {tab === 'keys' && (
                <div style={{ display: 'grid', gap: 10 }}>
                    {SERVICE_KEYS.map(ak => {
                        const status = getStatus(ak);
                        const maskedVal = getMaskedKey(ak);
                        const isEditing = editing === ak.key;
                        const tr = testResult[ak.service];

                        return (
                            <div key={ak.key} className="card" style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px' }}>
                                <div style={{ flex: 1 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                                        <Key size={14} style={{ color: 'var(--accent)' }} />
                                        <span style={{ fontWeight: 700, fontSize: '0.95em' }}>{ak.name}</span>
                                        {ak.required && <span className="badge badge-accent">{t('required')}</span>}
                                        {status === 'active' && <span className="badge badge-success">ACTIVE</span>}
                                        {status === 'missing' && <span className="badge badge-danger">MISSING</span>}
                                    </div>
                                    <div style={{ fontSize: '0.78em', color: 'var(--text-muted)', marginBottom: 6 }}>
                                        {ak.desc} — {ak.services.join(', ')}
                                    </div>
                                    {isEditing ? (
                                        <div style={{ display: 'flex', gap: 6 }}>
                                            <input className="form-input" style={{ fontSize: '0.85em', padding: '6px 10px' }}
                                                value={editVal} onChange={e => setEditVal(e.target.value)}
                                                placeholder={t('enterApiKey')} autoFocus />
                                            <button className="btn btn-primary btn-sm" onClick={() => saveKey(ak, editVal)}>
                                                <Save size={13} />
                                            </button>
                                        </div>
                                    ) : maskedVal && maskedVal !== '***' ? (
                                        <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.82em', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '100%' }}>
                                            {maskedVal}
                                        </div>
                                    ) : null}
                                    {tr && (
                                        <div style={{
                                            fontSize: '0.75em', marginTop: 4, padding: '4px 8px', borderRadius: 4,
                                            background: tr.status === 'ok' ? 'rgba(0,184,148,0.1)' : 'rgba(225,112,85,0.1)',
                                            color: tr.status === 'ok' ? 'var(--success)' : 'var(--danger)',
                                        }}>
                                            {tr.message}
                                        </div>
                                    )}
                                </div>

                                <div style={{ display: 'flex', gap: 4 }}>
                                    <button className="btn btn-sm" onClick={() => testService(ak.service)}
                                        disabled={testing === ak.service || status === 'missing'}
                                        title="Test connection">
                                        {testing === ak.service ? <Loader size={13} className="spin" /> : <TestTube size={13} />}
                                    </button>
                                    {maskedVal && maskedVal !== '***' && (
                                        <button className="btn btn-sm" onClick={() => copyKey(ak.key)}>
                                            {copied === ak.key ? <Check size={13} /> : <Copy size={13} />}
                                        </button>
                                    )}
                                    <button className="btn btn-sm" onClick={() => { setEditing(ak.key); setEditVal(''); }}>
                                        <Edit3 size={13} />
                                    </button>
                                    {maskedVal && maskedVal !== '***' && (
                                        <button className="btn btn-sm btn-danger" onClick={() => deleteKey(ak)}>
                                            <Trash2 size={13} />
                                        </button>
                                    )}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}

            {tab === 'general' && (
                <div className="card">
                    <div className="card-title">{t('generalSettings')}</div>
                    <div style={{ color: 'var(--text-muted)' }}>Browser settings coming soon...</div>
                </div>
            )}

            {tab === 'system' && (
                <div className="card">
                    <div className="card-title">{t('systemInfo')}</div>
                    <div>Leomail v3.0</div>
                </div>
            )}
        </div>
    );
}
