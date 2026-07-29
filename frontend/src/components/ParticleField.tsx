import { useEffect, useRef } from 'react';

interface Particle {
  x: number;
  y: number;
  velocityX: number;
  velocityY: number;
  radius: number;
}

export default function ParticleField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const context = canvas.getContext('2d');
    if (!context) return;

    let frameId = 0;
    let width = 0;
    let height = 0;
    const pointer = { x: -1000, y: -1000, active: false };
    let particles: Particle[] = [];

    const createParticles = () => {
      const count = Math.min(72, Math.max(32, Math.floor((width * height) / 24000)));
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        velocityX: (Math.random() - 0.5) * 0.22,
        velocityY: (Math.random() - 0.5) * 0.22,
        radius: 0.7 + Math.random() * 1.2,
      }));
    };

    const resize = () => {
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.floor(width * pixelRatio);
      canvas.height = Math.floor(height * pixelRatio);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      createParticles();
    };

    const updatePointer = (event: PointerEvent) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      pointer.active = true;
    };

    const clearPointer = () => {
      pointer.active = false;
      pointer.x = -1000;
      pointer.y = -1000;
    };

    const drawConnection = (first: Particle, secondX: number, secondY: number, opacity: number) => {
      context.beginPath();
      context.moveTo(first.x, first.y);
      context.lineTo(secondX, secondY);
      context.strokeStyle = `rgba(34, 211, 238, ${opacity})`;
      context.lineWidth = 0.55;
      context.stroke();
    };

    const render = () => {
      context.clearRect(0, 0, width, height);

      particles.forEach((particle, index) => {
        if (pointer.active) {
          const pointerX = pointer.x - particle.x;
          const pointerY = pointer.y - particle.y;
          const pointerDistance = Math.hypot(pointerX, pointerY);
          if (pointerDistance < 170 && pointerDistance > 0) {
            const attraction = (1 - pointerDistance / 170) * 0.004;
            particle.velocityX += pointerX * attraction * 0.012;
            particle.velocityY += pointerY * attraction * 0.012;
            drawConnection(particle, pointer.x, pointer.y, (1 - pointerDistance / 170) * 0.16);
          }
        }

        particle.velocityX *= 0.995;
        particle.velocityY *= 0.995;
        particle.x += particle.velocityX;
        particle.y += particle.velocityY;

        if (particle.x < -10) particle.x = width + 10;
        if (particle.x > width + 10) particle.x = -10;
        if (particle.y < -10) particle.y = height + 10;
        if (particle.y > height + 10) particle.y = -10;

        context.beginPath();
        context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
        context.fillStyle = 'rgba(165, 243, 252, 0.48)';
        context.fill();

        for (let neighborIndex = index + 1; neighborIndex < particles.length; neighborIndex += 1) {
          const neighbor = particles[neighborIndex];
          const distance = Math.hypot(neighbor.x - particle.x, neighbor.y - particle.y);
          if (distance < 115) {
            drawConnection(particle, neighbor.x, neighbor.y, (1 - distance / 115) * 0.075);
          }
        }
      });

      frameId = window.requestAnimationFrame(render);
    };

    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', updatePointer, { passive: true });
    window.addEventListener('pointerleave', clearPointer);
    frameId = window.requestAnimationFrame(render);

    return () => {
      window.cancelAnimationFrame(frameId);
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', updatePointer);
      window.removeEventListener('pointerleave', clearPointer);
    };
  }, []);

  return <canvas ref={canvasRef} className="particle-field" aria-hidden="true" />;
}
