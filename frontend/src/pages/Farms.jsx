import React, { useState, useEffect } from 'react';
import {
    Database, Plus, Download, Trash2, ChevronRight, Users, X,
    Activity, Calendar, Mail, AlertTriangle, TrendingUp, Merge, Upload, ArrowRight, MinusCircle, FileText
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
    const [selectedAccounts, setSelectedAccounts] = useState(new Set());
    const [showMoveTo, setShowMoveTo] = useState(false);
    const [emptyFarmIds, setEmptyFarmIds] = useState([]);  // farms to prompt for deletion

    const toggleSelect = (id) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });
    const toggleAll = () => setSelected(prev => prev.size === farms.length ? new Set() : new Set(farms.map(f => f.id)));
    const batchDelete = async () => {
        if (!confirm(`Delete ${selected.size} farms?`)) return;
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
        if (d.empty_farms?.length > 0) {
            setEmptyFarmIds(d.empty_farms);
        } else {
            alert(`Merged ${d.accounts_merged} accounts into farm "${mergeName}"`);
        }
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
        alert(`Imported ${d.imported} accounts (${Object.entries(d.providers || {}).map(([k, v]) => `${k}: ${v}`).join(', ')})`);
        setImportText(''); setShowImport(false);
        viewFarm(farmDetail.id);
    };

    const moveAccounts = async (targetFarmId) => {
        if (!farmDetail || selectedAccounts.size === 0) return;
        const res = await fetch(`${API}/farms/${farmDetail.id}/move-accounts`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_ids: [...selectedAccounts], target_farm_id: targetFarmId })
        });
        const d = await res.json();
        if (d.error) { alert(d.error); return; }
        setSelectedAccounts(new Set()); setShowMoveTo(false);
        if (d.source_empty) {
            setEmptyFarmIds([farmDetail.id]);
        }
        viewFarm(farmDetail.id); load();
    };

    const removeFromFarm = async () => {
        if (!farmDetail || selectedAccounts.size === 0) return;
        if (!confirm(`Remove ${selectedAccounts.size} accounts from this farm?`)) return;
        const res = await fetch(`${API}/farms/${farmDetail.id}/remove-accounts`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ account_ids: [...selectedAccounts] })
        });
        const d = await res.json();
        setSelectedAccounts(new Set());
        if (d.source_empty) {
            setEmptyFarmIds([farmDetail.id]);
        }
        viewFarm(farmDetail.id); load();
    };

    const deleteEmptyFarms = async () => {
        for (const id of emptyFarmIds) {
            await fetch(`${API}/farms/${id}`, { method: 'DELETE' });
        }
        setEmptyFarmIds([]); setFarmDetail(null); load();
    };

    const load = () => fetch(`${API}/farms/`).then(r => r.json()).then(setFarms).catch(() => { });
    useEffect(() => { load(); }, []);

    const createFarm = async () => {
        if (!newName.trim()) return;
        await fetch(`${API}/farms/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newName, description: newDesc }) });
        setNewName(''); setNewDesc(''); setShowCreate(false); load();
    };

    const deleteFarm = async (id) => {
        if (!confirm('Delete farm and all accounts?')) return;
        await fetch(`${API}/farms/${id}`, { method: 'DELETE' }); load();
    };

    const exportFarm = async (id, name) => {
        const res = await fetch(`${API}/farms/${id}/export`);
        const blob = await res.blob();
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${name}.zip`; a.click();
    };

    const exportFarmText = async (id, name) => {
        const res = await fetch(`${API}/farms/${id}/export-text`);
        const blob = await res.blob();
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${name}.txt`; a.click();
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
        new: 'New', phase_1: 'Phase 1', phase_2: 'Phase 2', phase_3: 'Phase 3',
        phase_4: 'Phase 4', phase_5: 'Phase 5', warmed: 'WARMED', sending: 'Sending',
        paused: 'Paused', dead: 'Dead', banned: 'Banned'
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
            <div style={{ fontSize: '0.65em', fontWeight: 700, color: 'var(--text-muted)', letterSpacing: 2, textTransform: 'uppercase', marginBottom: 2 }}>FARMS</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h2 className="page-title" style={{ margin: 0, borderBottom: '2px solid var(--accent)', paddingBottom: 8, display: 'inline-block' }}>
                    <Database size={22} style={{ verticalAlign: 'middle', marginRight: 8 }} /> Farms
                </h2>
                <button onClick={() => setShowCreate(!showCreate)} style={{
                    display: 'flex', alignItems: 'center', gap: 6, padding: '9px 20px',
                    fontWeight: 700, fontSize: '0.88em', border: 'none', borderRadius: 8,
                    cursor: 'pointer', background: 'var(--accent)', color: '#000',
                    fontFamily: 'inherit', transition: 'all 0.2s',
                }}>
                    <Plus size={16} /> New Farm
                </button>
            </div>

            {showCreate && (
                <div className="card" style={{ marginBottom: 14, padding: '16px 20px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '2fr 2fr auto', gap: 10, alignItems: 'end' }}>
                        <div>
                            <label style={{ fontSize: '0.72em', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--accent)', marginBottom: 5, display: 'block' }}>Farm Name</label>
                            <input className="form-input" value={newName} onChange={e => setNewName(e.target.value)} placeholder="Gmail US Farm..." />
                        </div>
                        <div>
                            <label style={{ fontSize: '0.72em', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--text-muted)', marginBottom: 5, display: 'block' }}>Description</label>
                            <input className="form-input" value={newDesc} onChange={e => setNewDesc(e.target.value)} placeholder="Optional..." />
                        </div>
                        <button onClick={createFarm} disabled={!newName.trim()} style={{
                            padding: '9px 24px', fontWeight: 700, fontSize: '0.88em', border: 'none', borderRadius: 8,
                            cursor: newName.trim() ? 'pointer' : 'not-allowed',
                            background: newName.trim() ? 'var(--accent)' : 'rgba(255,255,255,0.06)',
                            color: newName.trim() ? '#000' : 'var(--text-muted)',
                            fontFamily: 'inherit', transition: 'all 0.2s',
                        }}>Create</button>
                    </div>
                </div>
            )}

            {farms.length === 0 ? (
                <div className="card" style={{ textAlign: 'center', padding: '40px 24px', color: 'var(--text-muted)' }}>
                    <Database size={40} style={{ opacity: 0.2, marginBottom: 10 }} /><br />
                    <div style={{ fontSize: '1em', fontWeight: 600, marginBottom: 4 }}>No Farms</div>
                    <div style={{ fontSize: '0.82em' }}>Create a farm to organize your accounts</div>
                </div>
            ) : (
                <div style={{ display: 'grid', gap: 10 }}>
                    {/* Batch select bar */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.85em' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', color: 'var(--text-muted)' }}>
                            <input type="checkbox" checked={selected.size === farms.length && farms.length > 0} onChange={toggleAll} /> Select All
                        </label>
                        {selected.size > 0 && (<>
                            <button className="btn btn-danger btn-sm" onClick={batchDelete} style={{ marginLeft: 'auto' }}>
                                <Trash2 size={12} /> Delete Selected ({selected.size})
                            </button>
                            {selected.size >= 2 && (
                                <button className="btn btn-sm" onClick={() => setShowMerge(true)} style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                                    <Merge size={12} /> Merge ({selected.size})
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
                                            <span style={{ fontSize: '0.72em', fontWeight: 600, padding: '2px 8px', borderRadius: 4, background: 'rgba(6,182,212,0.12)', color: '#06b6d4' }}>{farm.accounts_count} accounts</span>
                                        </div>
                                        {farm.description && <div style={{ fontSize: '0.72em', color: 'var(--text-muted)', marginTop: 2 }}>{farm.description}</div>}
                                    </div>
                                </div>
                                <ChevronRight size={16} style={{ color: 'var(--text-muted)' }} />
                            </div>
                            {/* Phase status badges + providers */}
                            <div style={{ marginTop: 10, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 6 }}>
                                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                    {Object.entries(farm.statuses || {}).filter(([, count]) => count > 0).map(([status, count]) => {
                                        const c = statusColors[status] || '#888';
                                        return (
                                            <span key={status} style={{
                                                fontSize: '0.62em', fontWeight: 700, padding: '2px 7px', borderRadius: 4,
                                                background: `${c}18`, color: c, letterSpacing: 0.5,
                                            }}>
                                                {statusLabels[status]?.toUpperCase() || status} {count}
                                            </span>
                                        );
                                    })}
                                    {(!farm.status_breakdown || Object.keys(farm.status_breakdown).length === 0) && (
                                        <span style={{ fontSize: '0.62em', color: 'var(--text-muted)' }}>No accounts</span>
                                    )}
                                </div>
                                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                    {Object.entries(farm.providers || {}).map(([k, v]) => (
                                        <span key={k} style={{
                                            fontSize: '0.6em', fontWeight: 600, padding: '2px 6px', borderRadius: 3,
                                            background: 'rgba(255,255,255,0.05)', color: 'var(--text-muted)',
                                        }}>{k}({v})</span>
                                    ))}
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: 6, marginTop: 10 }} onClick={e => e.stopPropagation()}>
                                <button className="btn btn-sm" onClick={() => exportFarm(farm.id, farm.name)}><Download size={12} /> ZIP</button>
                                <button className="btn btn-sm" onClick={() => exportFarmText(farm.id, farm.name)}><FileText size={12} /> TXT</button>
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
                                <div style={{ fontSize: '0.72em', color: 'var(--text-muted)' }}>{farmDetail.accounts?.length || 0} accounts</div>
                            </div>
                            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                <button className="btn btn-sm" onClick={() => setShowImport(true)} style={{ borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                                    <Upload size={12} /> Import Accounts
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
                                    <div style={{ fontSize: '0.55em', color: 'var(--text-muted)', letterSpacing: 1 }}>{statusLabels[status]?.toUpperCase()}</div>
                                </div>
                            ))}
                        </div>

                        {/* Tabs */}
                        <div style={{ display: 'flex', gap: 4, marginBottom: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: 3 }}>
                            {['accounts', 'timeline'].map(t => (
                                <button key={t} onClick={() => setDetailTab(t)} style={{
                                    padding: '6px 14px', borderRadius: 6, border: 'none', cursor: 'pointer',
                                    fontSize: '0.72em', fontWeight: 600, fontFamily: 'inherit',
                                    background: detailTab === t ? 'rgba(16,185,129,0.1)' : 'transparent',
                                    color: detailTab === t ? 'var(--accent)' : 'var(--text-muted)'
                                }}>
                                    {t === 'accounts' ? 'Accounts' : 'Timeline'}
                                </button>
                            ))}
                        </div>

                        {detailTab === 'accounts' && (
                            <>
                                {/* Account actions bar */}
                                {farmDetail.accounts?.length > 0 && (
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, fontSize: '0.78em' }}>
                                        <label style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', color: 'var(--text-muted)' }}>
                                            <input type="checkbox"
                                                checked={selectedAccounts.size === farmDetail.accounts.length && farmDetail.accounts.length > 0}
                                                onChange={() => setSelectedAccounts(prev => prev.size === farmDetail.accounts.length ? new Set() : new Set(farmDetail.accounts.map(a => a.id)))}
                                            /> Select All
                                        </label>
                                        {selectedAccounts.size > 0 && (
                                            <>
                                                <button className="btn btn-sm" onClick={() => setShowMoveTo(!showMoveTo)}
                                                    style={{ marginLeft: 'auto', borderColor: 'var(--accent)', color: 'var(--accent)' }}>
                                                    <ArrowRight size={12} /> Move ({selectedAccounts.size})
                                                </button>
                                                <button className="btn btn-sm btn-danger" onClick={removeFromFarm}>
                                                    <MinusCircle size={12} /> Remove
                                                </button>
                                            </>
                                        )}
                                    </div>
                                )}
                                {/* Move to farm dropdown */}
                                {showMoveTo && (
                                    <div style={{ marginBottom: 10, padding: 10, background: 'rgba(16,185,129,0.04)', borderRadius: 8, border: '1px solid rgba(16,185,129,0.12)' }}>
                                        <div style={{ fontSize: '0.75em', fontWeight: 600, color: 'var(--accent)', marginBottom: 6 }}>Move to farm:</div>
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                                            {farms.filter(f => f.id !== farmDetail.id).map(f => (
                                                <button key={f.id} className="btn btn-sm" onClick={() => moveAccounts(f.id)}
                                                    style={{ fontSize: '0.75em' }}>
                                                    {f.name} ({f.account_count})
                                                </button>
                                            ))}
                                            {farms.filter(f => f.id !== farmDetail.id).length === 0 && (
                                                <span style={{ fontSize: '0.75em', color: 'var(--text-muted)' }}>No other farms available</span>
                                            )}
                                        </div>
                                    </div>
                                )}
                                {/* Account list */}
                                {farmDetail.accounts?.map(acc => (
                                    <div key={acc.id} style={{
                                        padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.03)',
                                        display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.82em',
                                        background: selectedAccounts.has(acc.id) ? 'rgba(16,185,129,0.04)' : 'transparent',
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
                                            <input type="checkbox" checked={selectedAccounts.has(acc.id)}
                                                onChange={() => setSelectedAccounts(prev => { const s = new Set(prev); s.has(acc.id) ? s.delete(acc.id) : s.add(acc.id); return s; })}
                                                style={{ accentColor: 'var(--accent)' }} />
                                            <div>
                                                <div style={{ color: '#e8ecf4', fontWeight: 500 }}>{acc.email}</div>
                                                <div style={{ fontSize: '0.75em', color: 'var(--text-muted)', marginTop: 2, display: 'flex', gap: 10 }}>
                                                    <span style={{ color: '#06b6d4' }}>{acc.provider}</span>
                                                    <span>{acc.geo || '?'}</span>
                                                    <span>Day {acc.warmup_day}</span>
                                                    {acc.sent_count > 0 && <span><Mail size={10} /> <span style={{ color: '#f59e0b' }}>{acc.sent_count}</span> sent</span>}
                                                </div>
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
                            </>
                        )}

                        {detailTab === 'timeline' && (
                            <div style={{ padding: '10px 0' }}>
                                <div style={{ fontSize: '0.78em', color: 'var(--text-muted)', textAlign: 'center', padding: 20 }}>
                                    <Activity size={24} style={{ opacity: 0.3, marginBottom: 8 }} /><br />
                                    Timeline will populate as farms process
                                </div>
                            </div>
                        )}
                        {/* Import accounts modal */}
                        {showImport && (
                            <div style={{ marginTop: 12, padding: 16, background: 'rgba(16,185,129,0.03)', borderRadius: 8, border: '1px solid rgba(16,185,129,0.1)' }}>
                                <div style={{ fontWeight: 600, fontSize: '0.85em', marginBottom: 8, color: 'var(--accent)' }}>Import Accounts</div>
                                <div style={{ fontSize: '0.7em', color: 'var(--text-muted)', marginBottom: 8 }}>
                                    Formats: email:pass or email:pass:recovery_email:recovery_pass
                                </div>
                                <textarea className="form-input" rows={6} value={importText} onChange={e => setImportText(e.target.value)}
                                    placeholder={'user@gmail.com:MyPass123\nuser@yahoo.com:Pass456:recovery@mail.com:RecoveryPass'}
                                    style={{ fontFamily: 'monospace', fontSize: '0.78em' }} />
                                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                                    <button className="btn btn-primary btn-sm" onClick={importAccounts} disabled={!importText.trim()}>
                                        <Upload size={12} /> Import {importText.trim() ? `(${importText.split('\n').filter(l => l.trim()).length})` : ''}
                                    </button>
                                    <button className="btn btn-sm" onClick={() => setShowImport(false)}>Cancel</button>
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
                            <Merge size={16} /> Merge {selected.size} Farms
                        </div>
                        <div className="form-group">
                            <label className="form-label">New Farm Name</label>
                            <input className="form-input" value={mergeName} onChange={e => setMergeName(e.target.value)}
                                placeholder="E.g.: Combined Farm" autoFocus />
                        </div>
                        <div style={{ display: 'flex', gap: 8 }}>
                            <button className="btn btn-primary" onClick={mergeFarms} disabled={!mergeName.trim()}>
                                <Merge size={14} /> Merge
                            </button>
                            <button className="btn" onClick={() => setShowMerge(false)}>Cancel</button>
                        </div>
                    </div>
                </div>
            )}
            {/* Empty farm cleanup dialog */}
            {emptyFarmIds.length > 0 && (
                <div className="modal-overlay" onClick={() => setEmptyFarmIds([])}>
                    <div className="card modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: 400, padding: 24, textAlign: 'center' }}>
                        <AlertTriangle size={32} style={{ color: '#f59e0b', marginBottom: 10 }} />
                        <div style={{ fontWeight: 700, fontSize: '1em', marginBottom: 8 }}>
                            {emptyFarmIds.length === 1 ? 'Farm is now empty' : `${emptyFarmIds.length} farms are now empty`}
                        </div>
                        <div style={{ fontSize: '0.82em', color: 'var(--text-muted)', marginBottom: 16 }}>
                            All accounts have been moved. Delete {emptyFarmIds.length === 1 ? 'this empty farm' : 'these empty farms'}?
                        </div>
                        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
                            <button className="btn btn-danger" onClick={deleteEmptyFarms}>
                                <Trash2 size={14} /> Delete
                            </button>
                            <button className="btn" onClick={() => setEmptyFarmIds([])}>
                                Keep
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div >
    );
}
