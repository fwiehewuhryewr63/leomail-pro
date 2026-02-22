import React, { createContext, useContext, useState, useEffect } from 'react';
import { translations } from './translations';

const I18nContext = createContext();

export function I18nProvider({ children }) {
    const [lang, setLang] = useState(() => {
        return localStorage.getItem('leomail_lang') || 'ru';
    });

    useEffect(() => {
        localStorage.setItem('leomail_lang', lang);
    }, [lang]);

    const t = (key) => {
        return translations[lang]?.[key] || translations['en']?.[key] || key;
    };

    const toggleLang = () => {
        setLang(prev => prev === 'ru' ? 'en' : 'ru');
    };

    return (
        <I18nContext.Provider value={{ lang, setLang, t, toggleLang }}>
            {children}
        </I18nContext.Provider>
    );
}

export function useI18n() {
    const ctx = useContext(I18nContext);
    if (!ctx) throw new Error('useI18n must be used inside I18nProvider');
    return ctx;
}
