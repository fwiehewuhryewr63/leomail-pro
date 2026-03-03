import React from 'react';

/* ═══════════════════════════════════════════════════════════
   Email Provider Logo Images
   Uses generated brand-style PNG logos from /providers/
   ═══════════════════════════════════════════════════════════ */

const PROVIDER_IDS = ['gmail', 'yahoo', 'aol', 'outlook', 'hotmail', 'protonmail', 'yahoo_aol', 'outlook_hotmail'];

// Combined IDs map to a base provider logo
const LOGO_MAP = { yahoo_aol: 'yahoo', outlook_hotmail: 'outlook' };

export function ProviderLogo({ provider, size = 40 }) {
    if (!provider || !PROVIDER_IDS.includes(provider)) {
        return <span style={{ fontSize: size * 0.6, display: 'flex', alignItems: 'center', justifyContent: 'center', width: size, height: size }}>📧</span>;
    }
    const logoFile = LOGO_MAP[provider] || provider;
    return (
        <img
            src={`/providers/${logoFile}.png`}
            alt={provider}
            width={size}
            height={size}
            style={{ borderRadius: size * 0.2, objectFit: 'cover' }}
        />
    );
}
