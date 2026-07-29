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

    const shell = canvas.closest<HTMLElement>('.app-shell');

    let frameId = 0;
    let width = 0;
    let height = 0;
    let minimumSpacing = 40;
    const pointer = { x: -1000, y: -1000, active: false };
    let particles: Particle[] = [];

    const createParticles = () => {
      const count = Math.min(148, Math.max(68, Math.floor((width * height) / 12500)));
      minimumSpacing = Math.max(34, Math.min(58, Math.sqrt((width * height) / count) * 0.42));
      particles = [];

      for (let index = 0; index < count; index += 1) {
        let x = Math.random() * width;
        let y = Math.random() * height;
        for (let attempt = 0; attempt < 30; attempt += 1) {
          const isSpaced = particles.every((particle) => Math.hypot(particle.x - x, particle.y - y) >= minimumSpacing);
          if (isSpaced) break;
          x = Math.random() * width;
          y = Math.random() * height;
        }
        particles.push({
          x,
          y,
          velocityX: (Math.random() - 0.5) * 0.22,
          velocityY: (Math.random() - 0.5) * 0.22,
          radius: 1.25 + Math.random() * 1.85,
        });
      }
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
      shell?.style.setProperty('--pointer-x', `${event.clientX}px`);
      shell?.style.setProperty('--pointer-y', `${event.clientY}px`);
      shell?.style.setProperty('--network-shift-x', `${(event.clientX - window.innerWidth / 2) * 0.012}px`);
      shell?.style.setProperty('--network-shift-y', `${(event.clientY - window.innerHeight / 2) * 0.012}px`);
      shell?.style.setProperty('--pointer-active', '1');
    };

    const clearPointer = () => {
      pointer.active = false;
      pointer.x = -1000;
      pointer.y = -1000;
      shell?.style.setProperty('--pointer-active', '0');
      shell?.style.setProperty('--network-shift-x', '0px');
      shell?.style.setProperty('--network-shift-y', '0px');
    };

    const drawConnection = (first: Particle, secondX: number, secondY: number, opacity: number) => {
      context.beginPath();
      context.moveTo(first.x, first.y);
      context.lineTo(secondX, secondY);
      context.strokeStyle = `rgba(34, 211, 238, ${opacity})`;
      context.lineWidth = 0.9;
      context.stroke();
    };

    const render = () => {
      context.clearRect(0, 0, width, height);

      particles.forEach((particle, index) => {
        if (pointer.active) {
          const pointerX = pointer.x - particle.x;
          const pointerY = pointer.y - particle.y;
          const pointerDistance = Math.hypot(pointerX, pointerY);
          if (pointerDistance < 230 && pointerDistance > 0) {
            const attraction = (1 - pointerDistance / 230) * 0.006;
            particle.velocityX += pointerX * attraction * 0.012;
            particle.velocityY += pointerY * attraction * 0.012;
            drawConnection(particle, pointer.x, pointer.y, (1 - pointerDistance / 230) * 0.36);
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
        context.fillStyle = 'rgba(165, 243, 252, 0.86)';
        context.fill();

        for (let neighborIndex = index + 1; neighborIndex < particles.length; neighborIndex += 1) {
          const neighbor = particles[neighborIndex];
          const deltaX = neighbor.x - particle.x;
          const deltaY = neighbor.y - particle.y;
          const distance = Math.hypot(deltaX, deltaY);
          if (distance > 0 && distance < minimumSpacing) {
            const repulsion = (1 - distance / minimumSpacing) * 0.006;
            particle.velocityX -= (deltaX / distance) * repulsion;
            particle.velocityY -= (deltaY / distance) * repulsion;
            neighbor.velocityX += (deltaX / distance) * repulsion;
            neighbor.velocityY += (deltaY / distance) * repulsion;
          }
          if (distance < 158) {
            drawConnection(particle, neighbor.x, neighbor.y, (1 - distance / 158) * 0.2);
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
