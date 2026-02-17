const canvas = document.getElementById('matrix-bg');
const ctx = canvas.getContext('2d');

let width = canvas.width = window.innerWidth;
let height = canvas.height = window.innerHeight;

const cols = Math.floor(width / 20);
const ypos = Array(cols).fill(0);

window.addEventListener('resize', () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
});

function matrix() {
    // Semi-transparent black to create trail effect
    ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
    ctx.fillRect(0, 0, width, height);

    ctx.fillStyle = '#0f0';
    ctx.font = '15pt monospace';

    ypos.forEach((y, ind) => {
        // Random Matrix character
        const text = String.fromCharCode(Math.random() * 128);
        const x = ind * 20;

        ctx.fillText(text, x, y);

        if (y > 100 + Math.random() * 10000) ypos[ind] = 0;
        else ypos[ind] = y + 20;
    });
}

setInterval(matrix, 50);
