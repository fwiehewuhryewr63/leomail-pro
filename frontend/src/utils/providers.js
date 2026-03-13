/**
 * Provider Colors — Single Source of Truth
 * 
 * All provider brand colors are defined here.
 * CSS classes (.provider-gmail etc.) use these same values.
 * Import this instead of hardcoding hex colors in components.
 */

export const PROVIDER_COLORS = {
    gmail: '#EA4335',
    yahoo: '#6001D2',
    aol: '#FF6B00',
    outlook: '#0078D4',
    hotmail: '#0078D4',
    protonmail: '#6D4AFF',
    webde: '#FFC107',
};

/**
 * Get provider color by ID. Returns fallback gray for unknown providers.
 */
export function providerColor(id) {
    return PROVIDER_COLORS[id] || '#888';
}

/**
 * Compute rgba background from provider hex color.
 * @param {string} id - provider ID
 * @param {number} opacity - 0-1 (default 0.15)
 */
export function providerBg(id, opacity = 0.15) {
    const hex = PROVIDER_COLORS[id] || '#888888';
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${opacity})`;
}

/**
 * Map email domain to provider color.
 * Used in Dashboard Live Activity to color-code emails.
 */
const DOMAIN_MAP = [
    ['gmail', 'gmail'],
    ['yahoo', 'yahoo'],
    ['outlook', 'outlook'],
    ['hotmail', 'hotmail'],
    ['proton', 'protonmail'],
    ['aol', 'aol'],
    ['web.de', 'webde'],
];

export function domainToColor(domain) {
    if (!domain) return 'var(--text-secondary)';
    const lower = domain.toLowerCase();
    for (const [pattern, providerId] of DOMAIN_MAP) {
        if (lower.includes(pattern)) return PROVIDER_COLORS[providerId];
    }
    return 'var(--text-secondary)';
}

/**
 * Provider column configs for Proxies page badges.
 * label: column header text
 * providerKey: key to map into PROVIDER_COLORS
 * dataKey: key suffix for proxy data (use_KEY, fail_KEY)
 * limitKey: key in proxyLimits state
 */
export const PROXY_COLUMNS = [
    { label: 'G', providerKey: 'gmail', dataKey: 'G', failKey: 'fail_G', limitKey: 'G', defaultLimit: 1, cooldownKeys: ['gmail'] },
    { label: 'Y/A', providerKey: 'yahoo', dataKey: 'YA', failKey: 'fail_YA', limitKey: 'YA', defaultLimit: 3, cooldownKeys: ['yahoo', 'aol'] },
    { label: 'O/H', providerKey: 'outlook', dataKey: 'OH', failKey: 'fail_OH', limitKey: 'OH', defaultLimit: 3, cooldownKeys: ['outlook', 'hotmail'] },
    { label: 'P', providerKey: 'protonmail', dataKey: 'PT', failKey: 'fail_PT', limitKey: 'PT', defaultLimit: 3, cooldownKeys: ['protonmail'] },
    { label: 'WD', providerKey: 'webde', dataKey: 'WD', failKey: 'fail_WD', limitKey: 'WD', defaultLimit: 3, cooldownKeys: ['webde'] },
];

/**
 * Short provider labels for compact UI badges (e.g. cooldown pills).
 */
export const PROVIDER_SHORT = {
    gmail: 'G', yahoo: 'YA', aol: 'YA',
    outlook: 'OH', hotmail: 'OH',
    protonmail: 'P', webde: 'WD',
};
