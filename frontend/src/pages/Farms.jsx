import React, { useState, useEffect } from 'react';
import {
    Database, Plus, Download, Trash2, ChevronRight, Users, X,
    Activity, Calendar, Mail, AlertTriangle, TrendingUp, Merge, Upload
} from 'lucide-react';

import { API } from '../api';

export default function Farms() {
    const [farms, setFarms] = useState([]);
    const [showCreate, setShowCreate] = useState(false);
    const [newName, setNewName] = useState('');
    const [newDesc, setNewDesc] = useState('');
    const [farmDetail, setFarmDetail] = useState(null);
    const [detailTab, setDetailTab] = useState('accounts');
    const [selected, setSelected] = useState(new Set());
    const [showMerge, setShowMerge] = useState(false);
    const [mergeName, setMergeName] = useState('');
    const [showImport, setShowImport] = useState(false);
    const [importText, setImportText] = useState('');

    const toggleSelect = (id) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
    const toggleAll = () => setSelected(prev => prev.size === farms.length ? new Set() : new Set(farms.map(f => f.id)));
    const batchDelete = async () => {
        if (!confirm(`Удалить ${selected.size} ферм?`)) return;
        await fetch(`${API}/farms/batch-delete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids: [...selected] }) });
        setSelected(new Set()); load();
    };

    const mergeFarms = async () => {
        if (!mergeName.trim() || selected.size < 2) return;
        const res = await fetch(`${API}/farms/merge`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_farm_ids: [...selected], target_name: mergeName })
        });
        const d = await res.json();
        alert(`Объединено ${d.accounts_merged} аккаунтов в ферму "${mergeName}"`);
        setSelected(new Set()); setShowMerge(false); setMergeName(''); load();
    };

    const importAccounts = async () => {
        if (!importText.trim() || !farmDetail) return;
        const lines = importText.split('\n').filter(l => l.trim());
        const res = await fetch(`${API}/farms/${farmDetail.id}/import-accounts`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lines })
        });
        const d = await res.json();
        if (d.error) { alert(d.error); return; }
        alert(`Импортировано ${d.imported} аккаунтов (${Object.entries(d.providers || {}).map(([k, v]) => `${k}: ${v}`).join(', ')})`);
        setImportText(''); setShowImport(false);
        viewFarm(farmDetail.id);
    };

    const load = () => fetch(`${API}/farms/`).then(r => r.json()).then(setFarms).catch(() => { });
    useEffect(() => { load(); }, []);

    const createFarm = async () => {
        if (!newName.trim()) return;
        await fetch(`${API}/farms/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newName, description: newDesc }) });
        setNewName(''); setNewDesc(''); setShowCreate(false); load();
    };

    const deleteFarm = async (id) => {
        if (!confirm('Удалить ферму и все аккаунты?')) return;
        await fetch(`${API}/farms/${id}`, { method: 'DELETE' }); load();
    };

    const exportFarm = async (id, name) => {
        const res = await fetch(`${API}/farms/${id}/export`);
        const blob = await res.blob();
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${name}.zip`; a.click();
    };

    const viewFarm = async (id) => {
        const data = await (await fetch(`${API}/farms/${id}`)).json();
        setFarmDetail(data);
        setDetailTab('accounts');
    };

    const statusColors = {
        new: '#64748b', phase_1: '#f59e0b', phase_2: '#f97316', phase_3: '#ef4444',
        phase_4: '#e11d48', phase_5: '#a855f7', warmed: '#00ff41', sending: '#a78bfa',
        paused: '#94a3b8', dead: '#ef4444', banned: '#991b1b'
    };
    const statusLabels = {
        new: 'Новый', phase_1: 'Фаза 1', phase_2: 'Фаза 2', phase_3: 'Фаза 3',
        phase_4: 'Фаза 4', phase_5: 'Фаза 5', warmed: 'WARMED', sending: 'Рассылка',
        paused: 'Пауза', dead: 'Dead', banned: 'Banned'
    };

    const getAccountsByStatus = () => {
        if (!farmDetail?.accounts) return {};
        return farmDetail.accounts.reduce((acc, a) => {
            (acc[a.status] = acc[a.status] || []).push(a);
            return acc;
        }, {});
    };

    return (
        <div className="page">
            <h2 className="page-title"><Database size={22} /> Фермы</h2>

            <button className="btn btn-primary" onClick={() => setShowCreate(!showCreate)} style={{ marginBottom: 16 }}>
                <Plus size={14} /> Новая ферма
            </button>

            {showCreate && (
                <div className="card" style={{ marginBottom: 16 }}>
                    <div className="card-title">Создать ферму</div>
                    <div className="form-group">
                        <label className="form-label">Название</label>
                        <input className="form-input" value={newName} onChange={e => setNewName(e.target.value)} placeholder="Gmail US Farm..." />
                    </div>
                    <div className="form-group">
                        <label className="form-label">Описание</label>
                        <input className="form-input" value={newDesc} onChange={e => setNewDesc(e.target.value)} placeholder="Опционально..." />
                    </div>
                    <button className="btn btn-primary" onClick={createFarm}>Создать</button>
                </div>
            )}

            {farms.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: 48, color: '#006611' }}>
                    <Database size={36} style={{ opacity: 0.3, marginBottom: 12 }} /><br />Нет ферм. Создайте для организации аккаунтов.
                </div>
            ) : (
                <div style={{ display: 'grid', gap: 10 }}>
                    {/* Batch select bar */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.85em' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', color: 'var(--text-muted)' }}>
                            <input type="checkbox" checked={selected.size === farms.length && farms.length > 0} onChange={toggleAll} /> Выбрать всё
                        </label>
                        {selected.size > 0 && (<>
                            <button className="btn btn-danger btn-sm" onClick={batchDelete} style={{ marginLeft: 'auto' }}>
                                <Trash2 size={12} /> Удалить выбранные ({selected.size})
                            </button>
                            {selected.size >= 2 && (
                                <button className="btn btn-sm" onClick={() => setShowMerge(true)} style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                                    <Merge size={12} /> Объединить ({selected.size})
                                </button>
                            )}
                        </>)}
                    </div>
                    {farms.map(farm => (
                        <div key={farm.id} className="card card-clickable" onClick={() => viewFarm(farm.id)} style={{ border: selected.has(farm.id) ? '1px solid var(--danger)' : undefined }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                    <input type="checkbox" checked={selected.has(farm.id)} onChange={(e) => { e.stopPropagation(); toggleSelect(farm.id); }} onClick={(e) => e.stopPropagation()} style={{ accentColor: 'var(--danger)' }} />
                                    <div>
                                        <div style={{ fontWeight: 600, fontSize: '0.95em', display: 'flex', alignItems: 'center', gap: 8 }}>
                                            {farm.name}
                                            <span className="neon-tag neon-tag-cyan">{farm.accounts_count} аккаунтов</span>
                                        </div>
                                        {farm.description && <div style={{ fontSize: '0.72em', color: '#006611', marginTop: 2 }}>{farm.description}</div>}
                                    </div>
                                </div>
                                <ChevronRight size={16} style={{ color: '#006611' }} />
                            </div>
                            {/* Progress bar */}
                            <div style={{ marginTop: 12 }}>
                                <div style={{ width: '100%', height: 4, background: '#020502', borderRadius: 2, overflow: 'hidden' }}>
                                    <div style={{
                                        width: `${farm.warmup_progress}%`, height: '100%',
                                        background: 'linear-gradient(90deg, #00ff41, #00ff41)', borderRadius: 2,
                                        boxShadow: '0 0 8px rgba(0,255,65,0.3)', transition: 'width 0.5s ease'
                                    }} />
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65em', color: '#006611', marginTop: 4 }}>
                                    <span>{farm.warmup_progress}% прогрето</span>
                                    <span>{Object.entries(farm.providers || {}).map(([k, v]) => `${k}(${v})`).join(' · ')}</span>
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: 6, marginTop: 10 }} onClick={e => e.stopPropagation()}>
                                <button className="btn btn-sm" onClick={() => exportFarm(farm.id, farm.name)}><Download size={12} /> Экспорт</button>
                                <button className="btn btn-sm btn-danger" onClick={() => deleteFarm(farm.id)}><Trash2 size={12} /></button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Farm detail modal */}
            {farmDetail && (
                <div className="modal-overlay" onClick={() => setFarmDetail(null)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 800, padding: 24 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                            <div>
                                <div style={{ fontWeight: 700, fontSize: '1.1em' }}>{farmDetail.name}</div>
                                <div style={{ fontSize: '0.72em', color: '#006611' }}>{farmDetail.accounts?.length || 0} аккаунтов</div>
                            </div>
                            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                <button className="btn btn-sm" onClick={() => setShowImport(true)} style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                                    <Upload size={12} /> Импорт аккаунтов
                                </button>
                                <button className="btn btn-sm" onClick={() => setFarmDetail(null)}><X size={14} /></button>
                            </div>
                        </div>

                        {/* Stats summary */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 6, marginBottom: 16 }}>
                            {Object.entries(getAccountsByStatus()).map(([status, accs]) => (
                                <div key={status} style={{
                                    textAlign: 'center', padding: 8, borderRadius: 8,
                                    background: `${statusColors[status]}06`, border: `1px solid ${statusColors[status]}12`
                                }}>
                                    <div style={{ fontSize: '1.2em', fontWeight: 700, color: statusColors[status] }}>{accs.length}</div>
                                    <div style={{ fontSize: '0.55em', color: '#006611', letterSpacing: 1 }}>{statusLabels[status]?.toUpperCase()}</div>
                                </div>
                            ))}
                        </div>

                        {/* Tabs */}
                        <div style={{ display: 'flex', gap: 4, marginBottom: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: 3 }}>
                            {['accounts', 'timeline'].map(t => (
                                <button key={t} onClick={() => setDetailTab(t)} style={{
                                    padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
                                    fontSize: '0.72em', fontWeight: 600, fontFamily: 'inherit',
                                    background: detailTab === t ? 'rgba(0,255,65,0.1)' : 'transparent',
                                    color: detailTab === t ? '#00ff41' : '#006611'
                                }}>
                                    {t === 'accounts' ? 'Аккаунты' : 'Timeline'}
                                </button>
                            ))}
                        </div>

                        {detailTab === 'accounts' && farmDetail.accounts?.map(acc => (
                            <div key={acc.id} style={{
                                padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.03)',
                                display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.82em'
                            }}>
                                <div style={{ flex: 1 }}>
                                    <div style={{ color: '#e8ecf4', fontWeight: 500 }}>{acc.email}</div>
                                    <div style={{ fontSize: '0.75em', color: '#006611', marginTop: 2, display: 'flex', gap: 10 }}>
                                        <span>{acc.provider}</span>
                                        <span>{acc.geo || '?'}</span>
                                        <span>День {acc.warmup_day}</span>
                                        {acc.sent_count > 0 && <span><Mail size={10} /> {acc.sent_count} отп.</span>}
                                    </div>
                                </div>
                                <span style={{
                                    padding: '3px 10px', borderRadius: 20, fontSize: '0.68em', fontWeight: 600,
                                    background: `${statusColors[acc.status]}12`, color: statusColors[acc.status]
                                }}>
                                    {statusLabels[acc.status]?.toUpperCase() || acc.status}
                                </span>
                            </div>
                        ))}

                        {detailTab === 'timeline' && (
                            <div style={{ padding: '10px 0' }}>
                                <div style={{ fontSize: '0.78em', color: '#006611', textAlign: 'center', padding: 20 }}>
                                    <Activity size={24} style={{ opacity: 0.3, marginBottom: 8 }} /><br />
                                    Timeline будет заполняться по мере работы ферм
                                </div>
                            </div>
                        )}
                        {/* Import accounts modal */}
                        {showImport && (
                            <div style={{ marginTop: 12, padding: 16, background: 'rgba(0,255,65,0.03)', borderRadius: 8, border: '1px solid rgba(0,255,65,0.1)' }}>
                                <div style={{ fontWeight: 600, fontSize: '0.85em', marginBottom: 8 }}>Импорт аккаунтов</div>
                                <div style={{ fontSize: '0.7em', color: '#006611', marginBottom: 8 }}>
                                    Форматы: email:pass или email:pass:recovery_email:recovery_pass
                                </div>
                                <textarea className="form-input" rows={6} value={importText} onChange={e => setImportText(e.target.value)}
                                    placeholder={'user@gmail.com:MyPass123\nuser@yahoo.com:Pass456:recovery@mail.com:RecoveryPass'}
                                    style={{ fontFamily: 'monospace', fontSize: '0.78em' }} />
                                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                                    <button className="btn btn-primary btn-sm" onClick={importAccounts} disabled={!importText.trim()}>
                                        <Upload size={12} /> Импортировать {importText.trim() ? `(${importText.split('\n').filter(l => l.trim()).length})` : ''}
                                    </button>
                                    <button className="btn btn-sm" onClick={() => setShowImport(false)}>Отмена</button>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            )
            }

            {/* Merge modal */}
            {showMerge && (
                <div className="modal-overlay" onClick={() => setShowMerge(false)}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 400, padding: 24 }}>
                        <div style={{ fontWeight: 700, fontSize: '1em', marginBottom: 12 }}>
                            <Merge size={16} /> Объединить {selected.size} ферм
                        </div>
                        <div className="form-group">
                            <label className="form-label">Название новой фермы</label>
                            <input className="form-input" value={mergeName} onChange={e => setMergeName(e.target.value)}
                                placeholder="Например: Combined Farm" autoFocus />
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                            <button className="btn btn-primary" onClick={mergeFarms} disabled={!mergeName.trim()}>
                                <Merge size={14} /> Объединить
                            </button>
                            <button className="btn" onClick={() => setShowMerge(false)}>Отмена</button>
                        </div>
                    </div>
                </div>
            )}
        </div >
    );
}
