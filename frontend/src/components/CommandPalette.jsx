import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    LayoutDashboard, Baby, Rocket, Shield, Boxes, Users,
    FileText, Link, Database, UserCircle, Terminal, Monitor,
    Settings, Search
} from 'lucide-react';

const COMMANDS = [
    { id: 'dash', label: 'Dashboard', icon: LayoutDashboard, path: '/', section: 'Навигация' },
    { id: 'birth', label: 'Авторегистрация', icon: Baby, path: '/birth', section: 'Навигация' },
    { id: 'camp', label: 'Компании', icon: Rocket, path: '/campaigns', section: 'Навигация' },
    { id: 'proxy', label: 'Прокси', icon: Shield, path: '/proxies', section: 'Навигация' },
    { id: 'farms', label: 'Фермы', icon: Boxes, path: '/farms', section: 'Навигация' },
    { id: 'accs', label: 'Аккаунты', icon: Users, path: '/accounts', section: 'Навигация' },
    { id: 'tmpl', label: 'Шаблоны', icon: FileText, path: '/templates', section: 'Навигация' },
    { id: 'links', label: 'Ссылки', icon: Link, path: '/links', section: 'Навигация' },
    { id: 'dbs', label: 'Базы получателей', icon: Database, path: '/databases', section: 'Навигация' },
    { id: 'names', label: 'Имена', icon: UserCircle, path: '/names', section: 'Навигация' },
    { id: 'threads', label: 'Потоки', icon: Terminal, path: '/threads', section: 'Система' },
    { id: 'logs', label: 'Логи', icon: Monitor, path: '/logs', section: 'Система' },
    { id: 'settings', label: 'Настройки', icon: Settings, path: '/settings', section: 'Система' },
];

export default function CommandPalette({ isOpen, onClose }) {
    const [query, setQuery] = useState('');
    const [activeIndex, setActiveIndex] = useState(0);
    const inputRef = useRef(null);
    const navigate = useNavigate();

    const filtered = COMMANDS.filter(cmd =>
        cmd.label.toLowerCase().includes(query.toLowerCase()) ||
        cmd.id.includes(query.toLowerCase())
    );

    useEffect(() => {
        if (isOpen && inputRef.current) {
            inputRef.current.focus();
        }
    }, [isOpen]);

    // Reset query/index when opened
    const prevOpen = useRef(false);
    if (isOpen && !prevOpen.current) {
        // Just opened — reset state synchronously (before render)
        if (query !== '') setQuery('');
        if (activeIndex !== 0) setActiveIndex(0);
    }
    prevOpen.current = isOpen;

    const handleSelect = useCallback((cmd) => {
        navigate(cmd.path);
        onClose();
    }, [navigate, onClose]);

    const handleKeyDown = useCallback((e) => {
        if (e.key === 'Escape') {
            onClose();
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActiveIndex(i => Math.min(i + 1, filtered.length - 1));
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActiveIndex(i => Math.max(i - 1, 0));
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (filtered[activeIndex]) handleSelect(filtered[activeIndex]);
        }
    }, [filtered, activeIndex, handleSelect, onClose]);

    if (!isOpen) return null;

    return (
        <div className="command-palette-overlay" onClick={onClose}>
            <div className="command-palette" onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 20px', borderBottom: '1px solid var(--border-default)' }}>
                    <Search size={16} style={{ opacity: 0.5, flexShrink: 0 }} />
                    <input
                        ref={inputRef}
                        className="command-palette-input"
                        placeholder="Поиск по страницам..."
                        value={query}
                        onChange={e => { setQuery(e.target.value); setActiveIndex(0); }}
                        onKeyDown={handleKeyDown}
                        style={{ border: 'none', borderBottom: 'none', paddingLeft: 0 }}
                    />
                    <span className="command-palette-shortcut">ESC</span>
                </div>
                <div className="command-palette-results">
                    {filtered.length === 0 && (
                        <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.88em' }}>
                            Ничего не найдено
                        </div>
                    )}
                    {filtered.map((cmd, i) => (
                        <div
                            key={cmd.id}
                            className={`command-palette-item ${i === activeIndex ? 'active' : ''}`}
                            onClick={() => handleSelect(cmd)}
                            onMouseEnter={() => setActiveIndex(i)}
                        >
                            <cmd.icon size={16} />
                            <span>{cmd.label}</span>
                            <span style={{ marginLeft: 'auto', fontSize: '0.72em', color: 'var(--text-muted)' }}>{cmd.section}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
