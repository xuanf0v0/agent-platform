<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const canvas = ref<HTMLCanvasElement>()
let frame = 0

onMounted(() => {
  const node = canvas.value!; const context = node.getContext('2d')!
  let width = 0; let height = 0; const pointer = { x: -9999, y: -9999 }
  const particles = Array.from({ length: 115 }, () => ({ x: Math.random(), y: Math.random(), vx: (Math.random() - .5) * .00011, vy: (Math.random() - .5) * .00011 }))
  const resize = () => { width = node.width = innerWidth * devicePixelRatio; height = node.height = innerHeight * devicePixelRatio }
  const move = (event: PointerEvent) => { pointer.x = event.clientX * devicePixelRatio; pointer.y = event.clientY * devicePixelRatio }
  const draw = () => {
    context.clearRect(0, 0, width, height)
    particles.forEach((particle) => {
      particle.x = (particle.x + particle.vx + 1) % 1; particle.y = (particle.y + particle.vy + 1) % 1
      const x = particle.x * width; const y = particle.y * height
      const dx = x - pointer.x; const dy = y - pointer.y; const distance = Math.hypot(dx, dy)
      if (distance < 190 * devicePixelRatio && distance > 1) { particle.x += dx / distance * .00035; particle.y += dy / distance * .00035 }
      context.fillStyle = 'rgba(91, 225, 255, .72)'; context.beginPath(); context.arc(x, y, 2.2 * devicePixelRatio, 0, Math.PI * 2); context.fill()
    })
    for (let first = 0; first < particles.length; first++) for (let second = first + 1; second < particles.length; second++) {
      const a = particles[first]!; const b = particles[second]!; const dx = (a.x - b.x) * width; const dy = (a.y - b.y) * height; const distance = Math.hypot(dx, dy)
      const min = 30 * devicePixelRatio; const max = 150 * devicePixelRatio
      if (distance > min && distance < max) { context.strokeStyle = `rgba(40, 196, 239, ${.28 * (1 - distance / max)})`; context.lineWidth = 1.2 * devicePixelRatio; context.beginPath(); context.moveTo(a.x * width, a.y * height); context.lineTo(b.x * width, b.y * height); context.stroke() }
    }
    frame = requestAnimationFrame(draw)
  }
  resize(); addEventListener('resize', resize); addEventListener('pointermove', move); draw()
  onBeforeUnmount(() => { cancelAnimationFrame(frame); removeEventListener('resize', resize); removeEventListener('pointermove', move) })
})
</script>
<template><canvas ref="canvas" class="particle-field" aria-hidden="true" /></template>
