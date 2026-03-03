import React from 'react';
import { NavLink } from 'react-router-dom';
import {
    LayoutDashboard, Baby, Flame, Rocket,
    Shield, FileText, Users, Boxes, Settings,
    Link, Database, UserCircle, Terminal, Monitor,
    ScanSearch
} from 'lucide-react';

// Menu structure with logical groups (separator = null item)
const NAV_ITEMS = [
    // Group 1: Overview
    { to: '/', icon: LayoutDashboard, label: 'dashboard', end: true },
    { to: '/birth', icon: Baby, label: 'autoreg' },
    { to: '/validator', icon: ScanSearch, label: 'validator' },
    null, // separator
    // Group 2: Email Operations
    { to: '/warmup', icon: Flame, label: 'warm-up' },
    { to: '/campaigns', icon: Rocket, label: 'campaigns' },
    null, // separator
    // Group 3: Resources
    { to: '/farms', icon: Boxes, label: 'farms' },
    { to: '/accounts', icon: Users, label: 'accounts' },
    { to: '/names', icon: UserCircle, label: 'names' },
    { to: '/proxies', icon: Shield, label: 'proxies' },
    null, // separator
    // Group 4: Content
    { to: '/templates', icon: FileText, label: 'templates' },
    { to: '/links', icon: Link, label: 'links' },
    { to: '/databases', icon: Database, label: 'recipients' },
    null, // separator
    // Group 5: System
    { to: '/threads', icon: Terminal, label: 'threads' },
    { to: '/logs', icon: Monitor, label: 'logs' },
    { to: '/settings', icon: Settings, label: 'settings' },
];

export default function Sidebar({ status, updateAvailable }) {
    return (
        <div className="sidebar">
            {/* Logo */}
            <div className="sidebar-logo">
                <img src="/logo.png" alt="Leomail" className="sidebar-logo-img" />
            </div>

            {/* Nav */}
            <nav className="sidebar-nav">
                {NAV_ITEMS.map((item, idx) => {
                    if (item === null) {
                        return <div key={`sep-${idx}`} className="nav-separator" />;
                    }
                    return (
                        <NavLink key={item.to} to={item.to}
                            className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
                            end={item.end}
                            style={{ position: 'relative' }}>
                            <item.icon size={22} />
                            <span className="nav-label">{item.label}</span>
                            {item.label === 'settings' && updateAvailable && (
                                <span style={{
                                    position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                                    width: 8, height: 8, borderRadius: '50%', background: '#EF4444',
                                    animation: 'pulse 2s infinite',
                                }} />
                            )}
                        </NavLink>
                    );
                })}
            </nav>

            {/* Footer */}
            <div className="sidebar-footer">
                <div className={`status-dot ${status === 'online' ? 'online' : ''}`} />
                <span>{status === 'online' ? 'online' : 'offline'}</span>
            </div>
        </div>
    );
}
