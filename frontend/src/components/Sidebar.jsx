import React from 'react';
import { NavLink } from 'react-router-dom';
import {
    LayoutDashboard, Baby, Flame, Rocket,
    Shield, FileText, Users, Boxes, Settings,
    Link, Database, UserCircle, Terminal, Monitor,
    ScanSearch
} from 'lucide-react';

const NAV_ITEMS = [
    // Overview
    { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
    { to: '/birth', icon: Baby, label: 'Autoreg' },
    { to: '/validator', icon: ScanSearch, label: 'Validator' },
    null,
    // Email Operations
    { to: '/warmup', icon: Flame, label: 'Warm-up' },
    { to: '/campaigns', icon: Rocket, label: 'Campaigns' },
    null,
    // Resources
    { to: '/farms', icon: Boxes, label: 'Farms' },
    { to: '/accounts', icon: Users, label: 'Accounts' },
    { to: '/names', icon: UserCircle, label: 'Names' },
    { to: '/proxies', icon: Shield, label: 'Proxies' },
    null,
    // Content
    { to: '/templates', icon: FileText, label: 'Templates' },
    { to: '/links', icon: Link, label: 'Links' },
    { to: '/databases', icon: Database, label: 'Recipients' },
    null,
    // System
    { to: '/threads', icon: Terminal, label: 'Threads' },
    { to: '/logs', icon: Monitor, label: 'Logs' },
    { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function Sidebar({ status, updateAvailable }) {
    return (
        <div className="sidebar">
            {/* Logo */}
            <div className="sidebar-logo">
                <img src="/logo.png" alt="Leomail" className="sidebar-logo-img" />
                <span className="sidebar-brand">Leomail</span>
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
                            end={item.end}>
                            <item.icon size={18} />
                            <span className="nav-label">{item.label}</span>
                            {item.label === 'Settings' && updateAvailable && (
                                <span className="nav-update-dot" />
                            )}
                        </NavLink>
                    );
                })}
            </nav>

            {/* Footer */}
            <div className="sidebar-footer">
                <div className={`status-dot ${status === 'online' ? 'online' : ''}`} />
                <span>{status === 'online' ? 'Connected' : 'Offline'}</span>
            </div>
        </div>
    );
}
