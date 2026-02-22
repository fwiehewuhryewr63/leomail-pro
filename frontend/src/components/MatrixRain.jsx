import React, { useRef, useEffect } from 'react';

export default function MatrixRain() {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d', { alpha: false });

        let w, h, columns, drops, speeds;

        const resize = () => {
            w = canvas.width = window.innerWidth;
            h = canvas.height = window.innerHeight;
            columns = Math.floor(w / 16);
            drops = new Array(columns).fill(0).map(() => Math.random() * -50);
            speeds = new Array(columns).fill(0).map(() => 0.4 + Math.random() * 0.6);
        };
        resize();
        window.addEventListener('resize', resize);

        const chars = 'アイウエオカキクケコ0123456789LEOMAIL';
        const fontSize = 16;
        let frame = 0;

        const draw = () => {
            ctx.fillStyle = 'rgba(0, 0, 0, 0.08)';
            ctx.fillRect(0, 0, w, h);
            ctx.font = `${fontSize}px monospace`;
            ctx.shadowBlur = 0; // No shadow — saves GPU

            for (let i = 0; i < columns; i++) {
                // Skip ~40% of columns each frame for performance
                if ((i + frame) % 3 === 0) continue;

                const y = drops[i] * fontSize;
                const char = chars[(Math.random() * chars.length) | 0];

                ctx.fillStyle = '#00ff41';
                ctx.fillText(char, i * fontSize, y);

                drops[i] += speeds[i];
                if (y > h && Math.random() > 0.97) {
                    drops[i] = 0;
                }
            }
            frame++;
        };

        // 150ms = ~6.7 FPS (was 80ms = 12.5 FPS) — 46% less CPU
        const interval = setInterval(draw, 150);

        return () => {
            clearInterval(interval);
            window.removeEventListener('resize', resize);
        };
    }, []);

    return (
        <canvas
            ref={canvasRef}
            id="matrix-rain"
            style={{
                position: 'fixed',
                top: 0, left: 0,
                width: '100%', height: '100%',
                zIndex: 0,
                pointerEvents: 'none',
                opacity: 0.12,
            }}
        />
    );
}
